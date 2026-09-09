"""Discover and optionally apply missing historical ratings."""

from __future__ import annotations

import asyncio

import db
from workflow_clients import RealExtractionClients
from workflow_models import HistoricalRating

from ..common import UpdateResult
from .common import add_target_arguments, persistence_progress, require_apply_bound, unit_completed, unit_started
from workflow_progress import emit

COMMAND = "ratings"


def find_candidates(*, week=None, appid=None, limit=None, connection_factory=None):
    """Select missing ratings with operation-owned SQL and bounded filters."""
    clauses = ["rating IS NULL"]
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
    connection = (connection_factory or db.get_connection)()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            return [{"appid": row[0], "week_date": row[1]} for row in cursor.fetchall()]
    finally:
        connection.close()


def apply_updates(updates, *, connection_factory=None, reporter=None):
    """Fill missing ratings in one operation-owned transaction."""
    rows = list(updates)
    if not rows:
        return 0
    connection = (connection_factory or db.get_connection)()
    try:
        applied = 0
        with connection.cursor() as cursor:
            for completed, row in enumerate(rows, 1):
                cursor.execute(
                    "UPDATE weeksheet SET rating = %s "
                    "WHERE week_date = %s AND game_id = %s AND rating IS NULL;",
                    (row["rating"], row["week_date"], row["appid"]),
                )
                applied += max(cursor.rowcount, 0)
                persistence_progress(
                    reporter, "repair_ratings",
                    f"week={row['week_date']},appid={row['appid']}", completed, len(rows),
                )
        connection.commit()
        return applied
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


async def discover(candidates, clients, reporter=None):
    """Fetch candidate ratings concurrently and isolate per-row failures."""
    completed = 0
    total = len(candidates)

    async def one(row):
        """Resolve one rating into a value-or-error discovery tuple."""
        nonlocal completed
        identity = f"week={row['week_date']},appid={row['appid']}"
        unit_started(reporter, "repair_ratings", "steam_rating", identity, total=total)
        try:
            value = await clients.rating(row["appid"], str(row["week_date"]))
            if isinstance(value, HistoricalRating):
                value = value.rating
            result = row, value, None
            outcome = "completed" if value is not None else "unavailable"
        except Exception as exc:
            result = row, None, str(exc)
            outcome = "failed"
        completed += 1
        unit_completed(reporter, "repair_ratings", "steam_rating", identity, outcome,
                       completed=completed, total=total, error=result[2])
        emit(reporter, "candidate_discovered", completed=completed, total=total,
             operation="repair_ratings", identity=f"week={row['week_date']},appid={row['appid']}")
        return result
    return await asyncio.gather(*(one(row) for row in candidates))


def register_parser(subparsers):
    """Register bounded rating-repair arguments."""
    parser = subparsers.add_parser(COMMAND, help="Repair missing historical ratings")
    add_target_arguments(parser)
    parser.set_defaults(handler=run)


def run(args, dependencies=None):
    """Discover rating repairs and persist them only when explicitly applied."""
    dependencies = dependencies or {}
    connection_factory = dependencies.get("connection_factory") or db.get_connection
    clients = dependencies.get("clients") or RealExtractionClients()
    reporter = dependencies.get("reporter")
    target = require_apply_bound(args)
    emit(reporter, "stage_started", operation="repair_ratings", stage="discovery", target=target)
    try:
        candidates = find_candidates(
            week=args.week, appid=args.appid, limit=args.limit,
            connection_factory=connection_factory,
        )
    except Exception as exc:
        emit(reporter, "stage_failed", operation="repair_ratings", stage="discovery", error=exc)
        raise
    emit(reporter, "stage_completed", operation="repair_ratings", stage="discovery", total=len(candidates))
    emit(reporter, "stage_started", operation="repair_ratings", stage="external_lookup", total=len(candidates))
    try:
        discovered = asyncio.run(discover(candidates, clients, reporter))
    except Exception as exc:
        emit(reporter, "stage_failed", operation="repair_ratings", stage="external_lookup", error=exc)
        raise
    emit(reporter, "stage_completed", operation="repair_ratings", stage="external_lookup", total=len(candidates))
    updates = [
        {"week_date": str(row["week_date"]), "appid": row["appid"], "rating": value}
        for row, value, error in discovered if value is not None and error is None
    ]
    messages = tuple(
        f"appid={row['appid']} week={row['week_date']}: {error or 'rating unavailable'}"
        for row, value, error in discovered if value is None
    )
    if args.apply and updates:
        emit(reporter, "stage_started", operation="repair_ratings", stage="persistence", records=len(updates))
        try:
            applied = apply_updates(updates, connection_factory=connection_factory, reporter=reporter)
        except Exception as exc:
            emit(reporter, "stage_failed", operation="repair_ratings", stage="persistence", error=exc)
            raise
        emit(reporter, "stage_completed", operation="repair_ratings", stage="persistence", applied=applied)
    else:
        applied = 0
    for completed, (row, value, error) in enumerate(discovered, 1):
        outcome = "failed" if error is not None else "skipped" if value is None else (
            "applied" if args.apply and applied == len(updates) else "proposed"
        )
        emit(reporter, "candidate_completed", completed=completed, total=len(discovered),
             operation="repair_ratings", identity=f"week={row['week_date']},appid={row['appid']}", outcome=outcome)
    return UpdateResult(
        "repair ratings", target, proposed=len(updates), applied=applied,
        skipped=sum(value is None and error is None for _, value, error in discovered),
        failed=sum(error is not None for _, _, error in discovered), messages=messages,
    )
