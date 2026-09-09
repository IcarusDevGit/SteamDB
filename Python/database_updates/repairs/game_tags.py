"""Discover and optionally repair empty catalog game tags from Steam HTML."""

from __future__ import annotations

import asyncio

import db
from tag_resolution import load_exceptions, resolve_tags
from workflow_clients import RealExtractionClients
from workflow_progress import emit

from ..common import UpdateResult
from .common import persistence_progress, positive_int, unit_completed, unit_started

COMMAND = "game-tags"
EMPTY_TAGS_SQL = "COALESCE(cardinality(tags), 0) = 0"


def find_candidates(*, appid=None, limit=None, connection_factory=None):
    """Select null or empty-tag games, optionally narrowed by ID or count."""
    query = f"SELECT id FROM games WHERE {EMPTY_TAGS_SQL}"
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
            return [{"appid": int(row[0])} for row in cursor.fetchall()]
    finally:
        connection.close()


def load_tags_by_name(*, connection_factory=None):
    """Load one canonical tag-name mapping for deterministic resolution."""
    connection = (connection_factory or db.get_connection)()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name FROM tags", ())
            return {str(name): int(tag_id) for tag_id, name in cursor.fetchall()}
    finally:
        connection.close()


def apply_updates(updates, *, connection_factory=None, reporter=None):
    """Atomically fill selected tag arrays while they remain empty."""
    rows = list(updates)
    if not rows:
        return 0
    connection = (connection_factory or db.get_connection)()
    try:
        applied = 0
        with connection.cursor() as cursor:
            for completed, row in enumerate(rows, 1):
                cursor.execute(
                    f"UPDATE games SET tags = %s WHERE id = %s AND {EMPTY_TAGS_SQL};",
                    (list(row["tag_ids"]), row["appid"]),
                )
                applied += max(cursor.rowcount, 0)
                persistence_progress(
                    reporter, "repair_game_tags", f"appid={row['appid']}",
                    completed, len(rows),
                )
        connection.commit()
        return applied
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


async def discover(candidates, clients, tags_by_name, *, exceptions=None, reporter=None):
    """Resolve Steam HTML tags concurrently while isolating game failures."""
    completed = 0
    total = len(candidates)
    aliases = exceptions if exceptions is not None else load_exceptions()
    canonical_by_id = {int(tag_id): name for name, tag_id in tags_by_name.items()}

    async def one(row):
        nonlocal completed
        identity = f"appid={row['appid']}"
        unit_started(reporter, "repair_game_tags", "steam_html", identity, total=total)
        try:
            store_data = await clients.steam_html(row["appid"])
            resolution = resolve_tags(
                store_data.tags, tags_by_name, exceptions=aliases,
                canonical_by_id=canonical_by_id,
            )
            result = row, resolution, None
            outcome = "completed" if resolution.ids else "unavailable"
        except Exception as exc:
            result = row, None, str(exc)
            outcome = "failed"
        completed += 1
        unit_completed(
            reporter, "repair_game_tags", "steam_html", identity, outcome,
            completed=completed, total=total, error=result[2],
        )
        emit(
            reporter, "candidate_discovered", completed=completed, total=total,
            operation="repair_game_tags", identity=identity,
        )
        return result

    return await asyncio.gather(*(one(row) for row in candidates))


def register_parser(subparsers):
    """Register empty-game-tag repair with optional narrowing controls."""
    parser = subparsers.add_parser(COMMAND, help="Repair empty game tags from Steam HTML")
    parser.add_argument("--appid", type=positive_int, help="limit candidates to this positive Steam app ID")
    parser.add_argument("--limit", type=positive_int, help="maximum number of candidates to inspect")
    parser.add_argument("--apply", action="store_true", help="Apply resolved tags; default is dry-run")
    parser.set_defaults(handler=run)


def _target(args):
    parts = []
    if args.appid:
        parts.append(f"appid={args.appid}")
    if args.limit:
        parts.append(f"limit={args.limit}")
    return ",".join(parts) or "empty-tags"


def run(args, dependencies=None):
    """Discover Steam tags and persist resolved IDs with explicit authorization."""
    dependencies = dependencies or {}
    connection_factory = dependencies.get("connection_factory") or db.get_connection
    clients = dependencies.get("clients") or RealExtractionClients()
    reporter = dependencies.get("reporter")
    snapshot = dependencies.get("snapshot")
    target = _target(args)

    emit(reporter, "stage_started", operation="repair_game_tags", stage="discovery", target=target)
    try:
        candidates = find_candidates(
            appid=args.appid, limit=args.limit, connection_factory=connection_factory,
        )
        tags_by_name = (
            dict(snapshot.get("tags_by_name", {})) if snapshot is not None
            else load_tags_by_name(connection_factory=connection_factory)
        )
    except Exception as exc:
        emit(reporter, "stage_failed", operation="repair_game_tags", stage="discovery", error=exc)
        raise
    emit(reporter, "stage_completed", operation="repair_game_tags", stage="discovery", total=len(candidates))

    emit(reporter, "stage_started", operation="repair_game_tags", stage="external_lookup", total=len(candidates))
    try:
        discovered = asyncio.run(discover(
            candidates, clients, tags_by_name,
            exceptions=dependencies.get("exceptions"), reporter=reporter,
        ))
    except Exception as exc:
        emit(reporter, "stage_failed", operation="repair_game_tags", stage="external_lookup", error=exc)
        raise
    emit(reporter, "stage_completed", operation="repair_game_tags", stage="external_lookup", total=len(candidates))

    updates = [
        {"appid": row["appid"], "tag_ids": list(resolution.ids)}
        for row, resolution, error in discovered
        if error is None and resolution is not None and resolution.ids
    ]
    messages = []
    for row, resolution, error in discovered:
        if error:
            messages.append(f"appid={row['appid']}: {error}")
        elif resolution.unresolved:
            messages.append(
                f"appid={row['appid']}: unresolved tags: {', '.join(resolution.unresolved)}"
            )
        if resolution is not None and not resolution.ids and not resolution.unresolved:
            messages.append(f"appid={row['appid']}: tags unavailable")

    if args.apply and updates:
        emit(reporter, "stage_started", operation="repair_game_tags", stage="persistence", records=len(updates))
        try:
            applied = apply_updates(updates, connection_factory=connection_factory, reporter=reporter)
        except Exception as exc:
            emit(reporter, "stage_failed", operation="repair_game_tags", stage="persistence", error=exc)
            raise
        emit(reporter, "stage_completed", operation="repair_game_tags", stage="persistence", applied=applied)
    else:
        applied = 0

    for completed, (row, resolution, error) in enumerate(discovered, 1):
        applicable = resolution is not None and bool(resolution.ids)
        outcome = "failed" if error else "skipped" if not applicable else "applied" if args.apply else "proposed"
        emit(
            reporter, "candidate_completed", completed=completed, total=len(discovered),
            operation="repair_game_tags", identity=f"appid={row['appid']}", outcome=outcome,
        )
    return UpdateResult(
        "repair game-tags", target, proposed=len(updates), applied=applied,
        skipped=sum(error is None and (resolution is None or not resolution.ids)
                    for _, resolution, error in discovered),
        failed=sum(error is not None for _, _, error in discovered),
        messages=tuple(messages),
    )
