"""CLI for isolated, read-only asynchronous extraction."""

from __future__ import annotations

import argparse
import asyncio
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


def last_closed_tuesday(now=None) -> str:
    current = now or datetime.now(timezone.utc)
    days_since_tuesday = (current.weekday() - 1) % 7
    candidate = current - timedelta(days=days_since_tuesday)
    if candidate.date() == current.date():
        candidate -= timedelta(days=7)
    return candidate.strftime("%Y-%m-%d")


def validate_tuesday(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc
    if parsed.weekday() != 1:
        raise argparse.ArgumentTypeError(f"{value} is not a Tuesday")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract Steam weekly data without database writes")
    parser.add_argument("dates", nargs="*", type=validate_tuesday, help="one or more Tuesday dates")
    parser.add_argument("--output", help="optional staging CSV path for one week or directory for multiple weeks")
    parser.add_argument("--max-entries", type=int, default=int(os.environ.get("PIPELINE_MAX_ENTRIES", "100")))
    parser.add_argument("--itad-batch-size", type=int, default=int(os.environ.get("ITAD_BATCH_SIZE", "100")))
    parser.add_argument("--itad-batch-wait", type=float, default=float(os.environ.get("ITAD_BATCH_WAIT", "0.05")))
    return parser


def build_gates():
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
        gates[name] = ProviderGate(policy)
    return gates


async def extract(dates, *, clients=None, snapshot=None, gates=None, config=None):
    catalog = snapshot or db.load_catalog_snapshot()
    pipeline = ExtractionPipeline(
        clients or RealExtractionClients(),
        gates or build_gates(),
        CatalogSnapshot(**catalog),
        config=config or PipelineConfig(),
    )
    return await pipeline.run(dates)


def _weekly_output(output: str | None, week: str, *, multiple: bool) -> Path:
    if not output:
        return weekly_extraction_csv_path(week)
    requested = Path(output)
    if multiple:
        if requested.suffix.lower() == ".csv":
            raise ValueError("--output must be a directory when multiple weeks are requested")
        return requested / f"steam_top_100_{week}.csv"
    return requested


def main(argv=None, *, extractor=extract, validator=ValidateEntries.run_validation):
    args = build_parser().parse_args(argv)
    dates = args.dates or [last_closed_tuesday()]
    config = PipelineConfig(
        max_entries=args.max_entries,
        itad_batch_size=args.itad_batch_size,
        itad_batch_wait=args.itad_batch_wait,
    )
    unsuccessful = False
    for week in dates:
        try:
            records = asyncio.run(extractor([week], config=config))
            staging_path = WriteCSV.write_csv(
                records, _weekly_output(args.output, week, multiple=len(dates) > 1)
            )
            result, csv_path, report_path = validator(staging_path)
            print(
                f"week={week} status={result.status.value} records={len(records)} "
                f"CSV={csv_path} REPORT={report_path}"
            )
            unsuccessful = unsuccessful or result.status is not ValidateEntries.ValidationStatus.PASSED
        except Exception as exc:
            unsuccessful = True
            print(f"week={week} status=error extraction={exc}", file=sys.stderr)
    return 1 if unsuccessful else 0


if __name__ == "__main__":
    raise SystemExit(main())
