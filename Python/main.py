"""CLI for isolated, read-only asynchronous extraction."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import db
import WriteCSV
import ValidateEntries
from extraction_pipeline import CatalogSnapshot, ExtractionPipeline, PipelineConfig
from request_scheduler import DEFAULT_POLICIES, ProviderGate, ProviderPolicy
from workflow_clients import RealExtractionClients
from workflow_paths import weekly_extraction_csv_path
from workflow_progress import Reporter, TerminalProgressReporter, emit


def last_closed_tuesday(now=None) -> str:
    """Return the latest Tuesday whose chart week has started before today."""
    current = now or datetime.now(timezone.utc)
    days_since_tuesday = (current.weekday() - 1) % 7
    candidate = current - timedelta(days=days_since_tuesday)
    if candidate.date() == current.date():
        candidate -= timedelta(days=7)
    return candidate.strftime("%Y-%m-%d")


def validate_tuesday(value: str) -> str:
    """Validate a CLI date as an ISO-formatted Tuesday."""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc
    if parsed.weekday() != 1:
        raise argparse.ArgumentTypeError(f"{value} is not a Tuesday")
    return value


def select_dates(start_date: str | None, end_date: str | None = None, *, now=None) -> list[str]:
    """Select one week or expand an inclusive range of Tuesday dates."""
    if start_date is None:
        if end_date is not None:
            raise ValueError("end date requires a start date")
        return [last_closed_tuesday(now)]
    if end_date is None:
        return [start_date]

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    if end < start:
        raise ValueError("end date must not precede start date")

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=7)
    return dates


def build_parser() -> argparse.ArgumentParser:
    """Create the read-only extraction command-line interface."""
    parser = argparse.ArgumentParser(description="Extract Steam weekly data without database writes")
    parser.add_argument("start_date", nargs="?", type=validate_tuesday, help="optional first Tuesday date")
    parser.add_argument("end_date", nargs="?", type=validate_tuesday, help="optional inclusive final Tuesday date")
    parser.add_argument("--output", help="optional staging CSV path for one week or directory for multiple weeks")
    parser.add_argument("--max-entries", type=int, default=int(os.environ.get("PIPELINE_MAX_ENTRIES", "100")), help="maximum chart entries to process per week")
    parser.add_argument("--itad-batch-size", type=int, default=int(os.environ.get("ITAD_BATCH_SIZE", "100")), help="maximum app IDs in each IsThereAnyDeal lookup batch")
    parser.add_argument("--itad-batch-wait", type=float, default=float(os.environ.get("ITAD_BATCH_WAIT", "0.05")), help="seconds to wait between IsThereAnyDeal lookup batches")
    return parser


def build_gates(reporter: Reporter | None = None):
    """Build provider gates, applying environment overrides to default policies."""
    gates = {}
    for name, default in DEFAULT_POLICIES.items():
        prefix = name.upper()
        policy = ProviderPolicy(
            interval=float(os.environ.get(f"{prefix}_INTERVAL", default.interval)),
            concurrency=int(os.environ.get(f"{prefix}_CONCURRENCY", default.concurrency)),
            queue_size=int(os.environ.get(f"{prefix}_QUEUE_SIZE", default.queue_size)),
            retries=int(os.environ.get(f"{prefix}_RETRIES", default.retries)),
            backoff_base=default.backoff_base,
        )
        gates[name] = ProviderGate(policy, provider=name, reporter=reporter)
    return gates


async def extract(dates, *, clients=None, snapshot=None, gates=None, config=None, reporter=None):
    """Construct and run the extraction pipeline with injectable dependencies."""
    catalog = snapshot or db.load_catalog_snapshot()
    pipeline = ExtractionPipeline(
        clients or RealExtractionClients(),
        gates or build_gates(reporter),
        CatalogSnapshot(**catalog),
        config=config or PipelineConfig(),
        reporter=reporter,
    )
    return await pipeline.run(dates)


def _weekly_output(output: str | None, week: str, *, multiple: bool) -> Path:
    """Resolve a staging file, requiring a directory for multiweek runs."""
    if not output:
        return weekly_extraction_csv_path(week)
    requested = Path(output)
    if multiple:
        if requested.suffix.lower() == ".csv":
            raise ValueError("--output must be a directory when multiple weeks are requested")
        return requested / f"steam_top_100_{week}.csv"
    return requested


def _record_value(record, name, default=None):
    """Read a field uniformly from mapping or model extraction records."""
    return record.get(name, default) if isinstance(record, dict) else getattr(record, name, default)


def print_unresolved_summary(records, csv_path) -> None:
    """Print unresolved tags grouped with affected games and a repair command."""
    grouped = {}
    for record in records:
        game = (
            str(_record_value(record, "name", "")),
            _record_value(record, "appid", ""),
            _record_value(record, "rank", ""),
        )
        for raw_name in _record_value(record, "unresolved_tags", []) or []:
            name = str(raw_name).strip()
            if not name:
                continue
            entry = grouped.setdefault(name.casefold(), {"name": name, "games": []})
            if game not in entry["games"]:
                entry["games"].append(game)
    print(f"unresolved_tags={len(grouped)}")
    for entry in sorted(grouped.values(), key=lambda value: value["name"].casefold()):
        print(f"unresolved_tag={entry['name']}")
        for name, appid, rank in sorted(entry["games"], key=lambda value: (value[2], value[1])):
            print(f"  game={name} appid={appid} rank={rank}")
    if grouped:
        print(f'RESOLVE=python Python/UpdateDB.py resolve tags "{csv_path}"')


def main(argv=None, *, extractor=extract, validator=ValidateEntries.run_validation, reporter=None):
    """Extract, stage, validate, and report each requested week independently.

    Processing continues after a failed week; the final exit status reports
    whether any extraction failed or any validation did not pass.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        dates = select_dates(args.start_date, args.end_date)
    except ValueError as exc:
        parser.error(str(exc))
    config = PipelineConfig(
        max_entries=args.max_entries,
        itad_batch_size=args.itad_batch_size,
        itad_batch_wait=args.itad_batch_wait,
    )
    unsuccessful = False
    progress = reporter or TerminalProgressReporter()
    for week in dates:
        # Isolate each week so later work survives an earlier provider failure.
        stage = "week"
        emit(progress, "stage_started", week=week, stage=stage)
        try:
            stage = "extraction"
            extractor_kwargs = {"config": config}
            parameters = inspect.signature(extractor).parameters
            # Compatibility injectors used by tests may not accept a reporter.
            if "reporter" in parameters or any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            ):
                extractor_kwargs["reporter"] = progress
            records = asyncio.run(extractor([week], **extractor_kwargs))
            stage = "csv_write"
            emit(progress, "stage_started", week=week, stage=stage, records=len(records))
            staging_path = WriteCSV.write_csv(
                records, _weekly_output(args.output, week, multiple=len(dates) > 1)
            )
            emit(progress, "stage_completed", week=week, stage=stage, path=staging_path)
            stage = "validation"
            emit(progress, "stage_started", week=week, stage=stage)
            result, csv_path, report_path = validator(staging_path)
            emit(
                progress, "stage_completed", week=week, stage=stage,
                status=result.status.value, csv=csv_path, report=report_path,
            )
            print(
                f"week={week} status={result.status.value} records={len(records)} "
                f"CSV={csv_path} REPORT={report_path}"
            )
            print_unresolved_summary(records, csv_path)
            unsuccessful = unsuccessful or result.status is not ValidateEntries.ValidationStatus.PASSED
            emit(progress, "stage_completed", week=week, stage="week", status=result.status.value)
        except Exception as exc:
            unsuccessful = True
            emit(progress, "stage_failed", week=week, stage=stage, error=exc)
            print(f"week={week} status=error extraction={exc}", file=sys.stderr)
    return 1 if unsuccessful else 0


if __name__ == "__main__":
    raise SystemExit(main())
