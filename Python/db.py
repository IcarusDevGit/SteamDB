"""
Database Helper Module for SteamDB (PostgreSQL).

Manages PostgreSQL connection, table initialization, and CRUD operations for `games`, `tags`, and `weeksheet` tables.
"""

import os
import re
import sys

try:
    import psycopg2
    from psycopg2.extras import execute_batch
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env.local'))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Database Connection Settings (can be configured via environment variables)
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_NAME = os.environ.get("DB_NAME", "Steam")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_connection():
    """Establish and return a PostgreSQL database connection."""
    if not HAS_PSYCOPG2:
        raise ImportError(
            "psycopg2 module is not installed. Please run: pip install psycopg2-binary"
        )
    
    if DATABASE_URL:
        try:
            return psycopg2.connect(DATABASE_URL)
        except psycopg2.OperationalError as e:
            print(f"\n[Neon PostgreSQL Connection Error]: {e}", file=sys.stderr)
            raise e

    kwargs = {
        "host": DB_HOST,
        "port": DB_PORT,
        "dbname": DB_NAME,
        "user": DB_USER,
    }
    if DB_PASS:
        kwargs["password"] = DB_PASS

    try:
        return psycopg2.connect(**kwargs)
    except psycopg2.OperationalError as e:
        print(f"\n[PostgreSQL Connection Error]: {e}", file=sys.stderr)
        print(
            "\nTips to resolve:\n"
            "1. If your 'postgres' user has a password, set DB_PASS in Python/db.py or set environment variable DB_PASS.\n"
            "2. Make sure PostgreSQL service is running on port 5432.\n"
            "3. Ensure database 'Steam' exists in PostgreSQL (CREATE DATABASE \"Steam\";).\n",
            file=sys.stderr
        )
        raise e


def create_tables(conn=None):
    """Ensure PostgreSQL schema tables and indexes exist."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    create_sql = """
    CREATE TABLE IF NOT EXISTS tags (
        id INT PRIMARY KEY,
        name VARCHAR(255) NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS games (
        id INT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        tags INT[] DEFAULT '{}'::INT[]
    );

    CREATE TABLE IF NOT EXISTS weeksheet (
        id SERIAL PRIMARY KEY,
        week_date DATE NOT NULL,
        rank INT NOT NULL,
        game_id INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
        price DECIMAL(10, 2),
        discount INT,
        rating DECIMAL(10, 2),
        CONSTRAINT unique_week_rank UNIQUE (week_date, rank),
        CONSTRAINT unique_week_game UNIQUE (week_date, game_id)
    );

    ALTER TABLE weeksheet ADD COLUMN IF NOT EXISTS rating DECIMAL(10, 2);
    ALTER TABLE weeksheet ADD COLUMN IF NOT EXISTS discount INT;
    ALTER TABLE weeksheet ALTER COLUMN price DROP NOT NULL;

    CREATE INDEX IF NOT EXISTS idx_weeksheet_date ON weeksheet (week_date);
    CREATE INDEX IF NOT EXISTS idx_weeksheet_game ON weeksheet (game_id);
    """
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()

    if close_after:
        conn.close()


def normalize(name: str) -> str:
    """Normalize string for fuzzy/exact matching."""
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r"[™®©]", "", name)
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def get_game_tags_by_appid(appid: int):
    """
    Check PostgreSQL database for an existing game and its tags by appid.
    Returns:
        (tag_names, tag_ids): Tuple of (list of tag names, list of tag IDs) if found with tags,
                             or (None, None) if not found or has no tags recorded.
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT tags FROM games WHERE id = %s;", (appid,))
        row = cur.fetchone()

        if not row or not row[0]:
            conn.close()
            return None, None

        tag_ids = row[0]
        if not tag_ids:
            conn.close()
            return None, None

        # Resolve tag IDs to tag names
        cur.execute("SELECT id, name FROM tags WHERE id = ANY(%s);", (tag_ids,))
        tag_rows = cur.fetchall()

    conn.close()

    tag_map = {tid: tname for tid, tname in tag_rows}
    # Preserve order of tag_ids
    tag_names = [tag_map[tid] for tid in tag_ids if tid in tag_map]

    if tag_names:
        return tag_names, tag_ids
    return None, None


def fetch_all_games():
    """
    Fetch all games from PostgreSQL database.
    Returns:
        name_lookup (dict): normalized_name -> appid
        all_games (list): list of dicts {"appid": int, "name": str, "tags": list}
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, tags FROM games;")
        rows = cur.fetchall()
    conn.close()

    name_lookup = {}
    all_games = []

    for appid, name, tags in rows:
        norm = normalize(name)
        if norm and norm not in name_lookup:
            name_lookup[norm] = appid
        all_games.append({
            "appid": appid,
            "name": name,
            "tags": tags or []
        })
    
    return name_lookup, all_games


def fetch_all_tags():
    """
    Fetch all tags from PostgreSQL database.
    Returns:
        tag_lookup (dict): lower_name -> tagid
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM tags;")
        rows = cur.fetchall()
    conn.close()

    return {name: tagid for tagid, name in rows}


def upsert_game(appid: int, name: str, tags: list = None):
    """Insert or update a single game in PostgreSQL database."""
    conn = get_connection()
    tags = tags or []
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO games (id, name, tags)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE 
            SET name = EXCLUDED.name,
                tags = CASE WHEN array_length(EXCLUDED.tags, 1) > 0 THEN EXCLUDED.tags ELSE games.tags END;
            """,
            (appid, name, tags)
        )
    conn.commit()
    conn.close()


def upsert_tags_batch(tags_with_ids: dict):
    """Insert new tags into the PostgreSQL tags table safely."""
    if not tags_with_ids:
        return

    tuples = []
    for k, v in tags_with_ids.items():
        if isinstance(k, int):
            tagid, name = k, v
        elif isinstance(v, int):
            name, tagid = k, v
        else:
            try:
                tagid, name = int(v), str(k)
            except ValueError:
                tagid, name = int(k), str(v)
        tuples.append((tagid, name))

    conn = get_connection()
    with conn.cursor() as cur:
        # Fetch existing tag IDs and names to prevent duplicate name/id conflicts
        cur.execute("SELECT id, name FROM tags;")
        existing_rows = cur.fetchall()
        existing_ids = {r[0] for r in existing_rows}
        existing_names = {r[1].lower() for r in existing_rows}

        filtered_tuples = []
        for tagid, name in tuples:
            if tagid not in existing_ids and name.lower() not in existing_names:
                filtered_tuples.append((tagid, name))
                existing_ids.add(tagid)
                existing_names.add(name.lower())

        if filtered_tuples:
            execute_batch(
                cur,
                "INSERT INTO tags (id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                filtered_tuples,
                page_size=500
            )
    conn.commit()
    conn.close()


def update_game_tags(appid: int, tag_ids: list):
    """Update the tags array for a game in PostgreSQL."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE games SET tags = %s WHERE id = %s;",
            (tag_ids or [], appid)
        )
    conn.commit()
    conn.close()


