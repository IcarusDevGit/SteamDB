"""
Appends a "Rating" column to data received by using RatingScraper.py.
"""
import os
import time

import db
from RatingScraper import fetch_rating, REQUEST_DELAY


def append_ratings(data: list) -> list:
    """
    Appends a 'rating' key to each game dictionary in data using RatingScraper.py.
    """
    if not data:
        return []

    total = len(data)
    print(f"\nProcessing ratings for {total} games...")
    for i, item in enumerate(data, start=1):
        name = item.get("name", "Unknown")
        appid_raw = item.get("appid")

        if not appid_raw:
            print(f"[{i}/{total}] No appid for '{name}' -- defaulting rating to 0.0")
            item["rating"] = 0.0
            continue

        try:
            appid = int(appid_raw)
            raw_rating = fetch_rating(appid)
            item["rating"] = round(raw_rating, 2)
            print(f"[{i}/{total}] Appended rating {item['rating']} for '{name}' (appid {appid})")
        except Exception as e:
            print(f"[{i}/{total}] Could not fetch rating for '{name}' (appid {appid_raw}): {e}")
            item["rating"] = 0.0

        time.sleep(REQUEST_DELAY)

    return data


def main(data: list = None) -> list:
    if data is None:
        data = []
    return append_ratings(data)


if __name__ == "__main__":
    main()
