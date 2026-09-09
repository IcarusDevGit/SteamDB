"""Self-contained production HTTP adapters for the isolated pipeline."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, time, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from request_scheduler import RetryableRequestError
from workflow_models import HistoricalRating, StoreData, classify_rating_label


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env.local"))
load_dotenv(os.path.join(ROOT, ".env"))

STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "")
ITAD_API_KEY = os.environ.get("ITAD_API_KEY", "")
ITAD_COUNTRY = os.environ.get("ITAD_COUNTRY", "US")
STEAM_CHART_COUNTRY = os.environ.get("STEAM_CHART_COUNTRY", "")
STEAM_STORE_COUNTRY = os.environ.get("STEAM_STORE_COUNTRY", "US")
ITAD_SHOP_ID = 61
TIMEOUT = 20

STEAM_WEEKLY_URL = "https://api.steampowered.com/IStoreTopSellersService/GetWeeklyTopSellers/v1/"
STEAM_HISTOGRAM_URL = "https://store.steampowered.com/appreviewhistogram/{appid}"
STEAM_STORE_URL = "https://store.steampowered.com/app/{appid}/"
STEAM_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_TAG_LIST_URL = "https://api.steampowered.com/IStoreService/GetTagList/v1/"
ITAD_BASE_URL = "https://api.isthereanydeal.com"

COOKIES = {
    "birthtime": "283993201",
    "lastagecheckage": "1-January-1979",
    "wants_mature_content": "1",
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
}
CONTENT_DESCRIPTORS = {
    1: "Some Nudity or Sexual Content",
    2: "Frequent Violence or Gore",
    3: "Adult Only Sexual Content",
    4: "Frequent Nudity or Sexual Content",
    5: "General Mature Content",
}


def _raise_for_retry(response):
    """Translate transient HTTP responses for scheduler retry handling."""
    if response.status_code == 429:
        value = response.headers.get("Retry-After")
        raise RetryableRequestError(
            "provider rate limited the request",
            retry_after=float(value) if value else None,
        )
    if response.status_code >= 500:
        raise RetryableRequestError(f"provider returned HTTP {response.status_code}")
    response.raise_for_status()


def parse_weekly(payload: dict, week_date: str) -> list[dict]:
    """Normalize Steam's weekly ranks and deduplicate category identifiers."""
    records = []
    for entry in payload.get("response", {}).get("ranks", []):
        item = entry.get("item", {})
        category_ids = []
        seen = set()
        for value in item.get("content_descriptorids", []) or []:
            if isinstance(value, int) and value not in seen:
                category_ids.append(value)
                seen.add(value)
        for values in (item.get("categories", {}) or {}).values():
            for value in values if isinstance(values, list) else []:
                if isinstance(value, int) and value not in seen:
                    category_ids.append(value)
                    seen.add(value)
        records.append(
            {
                "week_date": week_date,
                "rank": entry.get("rank"),
                "appid": entry.get("appid"),
                "name": item.get("name", ""),
                "last_week_rank": entry.get("last_week_rank"),
                "consecutive_weeks": entry.get("consecutive_weeks"),
                "category_ids": category_ids,
            }
        )
    return records


def parse_histogram_rating(payload: dict, target_date: str) -> HistoricalRating:
    """Return cumulative review counts, rating, and label through the closed week.

    ``target_date`` is the Tuesday starting the chart week. Reviews from that
    Tuesday through Monday are included; reviews at or after the following
    Tuesday 00:00 UTC are excluded.
    """
    week_start = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    cutoff = (week_start.timestamp() + 7 * 24 * 60 * 60)
    positive = total = 0
    rollups = payload.get("results", {}).get("rollups", payload.get("rollups", []))
    for point in rollups:
        try:
            timestamp = float(point.get("date", point.get("timestamp", 0)))
        except (TypeError, ValueError):
            continue
        if timestamp >= cutoff:
            continue
        up = int(point.get("recommendations_up", point.get("positive", 0)) or 0)
        down = int(point.get("recommendations_down", point.get("negative", 0)) or 0)
        positive += up
        total += up + down
    return HistoricalRating(
        positive=positive,
        total=total,
        rating=positive / total if total else None,
        label=classify_rating_label(positive, total),
    )


