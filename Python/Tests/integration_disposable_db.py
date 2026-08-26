"""Real PostgreSQL integration check using an isolated temporary schema."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import UpdateDB
import WriteCSV


class KeepOpenConnection:
    """Let the production transaction close logically while tests retain access."""

    def __init__(self, connection):
        self.connection = connection

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def close(self):
        pass


def connection_from_environment():
    if os.environ.get("ALLOW_DISPOSABLE_DB_TEST") != "1":
        raise RuntimeError("set ALLOW_DISPOSABLE_DB_TEST=1 to authorize temporary schema writes")
    if os.environ.get("DATABASE_URL"):
        return psycopg2.connect(os.environ["DATABASE_URL"])
    required = ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"missing PostgreSQL settings: {', '.join(missing)}")
    return psycopg2.connect(
        host=os.environ["PGHOST"],
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode=os.environ.get("PGSSLMODE", "require"),
        channel_binding=os.environ.get("PGCHANNELBINDING", "require"),
    )


def create_tables(connection, schema):
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.execute("CREATE TABLE tags (id INT PRIMARY KEY, name VARCHAR(255) NOT NULL UNIQUE)")
        cursor.execute("CREATE TABLE games (id INT PRIMARY KEY, name VARCHAR(255) NOT NULL, tags INT[] NOT NULL DEFAULT '{}')")
        cursor.execute(
            """CREATE TABLE weeksheet (
                id SERIAL PRIMARY KEY,
                week_date DATE NOT NULL,
                rank INT NOT NULL,
                game_id INT NOT NULL REFERENCES games(id),
                price DECIMAL(10,2), discount INT, rating DECIMAL(10,2),
                last_week_rank INT, consecutive_weeks INT,
                UNIQUE (week_date, rank), UNIQUE (week_date, game_id)
            )"""
        )
    connection.commit()


def validation_csv(directory, rows, name="approved.csv"):
    path = Path(directory) / name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=WriteCSV.FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    weeks = {item["week_date"] for item in rows}
    if len(weeks) == 1:
        report = path.with_name(f"{path.stem}.validation.json")
        report.write_text(json.dumps({
            "schema_version": 1,
            "status": "passed",
            "csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "weekly": {"week": next(iter(weeks))},
        }), encoding="utf-8")
    return path


def row(appid, rank, *, week="2026-08-04", tag_id=1, tag="Action", name=None):
    return {
        "week_date": week, "rank": rank, "appid": appid,
        "name": name or f"Disposable Game {appid}", "tags": tag, "tag_ids": str(tag_id),
        "unresolved_tags": "", "rating": 0.8, "price": 9.99,
        "discount": 20, "last_week_rank": 2, "consecutive_weeks": 3,
        "errors": "",
    }


def run():
    schema = f"codex_validation_{uuid.uuid4().hex}"
    connection = connection_from_environment()
    try:
        create_tables(connection, schema)
        original_get_connection = db.get_connection
        db.get_connection = lambda: KeepOpenConnection(connection)
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = validation_csv(directory, [row(10, 1), row(20, 2), row(30, 3)])
                first = UpdateDB.apply_csv(path, approved=True)
                swapped = validation_csv(
                    directory,
                    [
                        {
                            **row(10, 2, tag="Renamed Action", name="Renamed Game 10"),
                            "rating": 0.95, "price": 4.99, "discount": 50,
                            "last_week_rank": 1, "consecutive_weeks": 4,
                        },
                        row(20, 1, tag_id=2, tag="Strategy", name="Renamed Game 20"),
                    ],
                    name="swapped.csv",
                )
                second = UpdateDB.apply_csv(swapped, approved=True)
                third = UpdateDB.apply_csv(swapped, approved=True)
            with connection.cursor() as cursor:
                cursor.execute("SELECT (SELECT count(*) FROM tags), (SELECT count(*) FROM games), (SELECT count(*) FROM weeksheet)")
                counts = cursor.fetchone()
                cursor.execute("SELECT game_id, rank FROM weeksheet WHERE week_date='2026-08-04' ORDER BY rank")
                ranking = cursor.fetchall()
                cursor.execute("SELECT id, name FROM tags ORDER BY id")
                tags = cursor.fetchall()
                cursor.execute("SELECT id, name, tags FROM games ORDER BY id")
                games = cursor.fetchall()
                cursor.execute(
                    "SELECT rating, price, discount, last_week_rank, consecutive_weeks "
                    "FROM weeksheet WHERE week_date='2026-08-04' AND game_id=10"
                )
                weekly_facts = cursor.fetchone()
                cursor.execute("UPDATE weeksheet SET rating=NULL, price=NULL, discount=NULL WHERE game_id IN (10,20)")
            connection.commit()
            if first != 3 or second != 2 or third != 2 or counts != (2, 3, 3):
                raise AssertionError(f"unexpected apply result: {first=}, {second=}, {third=}, {counts=}")
            if ranking != [(20, 1), (10, 2), (30, 3)]:
                raise AssertionError(f"rank reconciliation failed: {ranking}")
            if tags != [(1, "Action"), (2, "Strategy")]:
                raise AssertionError(f"catalog tag insert/preservation failed: {tags}")
            if games != [
                (10, "Disposable Game 10", [1]),
                (20, "Disposable Game 20", [1]),
                (30, "Disposable Game 30", [1]),
            ]:
                raise AssertionError(f"catalog game preservation failed: {games}")
            if tuple(map(float, weekly_facts[:3])) != (0.95, 4.99, 50.0) or weekly_facts[3:] != (1, 4):
                raise AssertionError(f"weekly fact reconciliation failed: {weekly_facts}")

            db.apply_rating_repairs([{"week_date": "2026-08-04", "appid": 10, "rating": 0.9}])
            db.apply_price_repairs([{"week_date": "2026-08-04", "appid": 10, "price": 5.0, "discount": 50}])
            with connection.cursor() as cursor:
                cursor.execute("SELECT game_id, rating, price, discount FROM weeksheet WHERE game_id IN (10,20) ORDER BY game_id")
                repaired = cursor.fetchall()
            if (
                repaired[0][0] != 10 or float(repaired[0][1]) != 0.9
                or float(repaired[0][2]) != 5.0 or repaired[0][3] != 50
                or repaired[1][1:] != (None, None, None)
            ):
                raise AssertionError(f"targeted repair affected out-of-scope rows: {repaired}")

            bad_rows = [
                {**row(40, 1, week="2026-08-11", tag_id=3, tag="Collision")},
                {**row(50, 1, week="2026-08-18", tag_id=4, tag="Collision")},
            ]
            try:
                db.apply_validated_records([
                    {
                        "week_date": item["week_date"], "rank": item["rank"], "appid": item["appid"],
                        "name": item["name"], "tag_ids": [int(item["tag_ids"])], "tag_names": [item["tags"]],
                        "rating": item["rating"], "price": item["price"], "discount": item["discount"],
                        "last_week_rank": item["last_week_rank"], "consecutive_weeks": item["consecutive_weeks"],
                    } for item in bad_rows
                ])
                raise AssertionError("expected atomic transaction failure")
            except psycopg2.Error:
                pass
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM weeksheet WHERE week_date IN ('2026-08-11','2026-08-18')")
                if cursor.fetchone()[0] != 0:
                    raise AssertionError("failed multi-week apply was partially committed")
            print(
                "Disposable PostgreSQL integration passed: insert-only catalog, weekly reconciliation, "
                "atomic apply, rank swap, idempotency, and targeted repairs"
            )
        finally:
            db.get_connection = original_get_connection
    finally:
        try:
            connection.rollback()
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    run()
