"""Standalone database boundary for the isolated extraction and update workflows."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable
from collections import defaultdict

import psycopg2
from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPOSITORY_ROOT / ".env.local")
load_dotenv(REPOSITORY_ROOT / ".env")


def get_connection():
    """Create a PostgreSQL connection from standard environment settings."""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)
    kwargs = {
        "host": os.environ.get("PGHOST", os.environ.get("DB_HOST", "localhost")),
        "port": int(os.environ.get("PGPORT", os.environ.get("DB_PORT", "5432"))),
        "dbname": os.environ.get("PGDATABASE", os.environ.get("DB_NAME", "Steam")),
        "user": os.environ.get("PGUSER", os.environ.get("DB_USER", "postgres")),
    }
    password = os.environ.get("PGPASSWORD", os.environ.get("DB_PASS"))
    if password:
        kwargs["password"] = password
    sslmode = os.environ.get("PGSSLMODE")
    if sslmode:
        kwargs["sslmode"] = sslmode
    channel_binding = os.environ.get("PGCHANNELBINDING")
    if channel_binding:
        kwargs["channel_binding"] = channel_binding
    return psycopg2.connect(**kwargs)


def load_catalog_snapshot():
    """Read games/tags once; extraction performs no writes."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, tags FROM games")
            games = {int(appid): list(tag_ids or []) for appid, tag_ids in cursor.fetchall()}
            cursor.execute("SELECT id, name FROM tags")
            tags_by_name = {str(name): int(tag_id) for tag_id, name in cursor.fetchall()}
        return {"games": games, "tags_by_name": tags_by_name}
    finally:
        connection.close()


def apply_validated_records(records: Iterable[dict]) -> int:
    """Atomically upsert resolved entities and reconcile weekly rows as sets."""
    rows = list(records)
    if not rows:
        return 0
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for row in rows:
                tag_ids = list(row.get("tag_ids") or [])
                tag_names = list(row.get("tag_names") or [])
                for tag_id, tag_name in zip(tag_ids, tag_names):
                    cursor.execute(
                        "INSERT INTO tags (id, name) VALUES (%s, %s) "
                        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;",
                        (tag_id, tag_name),
                    )
                cursor.execute(
                    "INSERT INTO games (id, name, tags) VALUES (%s, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, tags = EXCLUDED.tags;",
                    (row["appid"], row.get("name", ""), tag_ids),
                )

            by_week = defaultdict(list)
            for row in rows:
                by_week[str(row["week_date"])].append(row)
            # Free ranks held by incoming games before assigning the validated
            # weekly set. A collision with an out-of-scope game still fails and
            # rolls back instead of silently overwriting an unauthorized row.
            for week_date, week_rows in by_week.items():
                cursor.execute(
                    "UPDATE weeksheet SET rank = rank + 1000000 "
                    "WHERE week_date = %s AND game_id = ANY(%s);",
                    (week_date, [row["appid"] for row in week_rows]),
                )
            for row in rows:
                cursor.execute(
                    """
                    INSERT INTO weeksheet
                        (week_date, rank, game_id, price, discount, rating,
                         last_week_rank, consecutive_weeks)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (week_date, game_id) DO UPDATE SET
                        rank = EXCLUDED.rank,
                        price = EXCLUDED.price,
                        discount = EXCLUDED.discount,
                        rating = EXCLUDED.rating,
                        last_week_rank = EXCLUDED.last_week_rank,
                        consecutive_weeks = EXCLUDED.consecutive_weeks;
                    """,
                    (
                        row["week_date"], row["rank"], row["appid"],
                        row.get("price"), row.get("discount"), row.get("rating"),
                        row.get("last_week_rank"), row.get("consecutive_weeks"),
                    ),
                )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _find_missing(column_sql: str, *, week=None, appid=None, limit=None):
    clauses = [column_sql]
    params = []
    if week:
        clauses.append("week_date = %s")
        params.append(week)
    if appid:
        clauses.append("game_id = %s")
        params.append(appid)
    query = (
        "SELECT game_id, week_date FROM weeksheet WHERE "
        + " AND ".join(clauses)
        + " ORDER BY week_date, game_id"
    )
    if limit:
        query += " LIMIT %s"
        params.append(limit)
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            return [{"appid": row[0], "week_date": row[1]} for row in cursor.fetchall()]
    finally:
        connection.close()


def find_missing_ratings(*, week=None, appid=None, limit=None):
    return _find_missing("rating IS NULL", week=week, appid=appid, limit=limit)


def find_missing_prices(*, week=None, appid=None, limit=None):
    return _find_missing("(price IS NULL OR discount IS NULL)", week=week, appid=appid, limit=limit)


def _apply_repairs(updates, statement, values):
    rows = list(updates)
    if not rows:
        return 0
    connection = get_connection()
    try:
        applied = 0
        with connection.cursor() as cursor:
            for row in rows:
                cursor.execute(statement, values(row))
                applied += max(cursor.rowcount, 0)
        connection.commit()
        return applied
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def apply_rating_repairs(updates):
    return _apply_repairs(
        updates,
        "UPDATE weeksheet SET rating = %s WHERE week_date = %s AND game_id = %s AND rating IS NULL;",
        lambda row: (row["rating"], row["week_date"], row["appid"]),
    )


def apply_price_repairs(updates):
    return _apply_repairs(
        updates,
        "UPDATE weeksheet SET price = COALESCE(price, %s), discount = COALESCE(discount, %s) "
        "WHERE week_date = %s AND game_id = %s AND (price IS NULL OR discount IS NULL);",
        lambda row: (row.get("price"), row.get("discount"), row["week_date"], row["appid"]),
    )


def apply_weekly_stat_repairs(updates):
    rows = list(updates)
    if not rows:
        return 0
    connection = get_connection()
    try:
        applied = 0
        with connection.cursor() as cursor:
            for row in rows:
                if "last_week_rank" in row and "consecutive_weeks" in row:
                    cursor.execute(
                        "UPDATE weeksheet SET last_week_rank = %s, consecutive_weeks = %s "
                        "WHERE week_date = %s AND rank = %s;",
                        (row["last_week_rank"], row["consecutive_weeks"], row["week_date"], row["rank"]),
                    )
                    applied += max(cursor.rowcount, 0)
                elif "last_week_rank" in row:
                    cursor.execute(
                        "UPDATE weeksheet SET last_week_rank = %s WHERE week_date = %s AND rank = %s;",
                        (row["last_week_rank"], row["week_date"], row["rank"]),
                    )
                    applied += max(cursor.rowcount, 0)
                else:
                    cursor.execute(
                        "UPDATE weeksheet SET consecutive_weeks = %s WHERE week_date = %s AND rank = %s;",
                        (row["consecutive_weeks"], row["week_date"], row["rank"]),
                    )
                    applied += max(cursor.rowcount, 0)
        connection.commit()
        return applied
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
