import json
import time
import requests

import db
import FetchSteamStoreTags

REQUEST_DELAY = 1.0     # seconds between SteamSpy requests -- keep at 1/sec, don't lower
TIMEOUT = 10             # seconds to wait for a response before giving up

STEAM_API_KEY = "2CE4F8F8A27675F987B80830C91C3F47"


import os

TAGS_EXCEPTIONS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "JSON", "TagsExceptions.JSON")


def load_tags_exceptions(filepath=None):
    """
    Loads tag exception/alias mappings from TagsExceptions.JSON.
    Returns:
        dict: {lower_tag_name: int_tag_id}
    """
    paths_to_try = [
        filepath,
        TAGS_EXCEPTIONS_PATH,
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "JSON", "TagsExceptions.json"),
        "C:/Dev/SteamDB/JSON/TagsExceptions.JSON",
        "C:/Dev/SteamDB/JSON/TagsExceptions.json",
    ]
    for path in paths_to_try:
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {k.strip().lower(): int(v) for k, v in data.items() if k.strip()}
            except Exception as e:
                print(f"[TagsScraper] Error reading {path}: {e}")
                return {}
    return {}


def fetch_tags_from_steam_store(appid):
    """
    Fetch genres and categories for a given appid from the Steam Store API.
    URL: https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=english
    Returns:
        list of genre and category name strings (merged, no duplicates)
    """
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=english"
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    app_data = data.get(str(appid), {})
    if not app_data.get("success"):
        return []

    inner_data = app_data.get("data", {})
    genres = inner_data.get("genres", [])
    categories = inner_data.get("categories", [])

    genre_names = [g.get("description", "").strip() for g in genres if g.get("description", "").strip()]
    category_names = [c.get("description", "").strip() for c in categories if c.get("description", "").strip()]

    # Merge genres and categories with no duplicates (case-insensitive dedup)
    merged = []
    seen = set()
    for name in genre_names + category_names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            merged.append(name)

    return merged


def fetch_tags(appid):
    """
    Fetch tags and genres for a given appid from both SteamSpy API and Steam Store API.
    Merges all genres, categories, and tags from both sources with no duplicates.
    Resolves tag names to IDs by querying the existing 'tags' table in the database
    and checking TagsExceptions.JSON.

    Returns:
        (resolved_names, resolved_ids, unresolved_names):
            - resolved_names: list of tag name strings found in the DB or exceptions
            - resolved_ids: list of corresponding tag IDs from the DB or exceptions
            - unresolved_names: list of tag names NOT found in the DB or exceptions
    """
    html_store_tags = []
    api_store_tags = []

    # 1. Fetch from Steam Store HTML page (user-defined tags)
    try:
        html_store_tags = FetchSteamStoreTags.fetch_tags(appid)
    except Exception as e:
        print(f"    [TagsScraper] HTML Store page scraping failed for appid {appid}: {e}")

    # 2. Fetch from Steam Store API (genres and categories)
    try:
        api_store_tags = fetch_tags_from_steam_store(appid)
    except Exception as e:
        print(f"    [TagsScraper] Steam Store API request failed for appid {appid}: {e}")

    # 3. Merge all tag sources with no duplicates (case-insensitive dedup, preserving order)
    seen = set()
    merged_names = []
    for name in html_store_tags + api_store_tags:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            merged_names.append(name)

    # 4. Resolve names to IDs from the DB tags table
    db_tags = db.fetch_all_tags()  # returns {name: tagid}
    # Build case-insensitive lookup
    db_tags_lower = {name.lower(): (name, tagid) for name, tagid in db_tags.items()}
    id_to_name = {tagid: name for name, tagid in db_tags.items()}

    # Load tag exceptions (e.g. "Rogue-lite": 3959)
    exceptions = load_tags_exceptions()

    resolved_names = []
    resolved_ids = []
    unresolved_names = []
    seen_ids = set()

    for name in merged_names:
        name_lower = name.lower()
        if name_lower in db_tags_lower:
            canonical_name, tagid = db_tags_lower[name_lower]
            if tagid not in seen_ids:
                resolved_names.append(canonical_name)
                resolved_ids.append(tagid)
                seen_ids.add(tagid)
        elif name_lower in exceptions:
            tagid = exceptions[name_lower]
            canonical_name = id_to_name.get(tagid, name)
            if tagid not in seen_ids:
                resolved_names.append(canonical_name)
                resolved_ids.append(tagid)
                seen_ids.add(tagid)
        else:
            unresolved_names.append(name)

    return resolved_names, resolved_ids, unresolved_names


def find_tag_id_by_name(tag_name):
    """
    Query the Steam GetTagList API to find a tag ID by name.
    Returns the tag ID (int) if found, None otherwise.
    """
    url = "https://api.steampowered.com/IStoreService/GetTagList/v1/"
    input_json = {"language": "english"}
    params = {"key": STEAM_API_KEY, "input_json": json.dumps(input_json)}
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    tags = data.get("response", {}).get("tags", [])

    for tag in tags:
        if tag["name"].lower() == tag_name.lower():
            return tag["tagid"]

    return None


def upsert_missing_tag(tag_name):
    """
    Find a tag ID by name using the Steam API and upsert it into the DB tags table.
    Returns (tag_name, tag_id) if successful, None if tag not found on Steam.
    """
    tag_id = find_tag_id_by_name(tag_name)
    if tag_id is None:
        print(f"    [TagsScraper] Tag '{tag_name}' not found in Steam tag list")
        return None

    db.upsert_tags_batch({tag_name: tag_id})
    print(f"    [TagsScraper] Upserted tag '{tag_name}' (ID: {tag_id}) to database")
    return tag_name, tag_id