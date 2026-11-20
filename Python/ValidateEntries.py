"""Validate one extraction CSV against Steam's public global weekly chart."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from validation_models import (
    ChartIdentity,
    ValidationResult,
    ValidationStatus,
    WeeklyValidationResult,
    WrongRank,
)
from workflow_clients import HEADERS, STEAM_API_KEY, STEAM_STORE_COUNTRY, STEAM_WEEKLY_URL, TIMEOUT
from workflow_paths import classified_csv_path
from workflow_progress import emit


CHART_URL = "https://store.steampowered.com/charts/topsellers/global/{date}"
EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_ERROR = 2


class ValidationInputError(ValueError):
    """Raised when the CSV cannot represent one complete weekly identity set."""


def csv_sha256(path: str | Path) -> str:
    """Return the content digest that binds a report to its exact CSV bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sidecar_path(csv_path: str | Path) -> Path:
    """Derive the validation report path beside its source CSV."""
    path = Path(csv_path)
    return path.with_name(f"{path.stem}.validation.json")


def parse_csv_identities(path: str | Path) -> tuple[str, list[ChartIdentity], list[int], list[int]]:
    """Parse one Tuesday's identities and report duplicate ranks/app IDs.

    Raises ``ValidationInputError`` for missing columns, malformed values,
    invalid ranges, empty input, or CSV data spanning more than one week.
    """
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = {"week_date", "rank", "appid"} - set(reader.fieldnames or ())
        if missing:
            raise ValidationInputError(f"missing required CSV fields: {', '.join(sorted(missing))}")
        rows = list(reader)
    if not rows:
        raise ValidationInputError("validation CSV contains no records")

    weeks: set[str] = set()
    identities: list[ChartIdentity] = []
    for line, row in enumerate(rows, 2):
        try:
            week = datetime.strptime(row["week_date"], "%Y-%m-%d")
            rank = int(row["rank"])
            appid = int(row["appid"])
        except (TypeError, ValueError) as exc:
            raise ValidationInputError(f"line {line} has a malformed week, rank, or appid") from exc
        if week.weekday() != 1:
            raise ValidationInputError(f"line {line} week_date is not a Tuesday")
        if not 1 <= rank <= 100 or appid <= 0:
            raise ValidationInputError(f"line {line} has an out-of-range rank or appid")
        weeks.add(week.strftime("%Y-%m-%d"))
        identities.append(ChartIdentity(rank, appid))
    if len(weeks) != 1:
        raise ValidationInputError("validation CSV must contain exactly one distinct week")

    rank_counts = Counter(item.rank for item in identities)
    appid_counts = Counter(item.appid for item in identities)
    duplicate_ranks = sorted(value for value, count in rank_counts.items() if count > 1)
    duplicate_appids = sorted(value for value, count in appid_counts.items() if count > 1)
    return next(iter(weeks)), identities, duplicate_ranks, duplicate_appids


def _loader_json(html: str) -> list:
    """Decode the JSON array from Steam Charts' SSR payload or legacy inline script."""
    soup = BeautifulSoup(html, "html.parser")
    ssr_data = soup.find("script", id="valve-ssr-data")
    if ssr_data is not None:
        try:
            payload = json.loads(ssr_data.get_text())
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Steam Charts loader data could not be parsed") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("loaderData"), list):
            raise RuntimeError("Steam Charts loader data could not be parsed")
        return payload["loaderData"]
    script = next(
        (node.get_text() for node in soup.find_all("script") if "window.SSR.loaderData" in node.get_text()),
        None,
    )
    if not script:
        raise RuntimeError("Steam Charts loader data was not found")
    marker = script.find("window.SSR.loaderData")
    start = script.find("[", marker)
    decoder = json.JSONDecoder()
    try:
        payload, _ = decoder.raw_decode(script[start:])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Steam Charts loader data could not be parsed") from exc
    return payload


def _find_weekly(value):
    """Recursively locate a weekly rank object in nested loader data."""
    if isinstance(value, dict):
        weekly = value.get("weekly")
        if isinstance(weekly, dict) and isinstance(weekly.get("rgRanks"), list):
            return weekly
        if isinstance(value.get("rgRanks"), list):
            return value
        for child in value.values():
            found = _find_weekly(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, str):
                try:
                    child = json.loads(child)
                except (TypeError, ValueError):
                    continue
            found = _find_weekly(child)
            if found is not None:
                return found
    return None


def parse_chart_bootstrap(html: str) -> list[ChartIdentity]:
    """Extract the rendered chart prefix from Steam's page bootstrap."""
    weekly = _find_weekly(_loader_json(html))
    if weekly is None:
        raise RuntimeError("Steam Charts weekly bootstrap was not found")
    identities = []
    for item in weekly["rgRanks"]:
        appid = (item.get("itemKey") or {}).get("appid")
        rank = item.get("nRank", item.get("rank"))
        if appid is None or rank is None:
            raise RuntimeError("Steam chart contains a non-application entry")
        identities.append(ChartIdentity(int(rank), int(appid)))
    if not identities:
        raise RuntimeError("Steam chart bootstrap is empty")
    return identities


