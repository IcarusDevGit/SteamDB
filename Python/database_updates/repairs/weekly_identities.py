"""Compare and optionally reconcile stored weeks with Steam's global Top 100."""

from __future__ import annotations

from dataclasses import dataclass

import db
from ValidateEntries import GlobalChartFetcher
from workflow_progress import emit

from ..common import UpdateResult
from .common import valid_week

COMMAND = "weekly-identities"


@dataclass(frozen=True, slots=True)
class WeekPlan:
    week: str
    rows: tuple[dict, ...]
    missing: tuple[tuple[int, int], ...]
    unexpected: tuple[tuple[int, int], ...]
    moved: tuple[tuple[int, int, int], ...]
    unchanged: int

    @property
    def changed(self):
        return bool(self.missing or self.unexpected or self.moved)


def load_state(*, week=None, connection_factory=None):
    """Read selected stored weeks and catalog IDs using operation-owned SQL."""
    connection = (connection_factory or db.get_connection)()
    try:
        with connection.cursor() as cursor:
            query = (
                "SELECT week_date, rank, game_id, price, discount, rating, rating_label "
                "FROM weeksheet"
            )
            params = ()
            if week:
                query += " WHERE week_date = %s"
                params = (week,)
            query += " ORDER BY week_date, rank"
            cursor.execute(query, params)
            records = cursor.fetchall()
            cursor.execute("SELECT id FROM games", ())
            catalog_ids = {row[0] for row in cursor.fetchall()}
        grouped = {}
        for week_date, rank, appid, price, discount, rating, rating_label in records:
            grouped.setdefault(str(week_date), []).append({
                "rank": rank, "appid": appid, "price": price,
                "discount": discount, "rating": rating, "rating_label": rating_label,
            })
        if week and not grouped:
            raise ValueError(f"weeksheet has no entries for week {week}")
        return grouped, catalog_ids
    finally:
        connection.close()


def build_plan(week, stored_rows, global_rows, catalog_ids):
    """Build deterministic identity differences and a complete replacement set."""
    stored_by_app = {row["appid"]: row for row in stored_rows}
    if len(stored_by_app) != len(stored_rows) or len({row["rank"] for row in stored_rows}) != len(stored_rows):
        raise ValueError(f"stored week {week} contains duplicate identities")
    expected_by_app = {row["appid"]: row for row in global_rows}
    missing = tuple((row["rank"], row["appid"]) for row in global_rows if row["appid"] not in stored_by_app)
    unexpected = tuple((row["rank"], row["appid"]) for row in stored_rows if row["appid"] not in expected_by_app)
    moved = tuple(
        (appid, stored_by_app[appid]["rank"], expected_by_app[appid]["rank"])
        for appid in sorted(set(stored_by_app) & set(expected_by_app))
        if stored_by_app[appid]["rank"] != expected_by_app[appid]["rank"]
    )
    unchanged = sum(
        stored_by_app[appid]["rank"] == expected_by_app[appid]["rank"]
        for appid in set(stored_by_app) & set(expected_by_app)
    )
    rows = []
    for expected in global_rows:
        current = stored_by_app.get(expected["appid"])
        if expected["appid"] not in catalog_ids and not expected.get("name", "").strip():
            raise ValueError(f"global game {expected['appid']} has no usable name for catalog insertion")
        rows.append({
            "week_date": week, "rank": expected["rank"], "appid": expected["appid"],
            "name": expected.get("name", "").strip(),
            "last_week_rank": expected.get("last_week_rank"),
            "consecutive_weeks": expected.get("consecutive_weeks"),
            "price": current.get("price") if current else None,
            "discount": current.get("discount") if current else None,
            "rating": current.get("rating") if current else None,
            "rating_label": current.get("rating_label") if current else None,
        })
    return WeekPlan(str(week), tuple(rows), missing, unexpected, moved, unchanged)