def parse_store_html(html: str) -> StoreData:
    """Extract unique community tags and the primary purchase offer from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    tags = []
    for element in soup.select("a.app_tag"):
        name = element.get_text(strip=True)
        if name and name != "+" and name not in tags:
            tags.append(name)
    area = soup.select_one("#game_area_purchase") or soup
    block = area.select_one(".game_area_purchase_game:not(.demo_above_purchase)") or area
    discount_block = block.select_one(".discount_block")
    if discount_block:
        cents = discount_block.get("data-price-final")
        price = int(cents) / 100 if cents and str(cents).isdigit() else None
        discount_text = (
            discount_block.select_one(".discount_pct").get_text(" ", strip=True)
            if discount_block.select_one(".discount_pct")
            else ""
        )
        digits = "".join(char for char in discount_text if char.isdigit())
        return StoreData(price=price, discount=int(digits) if digits else 0, tags=tags)
    price_element = block.select_one(".game_purchase_price")
    if price_element:
        cents = price_element.get("data-price-final")
        if cents and str(cents).isdigit():
            return StoreData(price=int(cents) / 100, discount=0, tags=tags)
        if "free" in price_element.get_text(" ", strip=True).lower():
            return StoreData(price=0.0, discount=0, tags=tags)
    return StoreData(tags=tags)


class RealExtractionClients:
    """Adapt blocking Steam and ITAD HTTP APIs to the async pipeline contract.

    Public coroutine methods move their synchronous request counterpart to a
    worker thread; provider gates outside this class control scheduling.
    """
    def __init__(self, session=None):
        """Reuse an injected HTTP session or create one for this client."""
        self.session = session or requests.Session()

    async def weekly(self, week_date: str) -> list[dict]:
        """Fetch and normalize the weekly Steam chart without blocking the loop."""
        return await asyncio.to_thread(self._weekly, week_date)

    def _weekly(self, week_date):
        """Issue the blocking weekly-chart request for a Tuesday timestamp."""
        timestamp = int(datetime.strptime(week_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        input_json = {
            # Steam represents the global chart with an empty country code.
            # The request context still needs a real storefront country.
            "country_code": STEAM_CHART_COUNTRY,
            "context": {"country_code": STEAM_STORE_COUNTRY},
            "data_request": {"include_all_purchase_options": True, "include_basic_info": True},
            "page_start": 0,
            "page_count": 100,
            "start_date": timestamp,
        }
        response = self.session.get(
            STEAM_WEEKLY_URL,
            params={"key": STEAM_API_KEY, "input_json": json.dumps(input_json)},
            timeout=TIMEOUT,
        )
        _raise_for_retry(response)
        return parse_weekly(response.json(), week_date)

    async def tag_list(self) -> list[dict]:
        """Fetch Steam's canonical tag list in a worker thread."""
        return await asyncio.to_thread(self._tag_list)

    def _tag_list(self):
        """Return normalized IDs and names from Steam's tag-list endpoint."""
        response = self.session.get(
            STEAM_TAG_LIST_URL,
            params={"key": STEAM_API_KEY, "language": "english"},
            timeout=TIMEOUT,
        )
        _raise_for_retry(response)
        return [
            {"id": int(item["tagid"]), "name": str(item["name"]).strip()}
            for item in response.json().get("response", {}).get("tags", [])
            if item.get("tagid") and item.get("name")
        ]

    async def itad_lookup(self, appids: list[int]) -> dict[int, str | None]:
        """Resolve Steam IDs to ITAD IDs in a worker thread."""
        return await asyncio.to_thread(self._itad_lookup, appids)

    def _itad_lookup(self, appids):
        """Batch-deduplicate application IDs and call the ITAD lookup API."""
        if not ITAD_API_KEY:
            raise RuntimeError("ITAD_API_KEY is required")
        ids = list(dict.fromkeys(int(value) for value in appids))
        response = self.session.post(
            f"{ITAD_BASE_URL}/lookup/id/shop/{ITAD_SHOP_ID}/v1",
            headers={"ITAD-API-Key": ITAD_API_KEY},
            json=[f"app/{appid}" for appid in ids],
            timeout=TIMEOUT,
        )
        _raise_for_retry(response)
        payload = response.json()
        return {appid: payload.get(f"app/{appid}") for appid in ids}

    async def itad_history(self, itad_id: str, week_date: str):
        """Fetch the latest eligible historical deal for a chart week."""
        return await asyncio.to_thread(self._itad_history, itad_id, week_date)

    def _itad_history(self, itad_id, week_date):
        """Select the newest Steam-shop deal no later than the week's Tuesday."""
        start = datetime.strptime(week_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.combine(start.date(), time.max, tzinfo=timezone.utc)
        response = self.session.get(
            f"{ITAD_BASE_URL}/games/history/v2",
            headers={"ITAD-API-Key": ITAD_API_KEY},
            params={"id": itad_id, "country": ITAD_COUNTRY, "shops": ITAD_SHOP_ID, "since": start.isoformat()},
            timeout=TIMEOUT,
        )
        _raise_for_retry(response)
        eligible = []
        for event in response.json():
            if event.get("shop", {}).get("id") != ITAD_SHOP_ID:
                continue
            timestamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            if timestamp <= end:
                eligible.append((timestamp, event.get("deal")))
        if not eligible:
            return None, None
        deal = max(eligible, key=lambda item: item[0])[1]
        if not deal:
            return None, None
        return deal.get("price", {}).get("amount"), deal.get("cut")

    async def rating(self, appid: int, week_date: str):
        """Fetch the cumulative rating through the closed chart week."""
        return await asyncio.to_thread(self._rating, appid, week_date)

    async def rating_histogram(self, appid: int) -> dict:
        """Fetch one game's complete histogram for multi-week repair reuse."""
        return await asyncio.to_thread(self._rating_histogram, appid)

    def _rating_histogram(self, appid):
        """Request all available review rollups for one Steam application."""
        response = self.session.get(
            STEAM_HISTOGRAM_URL.format(appid=int(appid)),
            params={"l": "english", "start_date": 0},
            timeout=TIMEOUT,
        )
        _raise_for_retry(response)
        return response.json()

    def _rating(self, appid, week_date):
        """Request the review histogram bounded by the next Tuesday."""
        week_start = datetime.strptime(week_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        week_end = int(week_start.timestamp() + 7 * 24 * 60 * 60)
        response = self.session.get(
            STEAM_HISTOGRAM_URL.format(appid=int(appid)),
            params={"l": "english", "start_date": 0, "end_date": week_end},
            timeout=TIMEOUT,
        )
        _raise_for_retry(response)
        return parse_histogram_rating(response.json(), week_date)

    async def steam_html(self, appid: int):
        """Fetch and parse a Steam store page in a worker thread."""
        return await asyncio.to_thread(self._steam_html, appid)

    def _steam_html(self, appid):
        """Request a mature-content-enabled US store page and parse it."""
        response = self.session.get(
            STEAM_STORE_URL.format(appid=int(appid)),
            params={"cc": "us", "l": "english"},
            cookies=COOKIES,
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        _raise_for_retry(response)
        return parse_store_html(response.text)

    async def categories(self, appid: int, category_ids: list[int]):
        """Resolve requested category IDs from Steam application details."""
        return await asyncio.to_thread(self._categories, appid, category_ids)

    async def game_name(self, appid: int) -> str | None:
        """Resolve one English Steam display name in a worker thread."""
        return await asyncio.to_thread(self._game_name, appid)

    def _game_name(self, appid):
        """Return a normalized application-details name when Steam supplies one."""
        response = self.session.get(
            STEAM_DETAILS_URL,
            params={"appids": int(appid), "cc": "us", "l": "english"},
            timeout=TIMEOUT,
        )
        _raise_for_retry(response)
        entry = response.json().get(str(appid), {})
        if not isinstance(entry, dict) or not entry.get("success"):
            return None
        data = entry.get("data")
        if not isinstance(data, dict) or data.get("name") is None:
            return None
        name = str(data["name"]).strip()
        return name or None

    def _categories(self, appid, category_ids):
        """Return only requested categories, including known content descriptors."""
        response = self.session.get(
            STEAM_DETAILS_URL,
            params={"appids": int(appid), "cc": "us", "l": "english"},
            timeout=TIMEOUT,
        )
        _raise_for_retry(response)
        data = response.json().get(str(appid), {}).get("data", {})
        values = {
            int(item["id"]): item["description"].strip()
            for item in data.get("categories", [])
            if item.get("id") is not None and item.get("description")
        }
        for value in data.get("content_descriptors", {}).get("ids", []):
            if value in CONTENT_DESCRIPTORS:
                values.setdefault(value, CONTENT_DESCRIPTORS[value])
        wanted = set(category_ids)
        return {tag_id: name for tag_id, name in values.items() if tag_id in wanted}
