"""Discover and optionally refresh Steam game names across the catalog."""

from __future__ import annotations

import asyncio

import db
from workflow_clients import RealExtractionClients
from workflow_progress import emit

from ..common import UpdateResult
from .common import persistence_progress, positive_int, unit_completed, unit_started

COMMAND = "game-names"


def find_candidates(*, appid=None, limit=None, connection_factory=None):
    """Select whitespace-name games, optionally narrowed by ID or row limit."""
    query = "SELECT id, name FROM games WHERE BTRIM(name) = ''"
    params = []
    if appid:
        query += " AND id = %s"
        params.append(appid)
    query += " ORDER BY id"
    if limit:
        query += " LIMIT %s"
        params.append(limit)
    connection = (connection_factory or db.get_connection)()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            return [{"appid": row[0], "current_name": row[1]} for row in cursor.fetchall()]
    finally:
        connection.close()


def apply_updates(updates, *, connection_factory=None, reporter=None):
    """Replace selected catalog names atomically using operation-owned SQL."""
    rows = list(updates)
    if not rows:
        return 0
    connection = (connection_factory or db.get_connection)()
    try:
        applied = 0
        with connection.cursor() as cursor:
            for completed, row in enumerate(rows, 1):
                cursor.execute(
                    "UPDATE games SET name = %s WHERE id = %s AND BTRIM(name) = '';",
                    (row["name"], row["appid"]),
                )
                applied += max(cursor.rowcount, 0)
                persistence_progress(reporter, "repair_game_names", f"appid={row['appid']}", completed, len(rows))
        connection.commit()
        return applied
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


async def discover(candidates, clients, reporter=None):
    """Resolve candidate names concurrently and isolate per-game failures."""
    completed = 0
    total = len(candidates)

    async def one(row):
        nonlocal completed
        identity = f"appid={row['appid']}"
        unit_started(reporter, "repair_game_names", "steam_game_name", identity, total=total)
        try:
            value = await clients.game_name(row["appid"])
            name = str(value).strip() if value is not None else None
            result = row, name or None, None
            outcome = "completed" if name else "unavailable"
        except Exception as exc:
            result = row, None, str(exc)
            outcome = "failed"
        completed += 1
        unit_completed(reporter, "repair_game_names", "steam_game_name", identity, outcome,
                       completed=completed, total=total, error=result[2])
        emit(
            reporter, "candidate_discovered", completed=completed, total=total,
            operation="repair_game_names", identity=f"appid={row['appid']}",
        )
        return result

    return await asyncio.gather(*(one(row) for row in candidates))


def register_parser(subparsers):
    """Register whitespace-name repair with optional narrowing controls."""
    parser = subparsers.add_parser(COMMAND, help="Refresh Steam game names")
    parser.add_argument("--appid", type=positive_int, help="limit candidates to this positive Steam app ID")
    parser.add_argument("--limit", type=positive_int, help="maximum number of candidates to inspect")
    parser.add_argument("--apply", action="store_true", help="Apply validated names; default is dry-run")
    parser.set_defaults(handler=run)


def _target(args):
    parts = []
    if args.appid:
        parts.append(f"appid={args.appid}")
    if args.limit:
        parts.append(f"limit={args.limit}")
    return ",".join(parts) or "whitespace-names"


def run(args, dependencies=None):
    """Discover Steam names and persist them only with explicit authorization."""
    dependencies = dependencies or {}
    connection_factory = dependencies.get("connection_factory") or db.get_connection
    clients = dependencies.get("clients") or RealExtractionClients()
    reporter = dependencies.get("reporter")
    target = _target(args)
    emit(reporter, "stage_started", operation="repair_game_names", stage="discovery", target=target)
    try:
        candidates = find_candidates(
            appid=args.appid, limit=args.limit, connection_factory=connection_factory,
        )
    except Exception as exc:
        emit(reporter, "stage_failed", operation="repair_game_names", stage="discovery", error=exc)
        raise
    emit(reporter, "stage_completed", operation="repair_game_names", stage="discovery", total=len(candidates))
    emit(reporter, "stage_started", operation="repair_game_names", stage="external_lookup", total=len(candidates))
    try:
        discovered = asyncio.run(discover(candidates, clients, reporter))
    except Exception as exc:
        emit(reporter, "stage_failed", operation="repair_game_names", stage="external_lookup", error=exc)
        raise
    emit(reporter, "stage_completed", operation="repair_game_names", stage="external_lookup", total=len(candidates))
    updates = [
        {"appid": row["appid"], "name": name}
        for row, name, error in discovered if name is not None and error is None
    ]
    messages = tuple(
        f"appid={row['appid']}: {error or 'name unavailable'}"
        for row, name, error in discovered if name is None
    )
    if args.apply and updates:
        emit(reporter, "stage_started", operation="repair_game_names", stage="persistence", records=len(updates))
        try:
            applied = apply_updates(updates, connection_factory=connection_factory, reporter=reporter)
        except Exception as exc:
            emit(reporter, "stage_failed", operation="repair_game_names", stage="persistence", error=exc)
            raise
        emit(reporter, "stage_completed", operation="repair_game_names", stage="persistence", applied=applied)
    else:
        applied = 0
    for completed, (row, name, error) in enumerate(discovered, 1):
        outcome = "failed" if error is not None else "skipped" if name is None else (
            "applied" if args.apply and applied == len(updates) else "proposed"
        )
        emit(
            reporter, "candidate_completed", completed=completed, total=len(discovered),
            operation="repair_game_names", identity=f"appid={row['appid']}", outcome=outcome,
        )
    return UpdateResult(
        "repair game-names", target, proposed=len(updates), applied=applied,
        skipped=sum(name is None and error is None for _, name, error in discovered),
        failed=sum(error is not None for _, _, error in discovered), messages=messages,
    )
