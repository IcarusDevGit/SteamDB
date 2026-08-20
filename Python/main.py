import argparse
import csv
import os
import sys

import FetchTop100Weekly
import AppendTags
import AppendRatings
import PriceScraper
import WriteCSV
import db


def upsert_csv_to_db(csv_filepath: str, week_date_str: str):
    """
    Reads entries from .csv file and upserts them to the weeksheet table in PostgreSQL using db.py.
    """
    if not week_date_str:
        week_date_str = FetchTop100Weekly.get_last_closed_tuesday()

    if not os.path.exists(csv_filepath):
        print(f"CSV file not found: {csv_filepath}")
        return

    entries = []
    with open(csv_filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append({
                "rank": int(row["rank"]) if row.get("rank") else None,
                "appid": int(row["appid"]) if row.get("appid") else None,
                "price": row.get("price") or None,
                "discount": row.get("discount"),
                "rating": float(row["rating"]) if row.get("rating") else 0.0,
            })

    db.insert_weeksheet_entries(week_date_str, entries)
    print(f"Upserted {len(entries)} entries from '{csv_filepath}' to database 'weeksheet' table for week {week_date_str}.")


def main():
    parser = argparse.ArgumentParser(
        description="SteamDB Top 100 Collector - Fetches closed chart week and updates database/csv."
    )
    parser.add_argument(
        "date_arg",
        nargs="?",
        default=None,
        help="Optional date (YYYY-MM-DD). If provided, fetches closed week for that date. If omitted, uses last closed Tuesday."
    )
    parser.add_argument(
        "--date", "-d",
        type=str,
        default=None,
        help="Optional reference date (YYYY-MM-DD)."
    )
    args = parser.parse_args()

    # Determine reference date if passed positionally or via --date flag
    target_date_str = args.date or args.date_arg

    print("Ensuring PostgreSQL database tables exist...")
    db.create_tables()

    # 1. Fetch top 100 data (appid, name, price, rank)
    print("\n1. Fetching last closed weekly top sellers from Steam API...")
    raw_data, closed_week_date = FetchTop100Weekly.main(date_str=target_date_str)

    # 2. Get games from data and append tags with AppendTags.py to any games not found on db
    print(f"\n2. Processing tags for closed week {closed_week_date} (DB lookup -> scraper fallback -> DB upserts)...")
    data_with_tags = AppendTags.main(week_date_str=closed_week_date, data=raw_data)

    # 3. Append ratings to data with AppendRatings.py
    print(f"\n3. Fetching and appending ratings with AppendRatings.py...")
    data_with_ratings = AppendRatings.main(data=data_with_tags)

    # 4. Replace the current Steam price with its historical value for the chart date.
    print(f"\n4. Fetching Steam prices for {closed_week_date} with PriceScraper.py...")
    data_with_prices = PriceScraper.append_prices(data_with_ratings, closed_week_date)

    # Transform to final data structure: [{'rank': 1, 'appid': 730, 'price': 0, 'rating': 0.95}]
    final_data = []
    for item in data_with_prices:
        final_data.append({
            "rank": item.get("rank"),
            "appid": item.get("appid"),
            "name": item.get("name"),
            "tags": item.get("Tags", ""),
            "rating": item.get("rating", 0.0),
            "price": item.get("price"),
            "discount": item.get("discount"),
        })

    # 5. Write data to .csv using WriteCSV.py
    csv_filename = "steam_top_100.csv"
    print(f"\n5. Writing final data to {csv_filename} using WriteCSV.py...")
    WriteCSV.main(final_data, filepath=csv_filename)

    # 5. Method for upserting entries from .csv to weeksheet table on db using script on db.py (Commented out per Workflow.md)
    # print(f"\n5. Upserting entries from {csv_filename} to database weeksheet table...")
    # upsert_csv_to_db(csv_filename, closed_week_date)


if __name__ == "__main__":
    main()
