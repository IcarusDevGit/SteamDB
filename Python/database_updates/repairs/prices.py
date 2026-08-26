"""Discover and optionally apply missing historical prices and discounts."""

from __future__ import annotations

import asyncio

import db
from workflow_clients import RealExtractionClients

from ..common import UpdateResult
from .common import add_target_arguments, require_apply_bound
from workflow_progress import emit

COMMAND = "prices"


async def discover(candidates, clients, reporter=None):
    appids = list(dict.fromkeys(row["appid"] for row in candidates))
    try:
        mappings = await clients.itad_lookup(appids)
    except Exception as exc:
        results = []
        for completed, row in enumerate(candidates, 1):
            emit(reporter, "candidate_discovered", completed=completed, total=len(candidates),
                 operation="repair_prices", identity=f"week={row['week_date']},appid={row['appid']}")
            results.append((row, None, None, str(exc)))
        return results

    completed = 0
    total = len(candidates)

    async def one(row):
        nonlocal completed
        try:
            price = discount = None
            itad_id = mappings.get(row["appid"])
            if itad_id:
                price, discount = await clients.itad_history(itad_id, str(row["week_date"]))
            if price is None or discount is None:
                store = await clients.steam_html(row["appid"])
                if price is None: price = store.price
                if discount is None: discount = store.discount
            result = row, price, discount, None
        except Exception as exc:
            result = row, None, None, str(exc)
        completed += 1
        emit(reporter, "candidate_discovered", completed=completed, total=total,
             operation="repair_prices", identity=f"week={row['week_date']},appid={row['appid']}")
        return result
    return await asyncio.gather(*(one(row) for row in candidates))


def register_parser(subparsers):
    parser = subparsers.add_parser(COMMAND, help="Repair missing historical prices")
    add_target_arguments(parser)
    parser.set_defaults(handler=run)


def run(args, dependencies=None):
    dependencies = dependencies or {}
    database = dependencies.get("database", db)
    clients = dependencies.get("clients") or RealExtractionClients()
    reporter = dependencies.get("reporter")
    target = require_apply_bound(args)
    emit(reporter, "stage_started", operation="repair_prices", stage="discovery", target=target)
    candidates = database.find_missing_prices(week=args.week, appid=args.appid, limit=args.limit)
    emit(reporter, "stage_completed", operation="repair_prices", stage="discovery", total=len(candidates))
    emit(reporter, "stage_started", operation="repair_prices", stage="external_lookup", total=len(candidates))
    discovered = asyncio.run(discover(candidates, clients, reporter))
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
            applied = database.apply_price_repairs(updates)
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