def apply_plans(plans, *, connection_factory=None, reporter=None):
    """Reconcile every changed week in one operation-owned transaction."""
    changed = [plan for plan in plans if plan.changed]
    if not changed:
        return 0
    connection = (connection_factory or db.get_connection)()
    try:
        with connection.cursor() as cursor:
            for completed, plan in enumerate(changed, 1):
                for row in plan.rows:
                    cursor.execute(
                        "INSERT INTO games (id, name, tags) VALUES (%s, %s, %s) "
                        "ON CONFLICT (id) DO NOTHING;",
                        (row["appid"], row["name"], []),
                    )
                emit(
                    reporter, "persistence_progress", operation="repair_weekly_identities",
                    phase="catalog", completed=completed, total=len(changed),
                    identity=f"week={plan.week}",
                )
            for completed, plan in enumerate(changed, 1):
                appids = [row["appid"] for row in plan.rows]
                cursor.execute(
                    "DELETE FROM weeksheet WHERE week_date = %s AND NOT (game_id = ANY(%s));",
                    (plan.week, appids),
                )
                cursor.execute(
                    "UPDATE weeksheet SET rank = rank + 1000000 WHERE week_date = %s;",
                    (plan.week,),
                )
                for row in plan.rows:
                    cursor.execute(
                        "INSERT INTO weeksheet "
                        "(week_date, rank, game_id, price, discount, rating, rating_label, last_week_rank, consecutive_weeks) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (week_date, game_id) DO UPDATE SET "
                        "rank = EXCLUDED.rank, price = EXCLUDED.price, discount = EXCLUDED.discount, "
                        "rating = EXCLUDED.rating, rating_label = EXCLUDED.rating_label, last_week_rank = EXCLUDED.last_week_rank, "
                        "consecutive_weeks = EXCLUDED.consecutive_weeks;",
                        (
                            row["week_date"], row["rank"], row["appid"], row["price"],
                            row["discount"], row["rating"], row.get("rating_label"), row["last_week_rank"],
                            row["consecutive_weeks"],
                        ),
                    )
                emit(
                    reporter, "persistence_progress", operation="repair_weekly_identities",
                    phase="weekly_reconciliation", completed=completed, total=len(changed),
                    identity=f"week={plan.week}",
                )
        connection.commit()
        return len(changed)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def register_parser(subparsers):
    parser = subparsers.add_parser(COMMAND, help="Reconcile stored weeks with the global Top 100")
    parser.add_argument("--week", type=valid_week, help="limit repair to this stored Tuesday")
    parser.add_argument("--apply", action="store_true", help="Apply validated reconciliation; default is dry-run")
    parser.set_defaults(handler=run)


def run(args, dependencies=None):
    dependencies = dependencies or {}
    connection_factory = dependencies.get("connection_factory") or db.get_connection
    reporter = dependencies.get("reporter")
    fetcher = dependencies.get("global_chart_fetcher") or GlobalChartFetcher(reporter=reporter)
    target = f"week={args.week}" if args.week else "all-stored-weeks"
    emit(reporter, "stage_started", operation="repair_weekly_identities", stage="discovery", target=target)
    try:
        stored, catalog_ids = load_state(week=args.week, connection_factory=connection_factory)
    except Exception as exc:
        emit(reporter, "stage_failed", operation="repair_weekly_identities", stage="discovery", error=exc)
        raise
    plans = []
    for completed, (week, rows) in enumerate(sorted(stored.items()), 1):
        try:
            _, global_rows = fetcher(week)
            plan = build_plan(week, rows, global_rows, catalog_ids)
        except Exception as exc:
            emit(reporter, "unit_completed", operation="repair_weekly_identities",
                 phase="week_validation", identity=f"week={week}", outcome="failed", error=exc)
            emit(reporter, "stage_failed", operation="repair_weekly_identities", stage="discovery", error=exc)
            raise
        plans.append(plan)
        emit(reporter, "candidate_discovered", operation="repair_weekly_identities", completed=completed,
             total=len(stored), identity=f"week={week}")
    emit(reporter, "stage_completed", operation="repair_weekly_identities", stage="discovery", total=len(plans))
    changed = [plan for plan in plans if plan.changed]
    if args.apply and changed:
        emit(reporter, "stage_started", operation="repair_weekly_identities", stage="persistence", records=len(changed))
        applied = apply_plans(
            changed, connection_factory=connection_factory, reporter=reporter,
        )
        emit(reporter, "stage_completed", operation="repair_weekly_identities", stage="persistence", applied=applied)
    else:
        applied = 0
    messages = []
    for completed, plan in enumerate(plans, 1):
        messages.append(
            f"week={plan.week} missing={len(plan.missing)} unexpected={len(plan.unexpected)} "
            f"moved={len(plan.moved)} unchanged={plan.unchanged}"
        )
        outcome = "applied" if args.apply and plan.changed else "proposed" if plan.changed else "skipped"
        emit(reporter, "candidate_completed", operation="repair_weekly_identities", completed=completed,
             total=len(plans), identity=f"week={plan.week}", outcome=outcome)
    return UpdateResult(
        "repair weekly-identities", target, proposed=len(changed), applied=applied,
        skipped=len(plans) - len(changed), messages=tuple(messages),
    )
