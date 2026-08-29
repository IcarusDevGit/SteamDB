"""Serializable models for weekly Steam chart validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class ValidationStatus(str, Enum):
    """Classify validation as successful, discrepant, or operationally failed."""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass(frozen=True, order=True)
class ChartIdentity:
    """Identify a chart entry by its expected rank and Steam application ID."""
    rank: int
    appid: int


@dataclass(frozen=True, order=True)
class WrongRank:
    """Describe an application found at a rank other than the CSV rank."""
    appid: int
    expected_rank: int
    actual_rank: int


@dataclass
class WeeklyValidationResult:
    """Collect structural and identity differences for one chart week."""
    week: str | None = None
    source_url: str | None = None
    expected_count: int = 0
    actual_count: int = 0
    duplicate_ranks: list[int] = field(default_factory=list)
    duplicate_appids: list[int] = field(default_factory=list)
    missing: list[ChartIdentity] = field(default_factory=list)
    unexpected: list[ChartIdentity] = field(default_factory=list)
    wrong_ranks: list[WrongRank] = field(default_factory=list)
    error: str | None = None

    @property
    def has_differences(self) -> bool:
        """Return whether any count, duplicate, identity, or rank check differs."""
        return bool(
            self.duplicate_ranks
            or self.duplicate_appids
            or self.missing
            or self.unexpected
            or self.wrong_ranks
            or self.expected_count != self.actual_count
        )


@dataclass
class ValidationResult:
    """Wrap validation evidence with its CSV digest and schema version."""
    csv_sha256: str
    status: ValidationStatus
    weekly: WeeklyValidationResult
    schema_version: int = 1

    def to_dict(self) -> dict:
        """Return a JSON-ready representation with the enum stored as text."""
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload
