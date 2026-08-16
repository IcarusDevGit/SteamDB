import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
import requests

API_KEY = "2CE4F8F8A27675F987B80830C91C3F47"
BASE_URL = "https://api.steampowered.com/IStoreTopSellersService/GetWeeklyTopSellers/v1/"


def get_last_closed_tuesday(ref_date=None) -> str:
    """
    Calculates the Tuesday date string ('YYYY-MM-DD') for the last completed/closed chart week.
    
    - If ref_date is None: calculates the last closed Tuesday relative to current execution time.
    - If ref_date is provided (e.g. '2026-07-28'):
        - If it is already a Tuesday, uses it.
        - Otherwise, calculates the last closed Tuesday prior to or on ref_date.
    """
    if ref_date is None:
        ref = datetime.now(timezone.utc)
    elif isinstance(ref_date, str):
        ref = datetime.strptime(ref_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    elif isinstance(ref_date, datetime):
        ref = ref_date
    else:
        ref = datetime.now(timezone.utc)

    # In Python datetime.weekday(): Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
    # Current week's Tuesday:
    days_since_tuesday = (ref.weekday() - 1) % 7
    current_tuesday = ref - timedelta(days=days_since_tuesday)

    # If an explicit date string was passed and is already a Tuesday:
    if isinstance(ref_date, str) and ref.weekday() == 1:
        closed_tuesday = ref
    else:
        # The last CLOSED week ended on current_tuesday (starts 7 days prior)
        closed_tuesday = current_tuesday - timedelta(days=7)

    return closed_tuesday.strftime("%Y-%m-%d")


def week_start_timestamp(date_str: str) -> int:
    """date_str: 'YYYY-MM-DD' for the Tuesday the chart week starts."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def fetch_weekly_top_sellers(start_date_str=None, country="US", count=100):
    input_json = {
        "country_code": country,
        "context": {
            "country_code": country,
        },
        "data_request": {
            "include_all_purchase_options": True,  # pulls price info
            "include_basic_info": True,
        },
        "page_start": 0,
        "page_count": count,
    }
    if start_date_str:
        input_json["start_date"] = week_start_timestamp(start_date_str)

    params = {
        "key": API_KEY,
        "input_json": json.dumps(input_json),
    }

    resp = requests.get(BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_results(data):
    results = []
    ranks = data.get("response", {}).get("ranks", [])
    for entry in ranks:
        appid = entry.get("appid")
        item_info = entry.get("item", {})
        name = item_info.get("name")
        # Price: use best_purchase_option, fall back to 0 for F2P titles
        best_option = item_info.get("best_purchase_option", {})
        price = best_option.get("formatted_final_price", "")
        if not price and item_info.get("is_free"):
            price = 0
        results.append({
            "rank": entry.get("rank"),
            "appid": appid,
            "name": name,
            "price": price,
        })
    print(results)
    return results


def main(date_str=None):
    target_tuesday = get_last_closed_tuesday(date_str)
    print(f"Fetching closed weekly top sellers for week starting Tuesday: {target_tuesday}")

    raw = fetch_weekly_top_sellers(start_date_str=target_tuesday, count=100)
    top_sellers = parse_results(raw)

    for entry in top_sellers:
        print(f"#{entry['rank']}: {entry['name']} (appid: {entry['appid']})")

    print(f"Retrieved {len(top_sellers)} items for week {target_tuesday}.")
    return top_sellers, target_tuesday


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch closed weekly top sellers from Steam.")
    parser.add_argument("--date", "-d", type=str, default=None, help="Reference date (YYYY-MM-DD)")
    args = parser.parse_args()
    main(args.date)