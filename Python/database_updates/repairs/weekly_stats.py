"""Discover and optionally apply weekly rank metadata from the Steam chart."""

from __future__ import annotations

import asyncio

import db
from workflow_clients import RealExtractionClients

from ..common import UpdateResult
from .common import persistence_progress, positive_int, unit_completed, unit_started, valid_week
from workflow_progress import emit

COMMAND = "weekly-stats"


def apply_updates(updates, *, connection_factory=None, reporter=None):
    """Persist weekly-stat variants in one operation-owned transaction."""
    rows = list(updates)
    if not rows:
        return 0
    connection = (connection_factory or db.get_connection)()
    try:
        applied = 0
        with connection.cursor() as cursor:
            for completed, row in enumerate(rows, 1):
                if "last_week_rank" in row and "consecutive_weeks" in row:
                    cursor.execute(
                        "UPDATE weeksheet SET last_week_rank = %s, consecutive_weeks = %s "
                        "WHERE week_date = %s AND rank = %s;",
                        (row["last_week_rank"], row["consecutive_weeks"], row["week_date"], row["rank"]),
                    )
                elif "last_week_rank" in row:
                    cursor.execute(
                        "UPDATE weeksheet SET last_week_rank = %s WHERE week_date = %s AND rank = %s;",
                        (row["last_week_rank"], row["week_date"], row["rank"]),
                    )
                else:
                    cursor.execute(
                        "UPDATE weeksheet SET consecutive_weeks = %s WHERE week_date = %s AND rank = %s;",
                        (row["consecutive_weeks"], row["week_date"], row["rank"]),
                    )
                applied += max(cursor.rowcount, 0)
                persistence_progress(
                    reporter, "repair_weekly_stats",
                    f"week={row['week_date']},rank={row['rank']}", completed, len(rows),
                )
        connection.commit()
        return applied
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def register_parser(subparsers):
    """Register a week-bounded repair for selectable chart-stat fields."""
    parser = subparsers.add_parser(COMMAND, help="Repair last-week rank and consecutive-week values")
    parser.add_argument("--week", type=valid_week, required=True, help="Tuesday chart week in YYYY-MM-DD form")
    parser.add_argument("--limit", type=positive_int, help="maximum number of chart rows to inspect")
    parser.add_argument("--field", choices=("all", "last-week-rank", "consecutive-weeks"), default="all", help="weekly-stat field to repair")
    parser.add_argument("--apply", action="store_true", help="Apply validated repairs; default is dry-run")
    parser.set_defaults(handler=run)


def run(args, dependencies=None):
    """Fetch weekly ranks and optionally persist selected historical fields."""
    dependencies = dependencies or {}
    connection_factory = dependencies.get("connection_factory") or db.get_connection
    clients = dependencies.get("clients") or RealExtractionClients()
    reporter = dependencies.get("reporter")
    target = f"week={args.week}" + (f",limit={args.limit}" if args.limit else "")
    emit(reporter, "stage_started", operation="repair_weekly_stats", stage="external_lookup", target=target)
    identity = f"week={args.week}"
    unit_started(reporter, "repair_weekly_stats", "steam_weekly_chart", identity, total=1)
    try:
        rows = asyncio.run(clients.weekly(args.week))
    except Exception as exc:
        unit_completed(reporter, "repair_weekly_stats", "steam_weekly_chart", identity,
                       "failed", completed=1, total=1, error=exc)
        emit(reporter, "stage_failed", operation="repair_weekly_stats", stage="external_lookup", error=exc)
        raise
    unit_completed(reporter, "repair_weekly_stats", "steam_weekly_chart", identity,
                   "completed", completed=1, total=1)
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
            applied = apply_updates(updates, connection_factory=connection_factory, reporter=reporter)
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
