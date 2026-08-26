"""Repository-relative paths for script-generated helper artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
HELPERS_DIR = REPOSITORY_ROOT / "helpers"
CSV_DIR = HELPERS_DIR / "CSV"
CSV_ERROR_DIR = HELPERS_DIR / "CSV_error"
EXCEPTIONS_PATH = HELPERS_DIR / "Exceptions.json"
LEGACY_EXCEPTIONS_PATH = REPOSITORY_ROOT / "JSON" / "TagsExceptions.JSON"


def helper_path(filename: str) -> Path:
    path = (HELPERS_DIR / filename).resolve()
    if HELPERS_DIR.resolve() not in path.parents:
        raise ValueError("helper filename must stay within the helpers directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def extraction_csv_path(now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return helper_path(f"steam_top_100_{timestamp}.csv")


def classified_csv_path(filename: str, *, passed: bool) -> Path:
    directory = CSV_DIR if passed else CSV_ERROR_DIR
    path = (directory / filename).resolve()
    if directory.resolve() not in path.parents:
        raise ValueError("CSV filename must stay within its classified helper directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def weekly_extraction_csv_path(week: str, now: datetime | None = None) -> Path:
    parsed = datetime.strptime(week, "%Y-%m-%d")
    if parsed.weekday() != 1:
        raise ValueError("extraction week must be a Tuesday")
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")
    filename = f"steam_top_100_{week}_{timestamp}.csv"
    # CSV_error is also the safe staging area: nothing is eligible until it passes.
    return classified_csv_path(filename, passed=False)


def exceptions_path() -> Path:
    return EXCEPTIONS_PATH if EXCEPTIONS_PATH.exists() else LEGACY_EXCEPTIONS_PATH
