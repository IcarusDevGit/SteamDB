"""Discover and bulk-apply missing historical Steam rating labels."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from psycopg2.extras import execute_values

import db
from workflow_clients import RealExtractionClients, parse_histogram_rating
from workflow_progress import emit

from ..common import UpdateResult
from .common import add_target_arguments, describe_target, persistence_progress, unit_completed, unit_started


COMMAND = "rating-labels"
OPERATION = "repair_rating_labels"


def find_candidates(*, week=None, appid=None, limit=None, connection_factory=None):
    """Load every selected null-label weekly row with one query."""
    clauses = ["rating_label IS NULL"]
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
        + " ORDER BY game_id, week_date"
    )
    if limit:
        query += " LIMIT %s"
        params.append(limit)
    connection = (connection_factory or db.get_connection)()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            return [{"appid": row[0], "week_date": row[1]} for row in cursor.fetchall()]
    finally:
        connection.close()


def _rollups(payload):
    """Validate that a histogram response exposes a reusable rollup list."""
    results = payload.get("results") if isinstance(payload, dict) else None
    value = results.get("rollups") if isinstance(results, dict) else payload.get("rollups") if isinstance(payload, dict) else None
    if not isinstance(value, list):
        raise ValueError("Steam histogram response has no valid rollups")
    return value


async def discover(candidates, clients, reporter=None):
    """Fetch each unique game once and derive every selected weekly label."""
    grouped = defaultdict(list)
    for row in candidates:
        grouped[int(row["appid"])].append(row)
    completed_games = 0
    total_games = len(grouped)

    async def one_game(appid, rows):
        nonlocal completed_games
        identity = f"appid={appid}"
        unit_started(reporter, OPERATION, "steam_histogram", identity, total=total_games)
        try:
            payload = await clients.rating_histogram(appid)
            _rollups(payload)
            results = [
                (row, parse_histogram_rating(payload, str(row["week_date"])).label, None)
                for row in rows
            ]
            outcome = "completed"
            error = None
        except Exception as exc:
            error = str(exc)
            results = [(row, None, error) for row in rows]
            outcome = "failed"
        completed_games += 1
        unit_completed(
            reporter, OPERATION, "steam_histogram", identity, outcome,
            completed=completed_games, total=total_games, error=error,
        )
        return results

    groups = await asyncio.gather(*(one_game(appid, rows) for appid, rows in grouped.items()))
    return [result for group in groups for result in group]


def apply_updates(updates, *, connection_factory=None, reporter=None):
    """Persist all still-null labels with one values-based statement and transaction."""
    rows = list(updates)
    if not rows:
        return 0
    values = [(row["week_date"], row["appid"], row["rating_label"]) for row in rows]
    connection = (connection_factory or db.get_connection)()
    try:
        with connection.cursor() as cursor:
            execute_values(
                cursor,
                "UPDATE weeksheet AS target SET rating_label = source.rating_label "
                "FROM (VALUES %s) AS source(week_date, game_id, rating_label) "
                "WHERE target.week_date = source.week_date::date "
                "AND target.game_id = source.game_id::integer "
                "AND target.rating_label IS NULL;",
                values,
                page_size=len(values),
            )
            applied = max(cursor.rowcount, 0)
            persistence_progress(reporter, OPERATION, "all-rating-label-updates", len(rows), len(rows))
        connection.commit()
        return applied
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def register_parser(subparsers):
    """Register the full-set-by-default rating-label repair."""
    parser = subparsers.add_parser(COMMAND, help="Repair missing historical rating labels")
    add_target_arguments(parser)
    parser.set_defaults(handler=run)


def run(args, dependencies=None):
    """Discover all selected labels before optionally bulk-persisting them."""
    dependencies = dependencies or {}
    connection_factory = dependencies.get("connection_factory") or db.get_connection
    clients = dependencies.get("clients") or RealExtractionClients()
    reporter = dependencies.get("reporter")
    supplied_target = describe_target(args)
    target = "all-null-rating-labels" if supplied_target == "unbounded" else supplied_target

    emit(reporter, "stage_started", operation=OPERATION, stage="discovery", target=target)
    try:
        candidates = find_candidates(
            week=args.week, appid=args.appid, limit=args.limit,
            connection_factory=connection_factory,
        )
    except Exception as exc:
        emit(reporter, "stage_failed", operation=OPERATION, stage="discovery", error=exc)
        raise
    emit(reporter, "stage_completed", operation=OPERATION, stage="discovery", total=len(candidates))

    emit(reporter, "stage_started", operation=OPERATION, stage="external_lookup", total=len(candidates))
    try:
        discovered = asyncio.run(discover(candidates, clients, reporter))
    except Exception as exc:
        emit(reporter, "stage_failed", operation=OPERATION, stage="external_lookup", error=exc)
        raise
    emit(reporter, "stage_completed", operation=OPERATION, stage="external_lookup", total=len(candidates))

    updates = [
        {"week_date": str(row["week_date"]), "appid": row["appid"], "rating_label": label}
        for row, label, error in discovered if label is not None and error is None
    ]
    if args.apply and updates:
        emit(reporter, "stage_started", operation=OPERATION, stage="persistence", records=len(updates))
        try:
            applied = apply_updates(updates, connection_factory=connection_factory, reporter=reporter)
        except Exception as exc:
            emit(reporter, "stage_failed", operation=OPERATION, stage="persistence", error=exc)
            raise
        emit(reporter, "stage_completed", operation=OPERATION, stage="persistence", applied=applied)
    else:
        applied = 0

    messages = tuple(
        f"appid={row['appid']} week={row['week_date']}: {error}"
        for row, label, error in discovered if error is not None
    )
    for completed, (row, label, error) in enumerate(discovered, 1):
        outcome = "failed" if error else "applied" if args.apply else "proposed"
        emit(
            reporter, "candidate_completed", operation=OPERATION,
            completed=completed, total=len(discovered),
            identity=f"week={row['week_date']},appid={row['appid']}", outcome=outcome,
        )
    return UpdateResult(
        "repair rating-labels", target, proposed=len(updates), applied=applied,
        failed=sum(error is not None for _, _, error in discovered), messages=messages,
    )
