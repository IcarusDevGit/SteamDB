"""
Writes given data to a .csv file.
"""

import csv
import json
import os


def write_csv(data: list, filepath: str = "CSV/steam_top_100.csv") -> str:
    """
    Writes a list of dictionaries to a CSV file.
    Expects: rank, appid, name, tags, rating, price, and discount.
    """
    if not data:
        print("No data provided to write to CSV.")
        return filepath

    fieldnames = ["rank", "appid", "name", "tags", "rating", "price", "discount"]

    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            writer.writerow({
                "rank": row.get("rank"),
                "appid": row.get("appid"),
                "name": row.get("name"),
                "tags": row.get("tags", row.get("Tags", "")),
                "rating": row.get("rating"),
                "price": row.get("price"),
                "discount": row.get("discount"),
            })

    print(f"Successfully wrote {len(data)} records to {filepath}")
    return filepath


def main(data: list = None, filepath: str = "steam_top_100.csv") -> str:
    if data is None:
        data = []
    return write_csv(data, filepath)


if __name__ == "__main__":
    main()
