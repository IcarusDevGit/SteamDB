"""
Database Update Helper Script for SteamDB.

Provides CLI functionality to:
1. Upsert entries from a CSV file into the PostgreSQL 'weeksheet' table.
2. Update entries in the 'weeksheet' table where rating is currently NULL using AppendRatings.py.
"""

import argparse
import csv
import os
import sys
import requests
import time

import FetchTop100Weekly
import AppendRatings
import AppendTags
import PriceScraper
import db

TIMEOUT = 10

def upsert_csv_to_db(csv_filepath: str = "C:/Dev/SteamDB/CSV/steam_top_100.csv", week_date_str: str = None):
    """
    Reads entries from a .csv file and upserts them to the weeksheet table in PostgreSQL using db.py.
    """
    if not week_date_str:
        week_date_str = FetchTop100Weekly.get_last_closed_tuesday()

    if not os.path.exists(csv_filepath):
        print(f"Error: CSV file not found at path: {csv_filepath}")
        return

    print(f"\nReading entries from '{csv_filepath}' for week date {week_date_str}...")
    entries = []
    with open(csv_filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append({
                "rank": int(row["rank"]) if row.get("rank") else None,
                "appid": int(row["appid"]) if row.get("appid") else None,
                "price": row.get("price") or None,
                "discount": int(row["discount"]) if row.get("discount") else None,
                "rating": float(row["rating"]) if row.get("rating") else 0.0,
                "last_week_rank": int(row["last_week_rank"]) if row.get("last_week_rank") else None,
                "consecutive_weeks": int(row["consecutive_weeks"]) if row.get("consecutive_weeks") else None,
            })

    db.create_tables()
    db.insert_weeksheet_entries(week_date_str, entries)
    print(f"Successfully upserted {len(entries)} entries from '{csv_filepath}' to 'weeksheet' table for week {week_date_str}.")


def update_null_ratings():
    """
    Queries weeksheet table for entries where rating IS NULL and uses AppendRatings.py to fetch and update ratings.
    """
    db.create_tables()

    null_entries = db.get_weeksheet_null_ratings()
    if not null_entries:
        print("No entries with NULL rating found in 'weeksheet' table.")
        return

    print(f"Found {len(null_entries)} distinct game(s) in 'weeksheet' with NULL rating.")

    # Use AppendRatings to fetch rating for each game
    rated_entries = AppendRatings.append_ratings(null_entries)

    updated_count = 0
    for entry in rated_entries:
        appid = entry.get("appid")
        rating = entry.get("rating")
        if appid is not None and rating is not None:
            db.update_weeksheet_rating(appid, rating)
            updated_count += 1

    print(f"\nSuccessfully updated ratings for {updated_count} game(s) in 'weeksheet' table.")


def update_null_prices():
    """Fetch and fill weeksheet rows where price or discount is NULL."""
    db.create_tables()
    entries = db.get_weeksheet_null_prices()
    if not entries:
        print("No entries with NULL price or discount found in 'weeksheet' table.")
        return
    print(f"Found {len(entries)} row(s) with missing price information.")
    updated = 0
    for entry in entries:
        appid = entry["appid"]
        week_date = entry["week_date"]
        try:
            price, discount = PriceScraper.main(appid, week_date)
            if price is not None and discount is not None:
                db.update_weeksheet_price(appid, week_date, price, discount)
                updated += 1
        except (ValueError, requests.RequestException, PriceScraper.PriceScraperError) as exc:
            print(f"Could not update appid {appid} for {week_date}: {exc}")
        time.sleep(PriceScraper.REQUEST_DELAY)
    print(f"Successfully updated price information for {updated} row(s).")


def update_last_week_rank(target_date_str: str = None):
    """
    Updates weeksheet table with last_week_rank fetched from Steam API.
    If target_date_str is provided, updates that specific date.
    Otherwise, queries weeksheet for dates where last_week_rank has not been populated.
    """
    db.create_tables()

    if target_date_str:
        dates_to_update = [target_date_str]
    else:
        dates_to_update = db.get_weeksheet_dates_with_null_last_week_rank()

    if not dates_to_update:
        print("No weeks with unpopulated last_week_rank found in 'weeksheet' table.")
        return

    print(f"Found {len(dates_to_update)} week(s) to update with last_week_rank: {', '.join(dates_to_update)}")

    for week_date in dates_to_update:
        print(f"\nFetching weekly top sellers for week {week_date} from Steam API...")
        try:
            raw_data = FetchTop100Weekly.fetch_weekly_top_sellers(start_date_str=week_date, count=100)
            ranks_data = FetchTop100Weekly.parse_results(raw_data)
            updated_count = db.update_weeksheet_last_week_ranks_batch(week_date, ranks_data)
            print(f"Successfully updated last_week_rank for {updated_count} entries on week {week_date}.")
        except Exception as e:
            print(f"Error updating last_week_rank for week {week_date}: {e}")

    print("\nCompleted updating last_week_rank in 'weeksheet' table.")


def update_consecutive_weeks(target_date_str: str = None):
    """
    Updates weeksheet table with consecutive_weeks fetched from Steam API.
    If target_date_str is provided, updates that specific date.
    Otherwise, queries weeksheet for dates where consecutive_weeks has not been populated.
    """
    db.create_tables()

    if target_date_str:
        dates_to_update = [target_date_str]
    else:
        dates_to_update = db.get_weeksheet_dates_with_null_consecutive_weeks()

    if not dates_to_update:
        print("No weeks with unpopulated consecutive_weeks found in 'weeksheet' table.")
        return

    print(f"Found {len(dates_to_update)} week(s) to update with consecutive_weeks: {', '.join(dates_to_update)}")

    for week_date in dates_to_update:
        print(f"\nFetching weekly top sellers for week {week_date} from Steam API...")
        try:
            raw_data = FetchTop100Weekly.fetch_weekly_top_sellers(start_date_str=week_date, count=100)
            ranks_data = FetchTop100Weekly.parse_results(raw_data)
            updated_count = db.update_weeksheet_consecutive_weeks_batch(week_date, ranks_data)
            print(f"Successfully updated consecutive_weeks for {updated_count} entries on week {week_date}.")
        except Exception as e:
            print(f"Error updating consecutive_weeks for week {week_date}: {e}")

    print("\nCompleted updating consecutive_weeks in 'weeksheet' table.")


def upsert_games():
    """
    Updates all games on the games table
    """

    name_lookup, all_games = db.fetch_all_games()
    for row in all_games:
        name = row["name"]
        appid = row["appid"]
        tags = row["tags"]
        if name == "":
            name = get_name_from_app_id(appid)
            print(name)
            db.upsert_game(appid, name, tags)

def get_name_from_app_id(appid):
    url = "https://store.steampowered.com/api/appdetails"
    params = {"appids": appid, "cc": "us", "l": "english"}
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()

    app_data = payload.get(str(appid), {}).get("data", {})
    return app_data.get("name", "")

def main():
    parser = argparse.ArgumentParser(
        description="SteamDB UpdateDB Script - Upsert CSV records or update missing ratings in database."
    )

    subparsers = parser.add_subparsers(dest="command", help="Sub-command to run")

    # Sub-command: upsert-csv
    csv_parser = subparsers.add_parser("upsert-csv", help="Upsert entries from CSV file to weeksheet table.")
    csv_parser.add_argument(
        "--csv", type=str, default="C:/Dev/SteamDB/CSV/steam_top_100.csv", help="Path to CSV file (default: C:/Dev/SteamDB/CSV/steam_top_100.csv)"
    )
    csv_parser.add_argument(
        "--date", "-d", type=str, default=None, help="Closed week date string YYYY-MM-DD (default: last closed Tuesday)"
    )

    # Sub-command: update-null-ratings
    subparsers.add_parser(
        "update-null-ratings", help="Fetch ratings via AppendRatings.py and update entries where rating IS NULL."
    )
    subparsers.add_parser(
        "update-null-prices", help="Fetch ITAD prices and update rows where price or discount is NULL."
    )
    subparsers.add_parser(
        "update-last-week-rank", help="Fetch last week ranks from Steam API and update weeksheet entries."
    )
    subparsers.add_parser(
        "update_last_week_rank", help="Fetch last week ranks from Steam API and update weeksheet entries."
    )
    subparsers.add_parser(
        "update-consecutive-weeks", help="Fetch consecutive weeks from Steam API and update weeksheet entries."
    )
    subparsers.add_parser(
        "update_consecutive_weeks", help="Fetch consecutive weeks from Steam API and update weeksheet entries."
    )

    # Sub-command: update-games
    subparsers.add_parser("update-games", help="Update entries on the games table.")

    # Sub-command: update-missing-tags
    subparsers.add_parser(
        "update-missing-tags", help="Fetch tags from SteamSpy for games with empty tags and write to CSV for validation."
    )

    # Sub-command: apply-missing-tags
    apply_parser = subparsers.add_parser(
        "apply-missing-tags", help="Apply resolved tags from the missing_tags CSV to the database."
    )
    apply_parser.add_argument(
        "--csv", type=str, default="C:/Dev/SteamDB/CSV/missing_tags.csv",
        help="Path to missing_tags CSV file (default: C:/Dev/SteamDB/CSV/missing_tags.csv)"
    )

    # Sub-command: resolve-missing-tags
    subparsers.add_parser(
        "resolve-missing-tags", help="Look up unresolved tags from the CSV on Steam API and upsert them to the DB tags table."
    )
    
    # Global flags for direct usage
    parser.add_argument(
        "--upsert-csv", action="store_true", help="Upsert entries from CSV to DB weeksheet table."
    )
    parser.add_argument(
        "--update-null-ratings", action="store_true", help="Fetch ratings and update NULL ratings in weeksheet table."
    )
    parser.add_argument(
        "--update-null-prices", action="store_true", help="Fetch prices and update NULL price fields."
    )
    parser.add_argument(
        "--update-last-week-rank", "--update_last_week_rank", action="store_true", help="Fetch last week ranks and update weeksheet entries."
    )
    parser.add_argument(
        "--update-consecutive-weeks", "--update_consecutive_weeks", action="store_true", help="Fetch consecutive weeks and update weeksheet entries."
    )
    parser.add_argument(
        "--update-games", action="store_true", help="Update entries on the games table."
    )
    parser.add_argument(
        "--update-missing-tags", action="store_true", help="Fetch tags from SteamSpy for games with empty tags and write to CSV."
    )
    parser.add_argument(
        "--apply-missing-tags", action="store_true", help="Apply resolved tags from the missing_tags CSV to the database."
    )
    parser.add_argument(
        "--resolve-missing-tags", action="store_true", help="Look up unresolved tags from the CSV on Steam API and upsert to DB."
    )
    parser.add_argument(
        "--csv", type=str, default="C:/Dev/SteamDB/CSV/steam_top_100.csv", help="Path to CSV file (default: C:/Dev/SteamDB/CSV/steam_top_100.csv)"
    )
    parser.add_argument(
        "--date", "-d", type=str, default=None, help="Closed week date string YYYY-MM-DD (default: last closed Tuesday)"
    )

    args = parser.parse_args()

    if args.command == "upsert-csv" or args.upsert_csv:
        upsert_csv_to_db(csv_filepath=args.csv, week_date_str=args.date)
    elif args.command == "update-null-ratings" or args.update_null_ratings:
        update_null_ratings()
    elif args.command == "update-null-prices" or args.update_null_prices:
        update_null_prices()
    elif args.command in ("update-last-week-rank", "update_last_week_rank") or args.update_last_week_rank:
        update_last_week_rank(target_date_str=args.date)
    elif args.command in ("update-consecutive-weeks", "update_consecutive_weeks") or args.update_consecutive_weeks:
        update_consecutive_weeks(target_date_str=args.date)
    elif args.command == "update-games" or args.update_games:
        upsert_games()
    elif args.command == "update-missing-tags" or args.update_missing_tags:
        AppendTags.update_missing_tags()
    elif args.command == "apply-missing-tags" or args.apply_missing_tags:
        AppendTags.apply_missing_tags()
    elif args.command == "resolve-missing-tags" or args.resolve_missing_tags:
        AppendTags.resolve_unresolved_tags()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
