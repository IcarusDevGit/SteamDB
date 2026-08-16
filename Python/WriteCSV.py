"""
Writes given data to a .csv file.
"""

import csv
import json
import os


def write_csv(data: list, filepath: str = "CSV/steam_top_100.csv") -> str:
    """
    Writes a list of dictionaries to a CSV file.
    Expects data elements to contain keys: 'rank', 'appid', 'price', 'rating'.
    """
    if not data:
        print("No data provided to write to CSV.")
        return filepath

    fieldnames = ["rank", "appid", "price", "rating"]

    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            writer.writerow({
                "rank": row.get("rank"),
                "appid": row.get("appid"),
                "price": row.get("price"),
                "rating": row.get("rating"),
            })

    print(f"Successfully wrote {len(data)} records to {filepath}")
    return filepath


def main(data: list = None, filepath: str = "steam_top_100.csv") -> str:
    if data is None:
        data = []
    return write_csv(data, filepath)


if __name__ == "__main__":
    main()