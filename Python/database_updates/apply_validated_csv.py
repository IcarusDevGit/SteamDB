"""Parse, validate, and atomically apply an operator-approved extraction CSV."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import db

from .common import UpdateResult, merge_results
import workflow_paths
from workflow_progress import Reporter, emit


COMMAND = "csv"
REQUIRED_FIELDS = {
    "week_date", "rank", "appid", "name", "tags", "tag_ids",
    "unresolved_tags", "rating", "price", "discount",
    "last_week_rank", "consecutive_weeks", "errors",
}


def _optional_number(value, cast, *, field, line):
    """Convert an optional CSV value and attach field/line context to errors."""
    if value in (None, ""):
        return None
    try:
        return cast(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"line {line} has invalid {field}: {value!r}") from exc


def _bounded(value, *, field, line, minimum=None, maximum=None):
    """Reject a present numeric value outside its inclusive semantic bounds."""
    if value is None:
        return
    if minimum is not None and value < minimum:
        raise ValueError(f"line {line} {field} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"line {line} {field} must be at most {maximum}")


def load_validated_csv(filepath: str | Path) -> list[dict]:
    """Parse and semantically validate an operator-reviewed extraction CSV.

    The returned records are normalized for persistence. Invalid structure,
    identities, unresolved data, extraction errors, or numeric ranges raise
    ``ValueError`` before a database connection is required.
    """
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

    # Cross-row identity sets enforce one game and one rank per chart week.
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
    """Derive the expected adjacent chart-evidence sidecar path."""
    path = Path(filepath)
    return path.with_name(f"{path.stem}.validation.json")


def _csv_weeks(filepath: str | Path) -> set[str]:
    """Return the CSV's sole non-empty week or reject mixed-week input."""
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
    """Verify passed, digest-matched evidence for exactly the CSV's week."""
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
    """Apply an explicitly approved and evidence-backed CSV atomically.

    Validation and tag-consistency checks finish before the database boundary;
    persistence errors propagate after a failed progress event is emitted.
    """
    if not approved:
        raise PermissionError("database update requires explicit --approved confirmation")
    emit(reporter, "stage_started", operation="apply_csv", stage="validation", target=filepath)
    try:
        verify_chart_evidence(filepath, report_path)
        records = load_validated_csv(filepath)
        unique_tags = len(db.prepare_tag_candidates(records))
    except Exception as exc:
        _record_failure_stage(exc, "validation")
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
        _record_failure_stage(exc, "persistence")
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


def _record_failure_stage(error: Exception, stage: str) -> None:
    """Attach lifecycle context without changing established exception types."""
    try:
        error.upsert_stage = stage
    except (AttributeError, TypeError):
        pass


def discover_csvs(directory: str | Path | None = None) -> list[Path]:
    """Return directly contained CSVs in deterministic filename order."""
    root = Path(directory) if directory is not None else workflow_paths.CSV_DIR
    files = sorted(
        (path for path in root.glob("*.csv") if path.is_file()),
        key=lambda path: (path.name.casefold(), path.name),
    )
    if not files:
        raise ValueError(f"no CSV files found in default directory: {root}")
    return files


def _archive_destinations(csv_path: Path, report_path: Path, directory: Path) -> tuple[Path, Path]:
    """Resolve pair destinations and reject destructive success archival."""
    csv_destination = directory / csv_path.name
    report_destination = directory / report_path.name
    collisions = [path for path in (csv_destination, report_destination) if path.exists()]
    if collisions:
        names = ", ".join(str(path) for path in collisions)
        error = FileExistsError(f"archive destination already exists: {names}")
        _record_failure_stage(error, "archive_preflight")
        raise error
    return csv_destination, report_destination


def _move_pair(csv_path: Path, report_path: Path, directory: Path) -> tuple[Path, Path]:
    """Move an evidence pair, compensating when the second move fails."""
    directory.mkdir(parents=True, exist_ok=True)
    csv_destination, report_destination = _archive_destinations(csv_path, report_path, directory)
    moved_report = False
    try:
        shutil.move(str(report_path), str(report_destination))
        moved_report = True
        shutil.move(str(csv_path), str(csv_destination))
    except Exception as exc:
        if moved_report and report_destination.exists() and not report_path.exists():
            try:
                shutil.move(str(report_destination), str(report_path))
            except Exception as compensation_error:
                try:
                    exc.add_note(f"report compensation failed: {compensation_error}")
                except AttributeError:
                    pass
        _record_failure_stage(exc, "archival")
        raise
    return csv_destination, report_destination


def _unique_quarantine_paths(csv_path: Path, report_path: Path | None) -> tuple[Path, Path | None, Path]:
    """Choose one collision-safe suffix for a failed artifact set."""
    directory = workflow_paths.CSV_ERROR_DIR
    directory.mkdir(parents=True, exist_ok=True)
    while True:
        token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + f"-{uuid4().hex[:8]}"
        csv_destination = directory / f"{csv_path.stem}.{token}{csv_path.suffix}"
        report_destination = None
        if report_path is not None and report_path.exists():
            report_destination = directory / f"{report_path.stem}.{token}{report_path.suffix}"
        error_destination = directory / f"{csv_path.stem}.{token}.upsert-error.json"
        candidates = (csv_destination, error_destination, report_destination)
        if not any(path is not None and path.exists() for path in candidates):
            return csv_destination, report_destination, error_destination


