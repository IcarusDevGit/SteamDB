"""
Appends a "Tags" column to data received.

Workflow:
1. Consults the PostgreSQL database (`games` table) by appid.
2. If the game/tags are not found in the database, calls TagsScraper.py to fetch tags from SteamSpy API.
3. At the end of the process, upserts all new games.
"""

import csv
import os
import time

import db
from FetchTop100Weekly import get_last_closed_tuesday
from TagsScraper import fetch_tags, upsert_missing_tag, load_tags_exceptions, REQUEST_DELAY

MISSING_TAGS_CSV = "C:/Dev/SteamDB/CSV/missing_tags.csv"


def main(week_date_str=None, data: dict = {}):
    # Ensure PostgreSQL database tables exist
    db.create_tables()

    if not week_date_str:
        week_date_str = get_last_closed_tuesday()

    total = len(data)
    print(f"\nProcessing {total} games for week {week_date_str}...")

    csv_rows = []

    for i, entry in enumerate(data, start=1):
        name = entry.get("name", "")
        appid_raw = str(entry.get("appid", "")).strip()

        if not appid_raw:
            print(f"[{i}/{total}] No appid for '{name}' -- leaving Tags blank")
            entry["Tags"] = ""
            continue

        try:
            appid = int(appid_raw)
        except ValueError:
            print(f"[{i}/{total}] Invalid appid '{appid_raw}' for '{name}' -- skipping")
            continue

        # 1. Consult PostgreSQL database first
        db_tag_names, db_tag_ids = db.get_game_tags_by_appid(appid)

        if db_tag_names is not None:
            # Found in DB
            entry["Tags"] = ", ".join(db_tag_names)
            print(f"[{i}/{total}] {name} (appid {appid}) [Found in DB]: {entry['Tags'][:60]}")
        else:
            # 2. Not found in DB -> Consult TagsScraper.py (SteamSpy API)
            print(f"[{i}/{total}] {name} (appid {appid}) [Not in DB -> Scraping tags...]")
            try:
                tag_names, tag_ids, unresolved = fetch_tags(appid)
                entry["Tags"] = ", ".join(tag_names)

                # Upsert game entry directly to database
                db.upsert_game(appid, name, tag_ids)

                csv_rows.append({
                    "appid": appid,
                    "name": name,
                    "tags": ", ".join(tag_names),
                    "unresolved_tags": ", ".join(unresolved),
                })

                if unresolved:
                    print(f"    -> Scraped tags: {entry['Tags'][:60]}")
                    print(f"    -> Unresolved: {', '.join(unresolved)[:60]}")
                else:
                    print(f"    -> Scraped tags: {entry['Tags'][:60]}")
            except Exception as e:
                import traceback
                print(f"    -> Failed to fetch tags for '{name}' (appid {appid}): {e}")
                traceback.print_exc()
                entry["Tags"] = ""
                db.upsert_game(appid, name, [])

            time.sleep(REQUEST_DELAY)

    # Write CSV log of scraped games for validation
    if csv_rows:
        csv_path = MISSING_TAGS_CSV
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["appid", "name", "tags", "unresolved_tags"])
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"\nWrote {len(csv_rows)} scraped game(s) to '{csv_path}' for validation.")

    print(f"\nDone. Processed {total} games.")
    return data


def update_missing_tags(csv_path=MISSING_TAGS_CSV):
    """
    Queries the database for all games with empty tags, fetches tags from
    SteamSpy for each, and writes the results to a CSV for validation.
    Does NOT update the database -- use apply_missing_tags() after reviewing the CSV.
    """
    db.create_tables()

    _, all_games = db.fetch_all_games()
    games_missing_tags = [g for g in all_games if not g["tags"]]

    if not games_missing_tags:
        print("No games with empty tags found in database.")
        return

    total = len(games_missing_tags)
    print(f"\nFound {total} game(s) with empty tags. Fetching from SteamSpy...\n")

    csv_rows = []
    for i, game in enumerate(games_missing_tags, start=1):
        appid = game["appid"]
        name = game["name"]

        print(f"[{i}/{total}] {name} (appid {appid}) -> Fetching tags...")
        try:
            tag_names, tag_ids, unresolved = fetch_tags(appid)
            csv_rows.append({
                "appid": appid,
                "name": name,
                "tags": ", ".join(tag_names),
                "unresolved_tags": ", ".join(unresolved),
            })
            if unresolved:
                print(f"    -> {len(tag_names)} resolved, {len(unresolved)} unresolved: {', '.join(unresolved)[:60]}")
            else:
                print(f"    -> {len(tag_names)} tag(s): {', '.join(tag_names)[:60]}")
        except Exception as e:
            print(f"    -> Failed to fetch tags for '{name}' (appid {appid}): {e}")
            csv_rows.append({"appid": appid, "name": name, "tags": "", "unresolved_tags": ""})

        time.sleep(REQUEST_DELAY)

    # Write CSV for validation
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["appid", "name", "tags", "unresolved_tags"])
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\nDone. Wrote {len(csv_rows)} entries to '{csv_path}'.")
    print("Review the CSV, then run 'apply-missing-tags' to update the database.")