def complete_chart_request(week: str) -> dict:
    """Build the API request for the complete global Top 100 on a Tuesday."""
    timestamp = int(datetime.strptime(week, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    return {
        "country_code": "",
        "context": {"country_code": STEAM_STORE_COUNTRY},
        "data_request": {"include_basic_info": True, "include_assets": True, "include_release": True},
        "start_date": timestamp,
        "page_start": 0,
        "page_count": 100,
    }


def parse_complete_chart(payload: dict) -> list[ChartIdentity]:
    """Validate and return exactly 100 unique, consecutively ranked entries."""
    return [ChartIdentity(item["rank"], item["appid"]) for item in parse_complete_chart_rows(payload)]


def parse_complete_chart_rows(payload: dict) -> list[dict]:
    """Validate and normalize complete global rows needed by identity repair."""
    rows = payload.get("response", {}).get("ranks", [])
    normalized = []
    for item in rows:
        basic = item.get("item") or {}
        appid = item.get("appid", basic.get("appid"))
        rank = item.get("rank", item.get("nRank"))
        if appid is None or rank is None:
            raise RuntimeError("complete Steam chart contains a non-application entry")
        name = str(basic.get("name") or "").strip()
        normalized.append({
            "rank": int(rank), "appid": int(appid), "name": name,
            "last_week_rank": item.get("last_week_rank"),
            "consecutive_weeks": item.get("consecutive_weeks"),
        })
    if len(normalized) != 100:
        raise RuntimeError(f"complete Steam chart returned {len(normalized)} entries instead of 100")
    if sorted(item["rank"] for item in normalized) != list(range(1, 101)):
        raise RuntimeError("complete Steam chart does not contain ranks 1 through 100 exactly once")
    if len({item["appid"] for item in normalized}) != 100:
        raise RuntimeError("complete Steam chart contains duplicate application identifiers")
    return sorted(normalized, key=lambda item: item["rank"])


class GlobalChartFetcher:
    """Fetch prefix-checked detailed rows from the explicitly global chart."""

    def __init__(self, session=None, reporter=None):
        self.session = session or requests.Session()
        self.reporter = reporter

    def __call__(self, week: str) -> tuple[str, list[dict]]:
        url = CHART_URL.format(date=week)
        identity = f"week={week}"
        emit(self.reporter, "unit_started", operation="repair_weekly_identities",
             phase="rendered_chart", identity=identity)
        try:
            page = self.session.get(url, headers=HEADERS, timeout=TIMEOUT)
            page.raise_for_status()
            rendered = parse_chart_bootstrap(page.text)
        except Exception as exc:
            emit(self.reporter, "unit_completed", operation="repair_weekly_identities",
                 phase="rendered_chart", identity=identity, outcome="failed", error=exc)
            raise
        emit(self.reporter, "unit_completed", operation="repair_weekly_identities",
             phase="rendered_chart", identity=identity, outcome="completed")
        emit(self.reporter, "unit_started", operation="repair_weekly_identities",
             phase="complete_chart", identity=identity)
        try:
            response = self.session.get(
                STEAM_WEEKLY_URL,
                params={"key": STEAM_API_KEY, "input_json": json.dumps(complete_chart_request(week))},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
        except Exception as exc:
            emit(self.reporter, "unit_completed", operation="repair_weekly_identities",
                 phase="complete_chart", identity=identity, outcome="failed", error=exc)
            raise
        try:
            rows = parse_complete_chart_rows(response.json())
        except Exception as exc:
            emit(self.reporter, "unit_completed", operation="repair_weekly_identities",
                 phase="complete_chart", identity=identity, outcome="failed", error=exc)
            raise
        emit(self.reporter, "unit_completed", operation="repair_weekly_identities",
             phase="complete_chart", identity=identity, outcome="completed")
        identities = [ChartIdentity(item["rank"], item["appid"]) for item in rows]
        if identities[: len(rendered)] != rendered:
            raise RuntimeError("Steam page bootstrap does not match the complete global chart prefix")
        return url, rows


class SteamChartFetcher:
    """Fetch and cross-check Steam's rendered chart prefix and complete API list."""
    def __init__(self, session=None):
        """Reuse an injected HTTP session or create a validation session."""
        self.session = session or requests.Session()

    def __call__(self, week: str) -> tuple[str, list[ChartIdentity]]:
        """Return the source URL and verified complete identities for a week."""
        url, rows = GlobalChartFetcher(self.session)(week)
        return url, [ChartIdentity(item["rank"], item["appid"]) for item in rows]


def compare_identities(
    actual: list[ChartIdentity], expected: list[ChartIdentity], weekly: WeeklyValidationResult
) -> None:
    """Populate missing, unexpected, and moved identities on a weekly result."""
    expected_by_rank = {item.rank: item.appid for item in expected}
    actual_by_rank = {item.rank: item.appid for item in actual}
    expected_by_appid = {item.appid: item.rank for item in expected}
    actual_by_appid = {item.appid: item.rank for item in actual}
    weekly.missing = sorted(item for item in expected if item.appid not in actual_by_appid)
    weekly.unexpected = sorted(item for item in actual if item.appid not in expected_by_appid)
    weekly.wrong_ranks = sorted(
        WrongRank(appid, expected_rank, actual_by_appid[appid])
        for appid, expected_rank in expected_by_appid.items()
        if appid in actual_by_appid and actual_by_appid[appid] != expected_rank
    )
    # Same-rank substitutions are already represented by missing/unexpected; this
    # assertion keeps rank comparison explicit and catches malformed chart sources.
    if set(expected_by_rank) != set(range(1, 101)):
        raise RuntimeError("expected chart ranks are incomplete")


def write_report(path: Path, result: ValidationResult) -> Path:
    """Atomically replace a JSON evidence sidecar and clean up failed temp files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        # Write beside the destination so os.replace remains atomic on one volume.
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(result.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return path


def validate_csv(csv_path: str | Path, *, fetcher=None) -> tuple[ValidationResult, Path]:
    """Validate a CSV and always emit a digest-bound evidence report.

    Input, network, and comparison errors become an ``ERROR`` result instead of
    escaping; failures while writing the evidence report still propagate.
    """
    path = Path(csv_path)
    digest = csv_sha256(path)
    weekly = WeeklyValidationResult()
    status = ValidationStatus.ERROR
    try:
        week, actual, duplicate_ranks, duplicate_appids = parse_csv_identities(path)
        weekly.week = week
        weekly.source_url = CHART_URL.format(date=week)
        weekly.actual_count = len(actual)
        weekly.duplicate_ranks = duplicate_ranks
        weekly.duplicate_appids = duplicate_appids
        source_url, expected = (fetcher or SteamChartFetcher())(week)
        weekly.source_url = source_url
        weekly.expected_count = len(expected)
        compare_identities(actual, expected, weekly)
        status = ValidationStatus.FAILED if weekly.has_differences else ValidationStatus.PASSED
    except Exception as exc:
        weekly.error = str(exc)
        status = ValidationStatus.ERROR
    result = ValidationResult(digest, status, weekly)
    report = write_report(sidecar_path(path), result)
    return result, report


def classify_artifacts(csv_path: str | Path, report_path: str | Path, status: ValidationStatus):
    """Move a CSV/report pair to the passed or error area without overwriting."""
    source_csv = Path(csv_path)
    source_report = Path(report_path)
    target_csv = classified_csv_path(source_csv.name, passed=status is ValidationStatus.PASSED)
    target_report = target_csv.with_name(f"{target_csv.stem}.validation.json")
    counter = 1
    while (
        source_csv.resolve() != target_csv.resolve()
        and (target_csv.exists() or target_report.exists())
    ):
        target_csv = classified_csv_path(
            f"{source_csv.stem}_{counter}{source_csv.suffix}",
            passed=status is ValidationStatus.PASSED,
        )
        target_report = target_csv.with_name(f"{target_csv.stem}.validation.json")
        counter += 1
    if source_csv.resolve() != target_csv.resolve():
        os.replace(source_csv, target_csv)
    if source_report.resolve() != target_report.resolve():
        os.replace(source_report, target_report)
    return target_csv, target_report


def run_validation(csv_path: str | Path, *, fetcher=None, classify=True):
    """Validate a CSV and optionally classify both artifact files together."""
    result, report = validate_csv(csv_path, fetcher=fetcher)
    final_csv, final_report = (
        classify_artifacts(csv_path, report, result.status) if classify else (Path(csv_path), report)
    )
    return result, final_csv, final_report


def build_parser() -> argparse.ArgumentParser:
    """Create the single-CSV validation command-line parser."""
    parser = argparse.ArgumentParser(description="Validate one weekly extraction CSV against Steam Top 100")
    parser.add_argument("csv", type=Path, help="weekly extraction CSV to validate and classify")
    return parser


def main(argv=None) -> int:
    """Run validation, print artifact locations, and return a status exit code."""
    args = build_parser().parse_args(argv)
    result, csv_path, report_path = run_validation(args.csv)
    print(f"status={result.status.value} week={result.weekly.week or 'unknown'}")
    print(f"CSV={csv_path}")
    print(f"REPORT={report_path}")
    return {ValidationStatus.PASSED: EXIT_PASSED, ValidationStatus.FAILED: EXIT_FAILED}.get(
        result.status, EXIT_ERROR
    )


if __name__ == "__main__":
    raise SystemExit(main())