def insert_weeksheet_entries(week_date_str: str, entries: list):
    """Insert weekly top 100 ranking entries into the PostgreSQL weeksheet table."""
    if not entries:
        return

    conn = get_connection()
    tuples = []

    for entry in entries:
        rank = entry.get("rank")
        appid = entry.get("appid")
        name = entry.get("name", "")
        price_val = entry.get("price", 0)
        rating = entry.get("rating", 0.0)
        discount = entry.get("discount")

        if price_val in (None, ""):
            price = None
        elif isinstance(price_val, str):
            clean_price = re.sub(r"[^\d.]", "", price_val)
            price = float(clean_price) if clean_price else None
        else:
            price = float(price_val)

        if appid and rank:
            upsert_game(appid, name)
            tuples.append((week_date_str, rank, appid, price, discount, rating))

    query = """
    INSERT INTO weeksheet (week_date, rank, game_id, price, discount, rating)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (week_date, rank) DO UPDATE 
    SET game_id = EXCLUDED.game_id, price = EXCLUDED.price,
        discount = EXCLUDED.discount, rating = EXCLUDED.rating;
    """

    with conn.cursor() as cur:
        execute_batch(cur, query, tuples, page_size=200)
    conn.commit()
    conn.close()


def get_weeksheet_null_ratings():
    """
    Fetch distinct game_ids and names from weeksheet where rating IS NULL.
    Returns a list of dicts [{'appid': game_id, 'name': name}, ...].
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT w.game_id, COALESCE(g.name, '') 
            FROM weeksheet w
            LEFT JOIN games g ON w.game_id = g.id
            WHERE w.rating IS NULL;
        """)
        rows = cur.fetchall()
    conn.close()

    return [{"appid": row[0], "name": row[1]} for row in rows]


def update_weeksheet_rating(game_id: int, rating: float):
    """
    Update rating in weeksheet for a given game_id where rating IS NULL.
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE weeksheet SET rating = %s WHERE game_id = %s AND rating IS NULL;",
            (rating, game_id)
        )
    conn.commit()
    conn.close()


def get_weeksheet_null_prices():
    """Return rows whose price or discount is missing, preserving each week date."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT game_id, week_date
            FROM weeksheet
            WHERE price IS NULL OR discount IS NULL
            ORDER BY week_date, game_id;
        """)
        rows = cur.fetchall()
    conn.close()
    return [{"appid": row[0], "week_date": row[1]} for row in rows]


def update_weeksheet_price(game_id, week_date, price, discount):
    """Fill missing historical price fields for one game/week pair."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE weeksheet
            SET price = COALESCE(price, %s), discount = COALESCE(discount, %s)
            WHERE game_id = %s AND week_date = %s
              AND (price IS NULL OR discount IS NULL);
        """, (price, discount, game_id, week_date))
    conn.commit()
    conn.close()