def apply_missing_tags(csv_path=MISSING_TAGS_CSV):
    """
    Reads the missing_tags CSV and applies resolved tags to the database.
    Only tags that exist in the DB tags table or TagsExceptions.JSON are resolved;
    unresolved tags are skipped.
    """
    if not os.path.exists(csv_path):
        print(f"CSV file not found: {csv_path}")
        return

    db.create_tables()

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("CSV is empty, nothing to apply.")
        return

    # Build case-insensitive tag lookup from DB and exceptions
    db_tags = db.fetch_all_tags()  # {name: tagid}
    db_tags_lower = {name.lower(): tagid for name, tagid in db_tags.items()}
    exceptions = load_tags_exceptions()

    updated = 0
    for row in rows:
        appid = int(row["appid"])
        name = row.get("name", "")
        tag_names_str = row.get("tags", "")
        unresolved_str = row.get("unresolved_tags", "")

        # Collect tag names from both 'tags' and 'unresolved_tags'
        tag_names = []
        if tag_names_str:
            tag_names.extend([t.strip() for t in tag_names_str.split(",") if t.strip()])
        if unresolved_str:
            tag_names.extend([t.strip() for t in unresolved_str.split(",") if t.strip()])

        if not tag_names:
            continue

        tag_ids = []
        seen_ids = set()
        for tn in tag_names:
            tn_lower = tn.lower()
            tid = db_tags_lower.get(tn_lower) or exceptions.get(tn_lower)
            if tid and tid not in seen_ids:
                tag_ids.append(tid)
                seen_ids.add(tid)

        if tag_ids:
            db.update_game_tags(appid, tag_ids)
            updated += 1
            print(f"  Updated {name} (appid {appid}) with {len(tag_ids)} tag(s)")

    print(f"\nDone. Updated {updated}/{len(rows)} game(s) in database.")


def resolve_unresolved_tags(csv_path=MISSING_TAGS_CSV):
    """
    Reads the missing_tags CSV, collects all unique unresolved tag names,
    checks if they exist in the DB tags table or TagsExceptions.JSON first,
    then looks up any remaining unresolved tags via the Steam API and upserts
    them into the DB tags table.
    After this, run apply-missing-tags to update game entries.
    """
    if not os.path.exists(csv_path):
        print(f"CSV file not found: {csv_path}")
        return

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Collect unique unresolved tag names
    unresolved_set = set()
    for row in rows:
        unresolved_str = row.get("unresolved_tags", "")
        if unresolved_str:
            for tag_name in unresolved_str.split(","):
                tag_name = tag_name.strip()
                if tag_name:
                    unresolved_set.add(tag_name)

    if not unresolved_set:
        print("No unresolved tags found in CSV.")
        return

    print(f"\nFound {len(unresolved_set)} unique unresolved tag(s). Checking database & exceptions, then Steam API...\n")

    # 1. Check existing database tags (case-insensitive)
    db_tags = db.fetch_all_tags()
    db_tags_lower = {name.lower(): (name, tagid) for name, tagid in db_tags.items()}
    id_to_name = {tagid: name for name, tagid in db_tags.items()}

    # 2. Check TagsExceptions.JSON
    exceptions = load_tags_exceptions()

    resolved = 0
    failed = []
    for tag_name in sorted(unresolved_set):
        tag_lower = tag_name.lower()
        if tag_lower in db_tags_lower:
            db_name, tag_id = db_tags_lower[tag_lower]
            if db_name.lower() == tag_lower and db_name != tag_name:
                print(f"    [Database] Tag '{tag_name}' found in database as '{db_name}' (ID: {tag_id})")
            else:
                print(f"    [Database] Tag '{tag_name}' found in database (ID: {tag_id})")
            resolved += 1
        elif tag_lower in exceptions:
            tag_id = exceptions[tag_lower]
            canonical_name = id_to_name.get(tag_id, tag_name)
            print(f"    [Exceptions] Tag '{tag_name}' mapped to '{canonical_name}' (ID: {tag_id})")
            resolved += 1
        else:
            result = upsert_missing_tag(tag_name)
            if result:
                resolved += 1
                resolved_name, resolved_id = result
                db_tags_lower[resolved_name.lower()] = (resolved_name, resolved_id)
                id_to_name[resolved_id] = resolved_name
            else:
                failed.append(tag_name)

    print(f"\nDone. Resolved {resolved}/{len(unresolved_set)} tag(s).")
    if failed:
        print(f"Could not find in DB, exceptions, or on Steam: {', '.join(failed)}")
    if resolved:
        print("Run 'apply-missing-tags' to update game entries with the newly resolved tags.")


if __name__ == "__main__":
    main()
