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
from database_updates.repairs import game_names, prices, ratings, weekly_identities, weekly_stats


class KeepOpenConnection:
    """Let the production transaction close logically while tests retain access."""

    def __init__(self, connection):
        """Wrap a real connection whose physical lifetime the harness controls."""
        self.connection = connection

    def __getattr__(self, name):
        """Delegate transaction and cursor operations to the real connection."""
        return getattr(self.connection, name)

    def close(self):
        """Ignore production close calls so teardown can inspect and clean up."""
        pass


def connection_from_environment():
    """Connect only after explicit authorization and complete credentials.

    The opt-in guard prevents an ordinary unit-test run from creating schemas
    against an accidentally configured PostgreSQL database.
    """
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
    """Create the production-shaped tables inside a unique temporary schema."""
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.execute("CREATE TABLE tags (id INT PRIMARY KEY, name VARCHAR(255) NOT NULL UNIQUE)")
        cursor.execute("CREATE TABLE games (id INT PRIMARY KEY, name VARCHAR(255), tags INT[] NOT NULL DEFAULT '{}')")
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
    """Write an approved CSV fixture and its matching validation evidence."""
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
    """Build one normalized persistence row for integration scenarios."""
    return {
        "week_date": week, "rank": rank, "appid": appid,
        "name": name or f"Disposable Game {appid}", "tags": tag, "tag_ids": str(tag_id),
        "unresolved_tags": "", "rating": 0.8, "price": 9.99,
        "discount": 20, "last_week_rank": 2, "consecutive_weeks": 3,
        "errors": "",
    }


