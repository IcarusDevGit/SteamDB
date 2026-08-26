"""Parse, validate, and atomically apply an operator-approved extraction CSV."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

import db

from .common import UpdateResult
from workflow_progress import Reporter, emit


COMMAND = "csv"
REQUIRED_FIELDS = {
    "week_date", "rank", "appid", "name", "tags", "tag_ids",
    "unresolved_tags", "rating", "price", "discount",
    "last_week_rank", "consecutive_weeks", "errors",
}


def _optional_number(value, cast, *, field, line):
    if value in (None, ""):
        return None
    try:
        return cast(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"line {line} has invalid {field}: {value!r}") from exc


def _bounded(value, *, field, line, minimum=None, maximum=None):
    if value is None:
        return
    if minimum is not None and value < minimum:
        raise ValueError(f"line {line} {field} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"line {line} {field} must be at most {maximum}")


def load_validated_csv(filepath: str | Path) -> list[dict]:
    path = Path(filepath)
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or ())
        missing = sorted(REQUIRED_FIELDS - headers)
        if missing:
            raise ValueError(f"missing required CSV fields: {', '.join(missing)}")
        raw_rows = list(reader)
    if not raw_rows:
        raise ValueError("approved CSV contains no records")

    records = []
    week_ranks = set()
    week_games = set()
    for line, row in enumerate(raw_rows, 2):
        try:
            week = date.fromisoformat(row["week_date"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"line {line} has invalid week_date") from exc
        if week.weekday() != 1:
            raise ValueError(f"line {line} week_date is not a Tuesday")
        rank = _optional_number(row["rank"], int, field="rank", line=line)
        appid = _optional_number(row["appid"], int, field="appid", line=line)
        if rank is None or appid is None:
            raise ValueError(f"line {line} requires rank and appid")
        _bounded(rank, field="rank", line=line, minimum=1, maximum=100)
        _bounded(appid, field="appid", line=line, minimum=1)
        if not row.get("name", "").strip():
            raise ValueError(f"line {line} has an empty game name")
        identity_rank = (week.isoformat(), rank)
        identity_game = (week.isoformat(), appid)
        if identity_rank in week_ranks:
            raise ValueError(f"line {line} duplicates week/rank {identity_rank}")
        if identity_game in week_games:
            raise ValueError(f"line {line} duplicates week/game {identity_game}")
        week_ranks.add(identity_rank)
        week_games.add(identity_game)

        unresolved = [value.strip() for value in row["unresolved_tags"].split(",") if value.strip()]
        if unresolved:
            raise ValueError(f"line {line} has unresolved tags: {', '.join(unresolved)}")
        if row["errors"].strip():
            raise ValueError(f"line {line} has unacknowledged extraction errors: {row['errors'].strip()}")
        try:
            tag_ids = [int(value) for value in row["tag_ids"].split(",") if value.strip()]
        except ValueError as exc:
            raise ValueError(f"line {line} has an invalid tag id") from exc
        tag_names = [value.strip() for value in row["tags"].split(",") if value.strip()]
        if len(tag_ids) != len(tag_names):
            raise ValueError(f"line {line} has mismatched tag ids and names")
        if len(set(tag_ids)) != len(tag_ids) or len(set(tag_names)) != len(tag_names):
            raise ValueError(f"line {line} contains duplicate tags")
        if any(value <= 0 for value in tag_ids):
            raise ValueError(f"line {line} has a non-positive tag id")

        rating = _optional_number(row["rating"], float, field="rating", line=line)
        price = _optional_number(row["price"], float, field="price", line=line)
        discount = _optional_number(row["discount"], int, field="discount", line=line)
        last_week_rank = _optional_number(row["last_week_rank"], int, field="last_week_rank", line=line)
        consecutive = _optional_number(row["consecutive_weeks"], int, field="consecutive_weeks", line=line)
        _bounded(rating, field="rating", line=line, minimum=0, maximum=1)
        _bounded(price, field="price", line=line, minimum=0)
        _bounded(discount, field="discount", line=line, minimum=0, maximum=100)
        _bounded(last_week_rank, field="last_week_rank", line=line, minimum=0)
        _bounded(consecutive, field="consecutive_weeks", line=line, minimum=1)
        records.append({
            "week_date": week.isoformat(), "rank": rank, "appid": appid,
            "name": row["name"].strip(), "tag_ids": tag_ids, "tag_names": tag_names,
            "rating": rating, "price": price, "discount": discount,
            "last_week_rank": last_week_rank, "consecutive_weeks": consecutive,
        })
    return records


def default_validation_report(filepath: str | Path) -> Path:
    path = Path(filepath)
    return path.with_name(f"{path.stem}.validation.json")


def _csv_weeks(filepath: str | Path) -> set[str]:
    with Path(filepath).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "week_date" not in set(reader.fieldnames or ()):
            raise ValueError("missing required CSV field: week_date")
        weeks = {row.get("week_date", "").strip() for row in reader}
    weeks.discard("")
    if len(weeks) != 1:
        raise ValueError("approved CSV must contain exactly one distinct week")
    return weeks


def verify_chart_evidence(filepath: str | Path, report_path: str | Path | None = None) -> Path:
    path = Path(filepath)
    report = Path(report_path) if report_path else default_validation_report(path)
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"chart validation report is missing: {report}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"chart validation report is malformed: {report}") from exc
    if payload.get("status") != "passed":
        raise ValueError("chart validation report status must be passed")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if payload.get("csv_sha256") != digest:
        raise ValueError("chart validation report digest does not match the CSV")
    weeks = _csv_weeks(path)
    report_week = (payload.get("weekly") or {}).get("week")
    if {report_week} != weeks:
        raise ValueError("chart validation report does not cover the CSV week")
    return report


def apply_csv(
    filepath: str | Path,
    *,
    approved: bool = False,
    report_path: str | Path | None = None,
    database=db,
    reporter: Reporter | None = None,
) -> int:
    if not approved:
        raise PermissionError("database update requires explicit --approved confirmation")
    emit(reporter, "stage_started", operation="apply_csv", stage="validation", target=filepath)
    try:
        verify_chart_evidence(filepath, report_path)
        records = load_validated_csv(filepath)
        unique_tags = len(db.prepare_tag_candidates(records))
    except Exception as exc:
        emit(reporter, "stage_failed", operation="apply_csv", stage="validation", error=exc)
        raise
    emit(
        reporter, "stage_completed", operation="apply_csv", stage="validation",
        records=len(records), unique_tags=unique_tags,
    )
    total = len(records)
    for completed, record in enumerate(records, 1):
        emit(
            reporter, "candidate_completed", completed=completed, total=total,
            operation="apply_csv", identity=f"week={record['week_date']},appid={record['appid']}",
            outcome="prepared",
        )
    emit(
        reporter, "stage_started", operation="apply_csv", stage="persistence",
        records=total, unique_tags=unique_tags,
    )
    try:
        applied = database.apply_validated_records(records)
    except Exception as exc:
        emit(
            reporter, "stage_failed", operation="apply_csv", stage="persistence",
            error=exc, records=total, unique_tags=unique_tags,
        )
        raise
    emit(
        reporter, "stage_completed", operation="apply_csv", stage="persistence",
        applied=applied, records=total, unique_tags=unique_tags,
    )
    return applied


def register_parser(subparsers):
    parser = subparsers.add_parser(COMMAND, help="Apply an operator-approved extraction CSV")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--validation-report", type=Path, help="override the adjacent validation report")
    parser.add_argument("--approved", action="store_true", help="Confirm the CSV was manually validated")
    parser.set_defaults(handler=run)


def run(args, dependencies=None):
    dependencies = dependencies or {}
    database = dependencies.get("database", db)
    count = apply_csv(
        args.csv,
        approved=args.approved,
        report_path=getattr(args, "validation_report", None),
        database=database,
        reporter=dependencies.get("reporter"),
    )
    return UpdateResult("apply csv", str(args.csv), proposed=count, applied=count)
