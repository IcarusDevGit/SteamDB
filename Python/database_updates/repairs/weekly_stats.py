"""Discover and optionally apply weekly rank metadata from the Steam chart."""

from __future__ import annotations

import asyncio

import db
from workflow_clients import RealExtractionClients

from ..common import UpdateResult
from .common import positive_int, valid_week
from workflow_progress import emit

COMMAND = "weekly-stats"


def register_parser(subparsers):
    parser = subparsers.add_parser(COMMAND, help="Repair last-week rank and consecutive-week values")
    parser.add_argument("--week", type=valid_week, required=True)
    parser.add_argument("--limit", type=positive_int)
    parser.add_argument("--field", choices=("all", "last-week-rank", "consecutive-weeks"), default="all")
    parser.add_argument("--apply", action="store_true", help="Apply validated repairs; default is dry-run")
    parser.set_defaults(handler=run)


def run(args, dependencies=None):
    dependencies = dependencies or {}
    database = dependencies.get("database", db)
    clients = dependencies.get("clients") or RealExtractionClients()
    reporter = dependencies.get("reporter")
    target = f"week={args.week}" + (f",limit={args.limit}" if args.limit else "")
    emit(reporter, "stage_started", operation="repair_weekly_stats", stage="external_lookup", target=target)
    try:
        rows = asyncio.run(clients.weekly(args.week))
    except Exception as exc:
        emit(reporter, "stage_failed", operation="repair_weekly_stats", stage="external_lookup", error=exc)
        raise
    if args.limit:
        rows = rows[:args.limit]
    emit(reporter, "stage_completed", operation="repair_weekly_stats", stage="external_lookup", total=len(rows))
    updates = []
    for row in rows:
        update = {"week_date": args.week, "rank": row["rank"]}
        if args.field in ("all", "last-week-rank"):
            update["last_week_rank"] = row.get("last_week_rank")
        if args.field in ("all", "consecutive-weeks"):
            update["consecutive_weeks"] = row.get("consecutive_weeks")
        updates.append(update)
    if args.apply and updates:
        emit(reporter, "stage_started", operation="repair_weekly_stats", stage="persistence", records=len(updates))
        try:
            applied = database.apply_weekly_stat_repairs(updates)
        except Exception as exc:
            emit(reporter, "stage_failed", operation="repair_weekly_stats", stage="persistence", error=exc)
            raise
        emit(reporter, "stage_completed", operation="repair_weekly_stats", stage="persistence", applied=applied)
    else:
        applied = 0
    for completed, update in enumerate(updates, 1):
        emit(
            reporter, "candidate_completed", completed=completed, total=len(updates),
            operation="repair_weekly_stats", identity=f"week={args.week},rank={update['rank']}",
            outcome="applied" if args.apply and applied == len(updates) else "proposed",
        )
    return UpdateResult(
        "repair weekly-stats", target,
        proposed=len(updates), applied=applied,
    )
