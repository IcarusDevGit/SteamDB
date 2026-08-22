"""Fetch historical Steam prices from the IsThereAnyDeal API."""

import os
import time
from datetime import date as date_type
from datetime import datetime, time as datetime_time, timezone

import requests
from dotenv import load_dotenv

import FetchPriceFromSteam


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env.local"))
load_dotenv(os.path.join(BASE_DIR, ".env"))

API_BASE_URL = "https://api.isthereanydeal.com"
API_KEY = os.environ.get("ITAD_API_KEY", "")
STEAM_SHOP_ID = 61
COUNTRY = os.environ.get("ITAD_COUNTRY", "US")
TIMEOUT = 20
REQUEST_DELAY = 0.1


class PriceScraperError(RuntimeError):
    """Raised when price data cannot be retrieved from IsThereAnyDeal."""


def _api_key(api_key=None):
    key = api_key or API_KEY
    if not key:
        raise PriceScraperError(
            "Missing IsThereAnyDeal API key. Set ITAD_API_KEY in .env.local or the environment."
        )
    return key


def _request(method, path, *, api_key=None, session=None, **kwargs):
    client = session or requests
    headers = dict(kwargs.pop("headers", {}))
    headers["ITAD-API-Key"] = _api_key(api_key)
    response = client.request(
        method,
        f"{API_BASE_URL}{path}",
        headers=headers,
        timeout=TIMEOUT,
        **kwargs,
    )
    if response.status_code == 429:
        retry_after = min(float(response.headers.get("Retry-After", 1)), 30)
        time.sleep(retry_after)
        response = client.request(
            method,
            f"{API_BASE_URL}{path}",
            headers=headers,
            timeout=TIMEOUT,
            **kwargs,
        )
    response.raise_for_status()
    return response.json()


def lookup_game(steam_id, *, api_key=None, session=None):
    """Return an ITAD game UUID for a Steam app ID, or ``None`` if unmapped."""
    appid = int(steam_id)
    shop_game_id = f"app/{appid}"
    payload = _request(
        "POST",
        f"/lookup/id/shop/{STEAM_SHOP_ID}/v1",
        api_key=api_key,
        session=session,
        json=[shop_game_id],
    )
    print(f"found id {payload.get(shop_game_id)} for steam id {steam_id}")
    return payload.get(shop_game_id)


def _parse_target_date(value):
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date_type):
        parsed = value
    else:
        try:
            parsed = datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("date must use YYYY-MM-DD format") from exc
    end = datetime.combine(parsed, datetime_time.max, tzinfo=timezone.utc)
    start = datetime.combine(parsed, datetime_time.min, tzinfo=timezone.utc)
    return start, end


def _parse_timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def history_log(game_id, target_date, *, api_key=None, session=None):
    """Return ``(price, discount)`` for Steam at the end of ``target_date`` (UTC).

    Price is the numeric amount in ITAD's returned currency (US requests normally
    return USD); discount is an integer percentage. Both are ``None`` when no
    Steam price state is available for that date.
    """
    start, end = _parse_target_date(target_date)
    payload = _request(
        "GET",
        "/games/history/v2",
        api_key=api_key,
        session=session,
        params={
            "id": game_id,
            "country": COUNTRY,
            "shops": STEAM_SHOP_ID,
            "since": start.isoformat(),
        },
    )

    eligible = []
    for event in payload:
        if event.get("shop", {}).get("id") != STEAM_SHOP_ID:
            continue
        timestamp = _parse_timestamp(event["timestamp"])
        if timestamp <= end:
            eligible.append((timestamp, event.get("deal")))

    if not eligible:
        print(f"no price found for game {game_id}")
        return None, None

    _, deal = max(eligible, key=lambda item: item[0])
    if not deal:
        print(f"no deal found for game {game_id}")
        return None, None
    price = deal.get("price", {}).get("amount")
    discount = deal.get("cut")
    return price, discount


def append_prices(data, target_date, *, api_key=None, session=None):
    """Add historical ``price`` and ``discount`` fields to game dictionaries."""
    if not data:
        return []
    client = session or requests.Session()
    total = len(data)
    print(f"looking up prices for {total} games")
    for index, item in enumerate(data, 1):
        appid = item.get("appid")
        name = item.get("name", "Unknown")
        try:
            price, discount = main(appid, target_date, api_key=api_key, session=client)
            item["price"] = price
            item["discount"] = discount
            print(f"[{index}/{total}] {name}: price={price}, discount={discount}")
        except (ValueError, requests.RequestException, PriceScraperError) as exc:
            print(f"[{index}/{total}] Could not fetch price for {name} (appid {appid}): {exc}")
            item["price"] = None
            item["discount"] = None
        time.sleep(REQUEST_DELAY)
    return data


def main(appid, date, *, api_key=None, session=None):
    """Return a Steam game's historical price, falling back to its store page."""
    if appid in (None, ""):
        return None, None
    game_id = lookup_game(appid, api_key=api_key, session=session)
    if not game_id:
        print(f"No ITAD mapping for appid {appid}; fetching the current Steam store price")
        return FetchPriceFromSteam.fetch_price(appid, session=session)

    price, discount = history_log(game_id, date, api_key=api_key, session=session)
    if price is None and discount is None:
        print(f"No ITAD price history for appid {appid}; fetching the current Steam store price")
        return FetchPriceFromSteam.fetch_price(appid, session=session)
    return price, discount


# Backwards-compatible names from the original scaffold.
LookupGame = lookup_game
HistoryLog = history_log
