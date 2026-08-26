"""Discover and optionally apply missing historical ratings."""

from __future__ import annotations

import asyncio

import db
from workflow_clients import RealExtractionClients

from ..common import UpdateResult
from .common import add_target_arguments, describe_target, require_apply_bound
from workflow_progress import emit

COMMAND = "ratings"


async def discover(candidates, clients, reporter=None):
    completed = 0
    total = len(candidates)

    async def one(row):
        nonlocal completed
        try:
            value = await clients.rating(row["appid"], str(row["week_date"]))
            result = row, value, None
        except Exception as exc:
            result = row, None, str(exc)
        completed += 1
        emit(reporter, "candidate_discovered", completed=completed, total=total,
             operation="repair_ratings", identity=f"week={row['week_date']},appid={row['appid']}")
        return result
    return await asyncio.gather(*(one(row) for row in candidates))


def register_parser(subparsers):
    parser = subparsers.add_parser(COMMAND, help="Repair missing historical ratings")
    add_target_arguments(parser)
    parser.set_defaults(handler=run)


def run(args, dependencies=None):
    dependencies = dependencies or {}
    database = dependencies.get("database", db)
    clients = dependencies.get("clients") or RealExtractionClients()
    reporter = dependencies.get("reporter")
    target = require_apply_bound(args)
    emit(reporter, "stage_started", operation="repair_ratings", stage="discovery", target=target)
    candidates = database.find_missing_ratings(week=args.week, appid=args.appid, limit=args.limit)
    emit(reporter, "stage_completed", operation="repair_ratings", stage="discovery", total=len(candidates))
    emit(reporter, "stage_started", operation="repair_ratings", stage="external_lookup", total=len(candidates))
    discovered = asyncio.run(discover(candidates, clients, reporter))
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
            applied = database.apply_rating_repairs(updates)
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