def run():
    """Exercise real transactional updates, then drop the disposable schema."""
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

            rating_candidates = ratings.find_candidates(week="2026-08-04")
            price_candidates = prices.find_candidates(week="2026-08-04")
            if {row["appid"] for row in rating_candidates} != {10, 20}:
                raise AssertionError(f"rating candidate selection failed: {rating_candidates}")
            if {row["appid"] for row in price_candidates} != {10, 20}:
                raise AssertionError(f"price candidate selection failed: {price_candidates}")
            repair_events = []
            ratings.apply_updates(
                [{"week_date": "2026-08-04", "appid": 10, "rating": 0.9}],
                reporter=repair_events.append,
            )
            prices.apply_updates(
                [{"week_date": "2026-08-04", "appid": 10, "price": 5.0, "discount": 50}],
                reporter=repair_events.append,
            )
            weekly_stats.apply_updates([{
                "week_date": "2026-08-04", "rank": 2,
                "last_week_rank": 8, "consecutive_weeks": 9,
            }], reporter=repair_events.append)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT game_id, rating, price, discount, last_week_rank, consecutive_weeks "
                    "FROM weeksheet WHERE game_id IN (10,20) ORDER BY game_id"
                )
                repaired = cursor.fetchall()
            if (
                repaired[0][0] != 10 or float(repaired[0][1]) != 0.9
                or float(repaired[0][2]) != 5.0 or repaired[0][3] != 50
                or repaired[0][4:] != (8, 9)
                or repaired[1][1:4] != (None, None, None)
            ):
                raise AssertionError(f"targeted repair affected out-of-scope rows: {repaired}")

            with connection.cursor() as cursor:
                cursor.execute("UPDATE games SET name=NULL WHERE id=10")
                cursor.execute("UPDATE games SET name='' WHERE id=20")
                cursor.execute("UPDATE games SET name='   ' WHERE id=30")
                cursor.execute("INSERT INTO games (id, name, tags) VALUES (40, 'Existing Name', '{}')")
            connection.commit()
            name_candidates = game_names.find_candidates()
            if [(item["appid"], item["current_name"]) for item in name_candidates] != [
                (20, ""), (30, "   "),
            ]:
                raise AssertionError(f"whitespace-name discovery failed: {name_candidates}")
            if [item["appid"] for item in game_names.find_candidates(limit=1)] != [20]:
                raise AssertionError("game-name limit did not narrow whitespace candidates")
            if [item["appid"] for item in game_names.find_candidates(appid=30)] != [30]:
                raise AssertionError("game-name appid target did not narrow whitespace candidates")
            if game_names.find_candidates(appid=40):
                raise AssertionError("populated name was selected for repair")
            game_names.apply_updates([
                {"appid": appid, "name": f"Steam Name {appid}"} for appid in (20, 30)
            ], reporter=repair_events.append)
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, name FROM games ORDER BY id")
                refreshed_names = cursor.fetchall()
            if refreshed_names != [
                (10, None), (20, "Steam Name 20"),
                (30, "Steam Name 30"), (40, "Existing Name"),
            ]:
                raise AssertionError(f"game-name refresh failed: {refreshed_names}")
            with connection.cursor() as cursor:
                cursor.execute("UPDATE games SET name='' WHERE id IN (20,30)")
            connection.commit()
            try:
                game_names.apply_updates([
                    {"appid": 20, "name": "Must Roll Back"},
                    {"appid": 30, "name": "x" * 300},
                ])
                raise AssertionError("expected atomic game-name transaction failure")
            except psycopg2.Error:
                pass
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM games WHERE id=20")
                if cursor.fetchone()[0] != "":
                    raise AssertionError("failed game-name repair was partially committed")

            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO weeksheet (week_date, rank, game_id, price, discount, rating, last_week_rank, consecutive_weeks) VALUES "
                    "('2026-08-11',1,10,11.00,10,0.70,2,3), ('2026-08-11',2,20,22.00,20,0.80,4,5), "
                    "('2026-08-18',1,10,33.00,30,0.60,2,3), ('2026-08-18',2,20,44.00,40,0.90,4,5), "
                    "('2026-08-25',1,10,55.00,50,0.95,2,3), ('2026-08-25',2,20,66.00,60,0.96,3,4)"
                )
            connection.commit()

            def identity_row(week, rank, appid, name, *, price=None, discount=None, rating=None):
                return {
                    "week_date": week, "rank": rank, "appid": appid, "name": name,
                    "price": price, "discount": discount, "rating": rating,
                    "last_week_rank": rank + 1, "consecutive_weeks": 2,
                }

            first_plan = weekly_identities.WeekPlan(
                "2026-08-11",
                (
                    identity_row("2026-08-11", 1, 20, "Steam Name 20", price=22.0, discount=20, rating=0.8),
                    identity_row("2026-08-11", 2, 50, "Global Game 50"),
                ),
                ((2, 50),), ((1, 10),), ((20, 2, 1),), 0,
            )
            failing_later_plan = weekly_identities.WeekPlan(
                "2026-08-18",
                (
                    identity_row("2026-08-18", 1, 20, "Steam Name 20", price=44.0, discount=40, rating=0.9),
                    identity_row("2026-08-18", 1, 60, "Global Game 60"),
                ),
                ((2, 60),), ((1, 10),), ((20, 2, 1),), 0,
            )
            try:
                weekly_identities.apply_plans([first_plan, failing_later_plan])
                raise AssertionError("expected later-week identity reconciliation failure")
            except psycopg2.Error:
                pass
            with connection.cursor() as cursor:
                cursor.execute("SELECT rank, game_id FROM weeksheet WHERE week_date='2026-08-11' ORDER BY rank")
                if cursor.fetchall() != [(1, 10), (2, 20)]:
                    raise AssertionError("earlier weekly identity repair survived later failure")
                cursor.execute("SELECT count(*) FROM games WHERE id IN (50,60)")
                if cursor.fetchone()[0] != 0:
                    raise AssertionError("catalog inserts survived failed identity repair")

            second_plan = weekly_identities.WeekPlan(
                "2026-08-18",
                (
                    identity_row("2026-08-18", 1, 20, "Steam Name 20", price=44.0, discount=40, rating=0.9),
                    identity_row("2026-08-18", 2, 60, "Global Game 60"),
                ),
                ((2, 60),), ((1, 10),), ((20, 2, 1),), 0,
            )
            correct_plan = weekly_identities.WeekPlan(
                "2026-08-25",
                (
                    identity_row("2026-08-25", 1, 10, "Global Game 10", price=55.0, discount=50, rating=0.95),
                    identity_row("2026-08-25", 2, 20, "Steam Name 20", price=66.0, discount=60, rating=0.96),
                ),
                (), (), (), 2,
            )
            if weekly_identities.apply_plans(
                [first_plan, second_plan, correct_plan], reporter=repair_events.append,
            ) != 2:
                raise AssertionError("weekly identity plans were not both applied")
            weekly_identities.apply_plans([first_plan, second_plan, correct_plan])
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT week_date, rank, game_id, price, discount, rating FROM weeksheet "
                    "WHERE week_date IN ('2026-08-11','2026-08-18') ORDER BY week_date, rank"
                )
                identities = cursor.fetchall()
                cursor.execute("SELECT id, name, tags FROM games WHERE id IN (10,50,60) ORDER BY id")
                identity_games = cursor.fetchall()
            if [tuple(row[:3]) for row in identities] != [
                (identities[0][0], 1, 20), (identities[0][0], 2, 50),
                (identities[2][0], 1, 20), (identities[2][0], 2, 60),
            ]:
                raise AssertionError(f"global identity reconciliation failed: {identities}")
            if tuple(map(float, identities[0][3:])) != (22.0, 20.0, 0.8) or identities[1][3:] != (None, None, None):
                raise AssertionError(f"identity enrichment preservation/default failed: {identities}")
            if identity_games != [
                (10, None, [1]), (50, "Global Game 50", []), (60, "Global Game 60", []),
            ]:
                raise AssertionError(f"identity catalog preservation/insertion failed: {identity_games}")
            progress_operations = {
                event.fields.get("operation") for event in repair_events
                if event.kind == "persistence_progress"
            }
            if progress_operations != {
                "repair_ratings", "repair_prices", "repair_weekly_stats",
                "repair_game_names", "repair_weekly_identities",
            }:
                raise AssertionError(f"repair persistence progress incomplete: {progress_operations}")

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
                if cursor.fetchone()[0] != 4:
                    raise AssertionError("failed multi-week apply was partially committed")
            print(
                "Disposable PostgreSQL integration passed: insert-only catalog, weekly reconciliation, "
                "atomic apply, rank swap, idempotency, correct-week skipping, targeted repairs, "
                "and whitespace-name repair"
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
