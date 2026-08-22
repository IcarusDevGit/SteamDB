"""Fetch the current price and discount from a Steam store page."""

import re

import requests
from bs4 import BeautifulSoup


TIMEOUT = 10
STORE_URL = "https://store.steampowered.com/app/{appid}/"
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


def _price_from_text(value):
    """Convert a US-formatted Steam price string to a numeric amount."""
    if not value:
        return None
    text = value.strip()
    if "free" in text.lower():
        return 0.0
    match = re.search(r"(?:US\$|\$)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _discount_from_text(value):
    if not value:
        return 0
    match = re.search(r"-?\s*(\d+)\s*%", value)
    return int(match.group(1)) if match else 0


def parse_price_html(html):
    """Return ``(final_price, discount_percent)`` from Steam store HTML."""
    soup = BeautifulSoup(html, "html.parser")
    purchase_area = soup.select_one("#game_area_purchase") or soup

    # The first game purchase block is the base game. Later blocks can be deluxe
    # editions, soundtracks, DLC, or bundles with different prices.
    purchase_block = (
        purchase_area.select_one(".game_area_purchase_game:not(.demo_above_purchase)")
        or purchase_area
    )
    discount_block = purchase_block.select_one(".discount_block")
    if discount_block is not None:
        final_price_cents = discount_block.get("data-price-final")
        if final_price_cents and str(final_price_cents).isdigit():
            price = int(final_price_cents) / 100
        else:
            final_element = discount_block.select_one(".discount_final_price")
            price = _price_from_text(final_element.get_text(" ", strip=True) if final_element else None)

        discount_element = discount_block.select_one(".discount_pct")
        discount = _discount_from_text(
            discount_element.get_text(" ", strip=True) if discount_element else None
        )
        if price is not None:
            return price, discount

    price_element = purchase_block.select_one(".game_purchase_price")
    if price_element is not None:
        final_price_cents = price_element.get("data-price-final")
        if final_price_cents and str(final_price_cents).isdigit():
            return int(final_price_cents) / 100, 0
        price = _price_from_text(price_element.get_text(" ", strip=True))
        if price is not None:
            return price, 0

    return None, None


def fetch_price(appid, *, session=None):
    """Fetch the current US Steam price and return ``(price, discount)``."""
    if appid in (None, ""):
        return None, None

    client = session or requests
    try:
        response = client.get(
            STORE_URL.format(appid=int(appid)),
            params={"cc": "us", "l": "english"},
            cookies=COOKIES,
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        price, discount = parse_price_html(response.text)
        if price is None:
            print(f"[FetchPriceFromSteam] No price found for appid {appid}")
        return price, discount
    except (TypeError, ValueError, requests.RequestException) as exc:
        print(f"[FetchPriceFromSteam] Error fetching price for appid {appid}: {exc}")
        return None, None


if __name__ == "__main__":
    test_appid = 1091500
    print(f"Fetching price for AppID {test_appid}...")
    print(fetch_price(test_appid))
