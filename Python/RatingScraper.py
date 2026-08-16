"""
Scrapes rating from https://store.steampowered.com/appreviews/{appid}?json=1 for the weekly entry of a game
"""

import json
import requests

REQUEST_DELAY = 1.0

def fetch_rating(appid):
    """Fetches rating for a given appid from Steam API."""
    url = f"https://store.steampowered.com/appreviews/{appid}?json=1"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    total_reviews = data.get("query_summary", {}).get("total_reviews", 0)
    positive_reviews = data.get("query_summary", {}).get("total_positive", 0)
    rating = float(positive_reviews) / float(total_reviews)
    return rating

def main():
    """Main function."""
    appid = input("Enter appid: ")
    rating = fetch_rating(appid)
    print(json.dumps(rating, indent=2))

if __name__ == "__main__":
    main()