"""Discover and optionally apply missing historical prices and discounts."""

from __future__ import annotations

import asyncio

import db
from workflow_clients import RealExtractionClients

from ..common import UpdateResult
from .common import add_target_arguments, persistence_progress, require_apply_bound, unit_completed, unit_started
from workflow_progress import emit

COMMAND = "prices"


def find_candidates(*, week=None, appid=None, limit=None, connection_factory=None):
    """Select incomplete prices with operation-owned SQL and bounded filters."""
    clauses = ["(price IS NULL OR discount IS NULL)"]
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
    """Fill missing price components in one operation-owned transaction."""
    rows = list(updates)
    if not rows:
        return 0
    connection = (connection_factory or db.get_connection)()
    try:
        applied = 0
        with connection.cursor() as cursor:
            for completed, row in enumerate(rows, 1):
                cursor.execute(
                    "UPDATE weeksheet SET price = COALESCE(price, %s), "
                    "discount = COALESCE(discount, %s) WHERE week_date = %s "
                    "AND game_id = %s AND (price IS NULL OR discount IS NULL);",
                    (
                        row.get("price"), row.get("discount"),
                        row["week_date"], row["appid"],
                    ),
                )
                applied += max(cursor.rowcount, 0)
                persistence_progress(
                    reporter, "repair_prices",
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
    """Resolve prices concurrently, using Steam for incomplete ITAD data.

    A failed shared ITAD identifier lookup marks every candidate failed;
    per-candidate history or Steam failures remain isolated to that row.
    """
    appids = list(dict.fromkeys(row["appid"] for row in candidates))
    unit_started(reporter, "repair_prices", "itad_lookup", f"appids={len(appids)}", total=len(appids))
    try:
        mappings = await clients.itad_lookup(appids)
    except Exception as exc:
        unit_completed(reporter, "repair_prices", "itad_lookup", f"appids={len(appids)}",
                       "failed", completed=0, total=len(appids), error=exc)
        results = []
        for completed, row in enumerate(candidates, 1):
            identity = f"week={row['week_date']},appid={row['appid']}"
            unit_completed(reporter, "repair_prices", "candidate", identity, "failed",
                           completed=completed, total=len(candidates), error=exc)
            emit(reporter, "candidate_discovered", completed=completed, total=len(candidates),
                 operation="repair_prices", identity=identity)
            results.append((row, None, None, str(exc)))
        return results
    unit_completed(reporter, "repair_prices", "itad_lookup", f"appids={len(appids)}",
                   "completed", completed=len(appids), total=len(appids))

    completed = 0
    total = len(candidates)

    async def one(row):
        """Combine ITAD history and Steam fallback values for one candidate."""
        nonlocal completed
        identity = f"week={row['week_date']},appid={row['appid']}"
        active_phase = None
        try:
            price = discount = None
            itad_id = mappings.get(row["appid"])
            if itad_id:
                active_phase = "itad_history"
                unit_started(reporter, "repair_prices", "itad_history", identity, total=total)
                price, discount = await clients.itad_history(itad_id, str(row["week_date"]))
                unit_completed(reporter, "repair_prices", "itad_history", identity, "completed")
                active_phase = None
            if price is None or discount is None:
                # Preserve either ITAD component while filling only what is absent.
                active_phase = "steam_fallback"
                unit_started(reporter, "repair_prices", "steam_fallback", identity, total=total)
                store = await clients.steam_html(row["appid"])
                unit_completed(reporter, "repair_prices", "steam_fallback", identity, "completed")
                active_phase = None
                if price is None: price = store.price
                if discount is None: discount = store.discount
            result = row, price, discount, None
            outcome = "completed" if price is not None or discount is not None else "unavailable"
        except Exception as exc:
            if active_phase:
                unit_completed(reporter, "repair_prices", active_phase, identity, "failed", error=exc)
            result = row, None, None, str(exc)
            outcome = "failed"
        completed += 1
        unit_completed(reporter, "repair_prices", "candidate", identity, outcome,
                       completed=completed, total=total, error=result[3])
        emit(reporter, "candidate_discovered", completed=completed, total=total,
             operation="repair_prices", identity=f"week={row['week_date']},appid={row['appid']}")
        return result
    return await asyncio.gather(*(one(row) for row in candidates))


def register_parser(subparsers):
    """Register bounded price-repair arguments."""
    parser = subparsers.add_parser(COMMAND, help="Repair missing historical prices")
    add_target_arguments(parser)
    parser.set_defaults(handler=run)


def run(args, dependencies=None):
    """Discover price repairs and persist them only when explicitly applied."""
    dependencies = dependencies or {}
    connection_factory = dependencies.get("connection_factory") or db.get_connection
    clients = dependencies.get("clients") or RealExtractionClients()
    reporter = dependencies.get("reporter")
    target = require_apply_bound(args)
    emit(reporter, "stage_started", operation="repair_prices", stage="discovery", target=target)
    try:
        candidates = find_candidates(
            week=args.week, appid=args.appid, limit=args.limit,
            connection_factory=connection_factory,
        )
    except Exception as exc:
        emit(reporter, "stage_failed", operation="repair_prices", stage="discovery", error=exc)
        raise
    emit(reporter, "stage_completed", operation="repair_prices", stage="discovery", total=len(candidates))
    emit(reporter, "stage_started", operation="repair_prices", stage="external_lookup", total=len(candidates))
    try:
        discovered = asyncio.run(discover(candidates, clients, reporter))
    except Exception as exc:
        emit(reporter, "stage_failed", operation="repair_prices", stage="external_lookup", error=exc)
        raise
    emit(reporter, "stage_completed", operation="repair_prices", stage="external_lookup", total=len(candidates))
    updates = [
        {"week_date": str(row["week_date"]), "appid": row["appid"], "price": price, "discount": discount}
        for row, price, discount, error in discovered
        if error is None and (price is not None or discount is not None)
    ]
    messages = tuple(
        f"appid={row['appid']} week={row['week_date']}: {error or 'price unavailable'}"
        for row, price, discount, error in discovered
        if error is not None or (price is None and discount is None)
    )
    if args.apply and updates:
        emit(reporter, "stage_started", operation="repair_prices", stage="persistence", records=len(updates))
        try:
            applied = apply_updates(updates, connection_factory=connection_factory, reporter=reporter)
        except Exception as exc:
            emit(reporter, "stage_failed", operation="repair_prices", stage="persistence", error=exc)
            raise
        emit(reporter, "stage_completed", operation="repair_prices", stage="persistence", applied=applied)
    else:
        applied = 0
    for completed, (row, price, discount, error) in enumerate(discovered, 1):
        unavailable = price is None and discount is None
        outcome = "failed" if error is not None else "skipped" if unavailable else (
            "applied" if args.apply and applied == len(updates) else "proposed"
        )
        emit(reporter, "candidate_completed", completed=completed, total=len(discovered),
             operation="repair_prices", identity=f"week={row['week_date']},appid={row['appid']}", outcome=outcome)
    return UpdateResult(
        "repair prices", target, proposed=len(updates), applied=applied,
        skipped=sum(error is None and price is None and discount is None for _, price, discount, error in discovered),
        failed=sum(error is not None for _, _, _, error in discovered), messages=messages,
    )
