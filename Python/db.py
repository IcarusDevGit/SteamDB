"""Standalone database boundary for the isolated extraction and update workflows."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable
from collections import defaultdict

import psycopg2
from psycopg2.extras import execute_values
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


def prepare_tag_candidates(records: Iterable[dict]) -> list[tuple[int, str]]:
    """Collapse repeated tag references and reject contradictory mappings."""
    candidates: dict[int, str] = {}
    for row in records:
        tag_ids = list(row.get("tag_ids") or [])
        tag_names = list(row.get("tag_names") or [])
        for tag_id, tag_name in zip(tag_ids, tag_names):
            tag_id = int(tag_id)
            tag_name = str(tag_name)
            if tag_id in candidates and candidates[tag_id] != tag_name:
                raise ValueError(
                    f"tag id {tag_id} has contradictory names: "
                    f"{candidates[tag_id]!r} and {tag_name!r}"
                )
            candidates.setdefault(tag_id, tag_name)
    return list(candidates.items())


def _bulk_values(cursor, statement: str, values: list[tuple]) -> None:
    """Execute one values-based bulk statement when candidates are present."""
    if values:
        execute_values(cursor, statement, values, page_size=len(values))


def apply_validated_records(records: Iterable[dict]) -> int:
    """Atomically upsert resolved entities and reconcile weekly rows as sets."""
    rows = list(records)
    if not rows:
        return 0
    tag_candidates = prepare_tag_candidates(rows)
    game_candidates = [
        (row["appid"], row.get("name", ""), list(row.get("tag_ids") or []))
        for row in rows
    ]
    weeksheet_candidates = [
        (
            row["week_date"], row["rank"], row["appid"],
            row.get("price"), row.get("discount"), row.get("rating"), row.get("rating_label"),
            row.get("last_week_rank"), row.get("consecutive_weeks"),
        )
        for row in rows
    ]
    # Every entity and weekly-row mutation shares one all-or-nothing transaction.
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            _bulk_values(
                cursor,
                "INSERT INTO tags (id, name) VALUES %s "
                "ON CONFLICT (id) DO NOTHING;",
                tag_candidates,
            )
            _bulk_values(
                cursor,
                "INSERT INTO games (id, name, tags) VALUES %s "
                "ON CONFLICT (id) DO NOTHING;",
                game_candidates,
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
            _bulk_values(
                cursor,
                """
                INSERT INTO weeksheet
                    (week_date, rank, game_id, price, discount, rating, rating_label,
                     last_week_rank, consecutive_weeks)
                VALUES %s
                ON CONFLICT (week_date, game_id) DO UPDATE SET
                    rank = EXCLUDED.rank,
                    price = EXCLUDED.price,
                    discount = EXCLUDED.discount,
                    rating = EXCLUDED.rating,
                    rating_label = EXCLUDED.rating_label,
                    last_week_rank = EXCLUDED.last_week_rank,
                    consecutive_weeks = EXCLUDED.consecutive_weeks;
                """,
                weeksheet_candidates,
            )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
