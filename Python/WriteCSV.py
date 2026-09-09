"""Validation CSV serialization for normalized extraction records."""

from __future__ import annotations

import csv
from pathlib import Path

from workflow_models import ExtractionRecord
from workflow_paths import extraction_csv_path


FIELDNAMES = [
    "week_date", "rank", "appid", "name", "tags", "tag_ids",
    "unresolved_tags", "rating", "rating_label", "price", "discount", "last_week_rank",
    "consecutive_weeks", "errors",
]


def write_csv(records, filepath: str | Path | None = None) -> Path:
    """Write records using the stable validation schema and return the path.

    ``ExtractionRecord`` instances are serialized through their model contract;
    mapping-like rows are passed directly to ``csv.DictWriter``.
    """
    path = Path(filepath) if filepath else extraction_csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [record.to_csv_row() if isinstance(record, ExtractionRecord) else record for record in records]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_csv(filepath: str | Path) -> list[dict]:
    """Read a validation CSV into dictionaries without applying type coercion."""
    with Path(filepath).open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