def quarantine_failure(
    csv_path: Path,
    report_path: Path | None,
    error: Exception,
    *,
    committed: bool,
) -> tuple[str, ...]:
    """Best-effort quarantine of one failed default-batch artifact set."""
    messages = []
    csv_destination, report_destination, error_destination = _unique_quarantine_paths(
        csv_path, report_path
    )
    moved = []
    for source, destination, label in (
        (report_path, report_destination, "report"),
        (csv_path, csv_destination, "csv"),
    ):
        if source is None or destination is None or not source.exists():
            continue
        try:
            shutil.move(str(source), str(destination))
            moved.append(f"{label}={destination}")
        except Exception as diagnostic_error:
            messages.append(f"QUARANTINE_ERROR {label}={source} error={diagnostic_error}")
    payload = {
        "source_csv": str(csv_path),
        "source_report": str(report_path) if report_path is not None else None,
        "stage": getattr(error, "upsert_stage", "application"),
        "error_type": type(error).__name__,
        "error": str(error),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database_committed": committed,
    }
    try:
        error_destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        moved.append(f"error_report={error_destination}")
    except Exception as diagnostic_error:
        messages.append(f"QUARANTINE_ERROR error_report={error_destination} error={diagnostic_error}")
    messages.insert(0, f"QUARANTINED csv={csv_path} {' '.join(moved)}".rstrip())
    return tuple(messages)


def _apply_one(
    csv_path: Path,
    *,
    approved: bool,
    report_path: Path | None,
    database,
    reporter: Reporter | None,
) -> UpdateResult:
    """Apply and archive one file while preserving per-file atomicity."""
    report = report_path if report_path is not None else default_validation_report(csv_path)
    archive = workflow_paths.CSV_UPSERTED_DIR
    _archive_destinations(csv_path, report, archive)
    count = apply_csv(
        csv_path, approved=approved, report_path=report,
        database=database, reporter=reporter,
    )
    try:
        csv_destination, report_destination = _move_pair(csv_path, report, archive)
    except Exception as exc:
        try:
            exc.database_committed = True
            exc.applied_count = count
        except (AttributeError, TypeError):
            pass
        raise
    return UpdateResult(
        "apply csv", str(csv_path), proposed=count, applied=count,
        messages=(f"APPLIED csv={csv_destination} report={report_destination}",),
    )


def register_parser(subparsers):
    """Register the approved-CSV apply command and its safety flags."""
    parser = subparsers.add_parser(COMMAND, help="Apply an operator-approved extraction CSV")
    parser.add_argument(
        "csv", nargs="?", type=Path,
        help="operator-reviewed weekly extraction CSV; default: every CSV in helpers/CSV",
    )
    parser.add_argument("--validation-report", type=Path, help="override the adjacent validation report")
    parser.add_argument("--approved", action="store_true", help="Confirm the CSV was manually validated")
    parser.set_defaults(handler=run)


def run(args, dependencies=None):
    """Apply one explicit CSV or every eligible default-directory CSV."""
    dependencies = dependencies or {}
    database = dependencies.get("database", db)
    reporter = dependencies.get("reporter")
    report_override = getattr(args, "validation_report", None)
    if not args.approved:
        raise PermissionError("database update requires explicit --approved confirmation")
    if args.csv is None and report_override is not None:
        raise ValueError("--validation-report requires an explicit CSV path")

    if args.csv is not None:
        return _apply_one(
            Path(args.csv), approved=True, report_path=report_override,
            database=database, reporter=reporter,
        )

    csvs = discover_csvs(dependencies.get("csv_directory"))
    results = []
    for index, csv_path in enumerate(csvs, 1):
        report = default_validation_report(csv_path)
        try:
            result = _apply_one(
                csv_path, approved=True, report_path=report,
                database=database, reporter=reporter,
            )
            results.append(result)
            emit(
                reporter, "candidate_completed", operation="apply_csv_batch",
                completed=index, total=len(csvs), identity=str(csv_path), outcome="applied",
            )
        except Exception as exc:
            committed = bool(getattr(exc, "database_committed", False))
            try:
                diagnostics = quarantine_failure(csv_path, report, exc, committed=committed)
            except Exception as diagnostic_error:
                diagnostics = (
                    f"QUARANTINE_ERROR csv={csv_path} error={diagnostic_error}",
                )
            results.append(UpdateResult(
                "apply csv", str(csv_path),
                proposed=int(getattr(exc, "applied_count", 0)),
                applied=int(getattr(exc, "applied_count", 0)), failed=1,
                messages=(
                    f"FAILED csv={csv_path} stage={getattr(exc, 'upsert_stage', 'application')} "
                    f"committed={str(committed).lower()} error={exc}",
                    *diagnostics,
                ),
            ))
            emit(
                reporter, "candidate_completed", operation="apply_csv_batch",
                completed=index, total=len(csvs), identity=str(csv_path), outcome="failed",
            )
    merged = merge_results("apply csv batch", str(workflow_paths.CSV_DIR), results)
    failed_files = sum(result.failed > 0 for result in results)
    return UpdateResult(
        merged.operation, merged.target, proposed=merged.proposed, applied=merged.applied,
        skipped=merged.skipped, failed=merged.failed,
        messages=(
            *merged.messages,
            f"BATCH files={len(results)} succeeded={len(results) - failed_files} "
            f"failed={failed_files} records_applied={merged.applied}",
        ),
    )
