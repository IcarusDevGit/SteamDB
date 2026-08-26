"""Serializable models for weekly Steam chart validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class ValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass(frozen=True, order=True)
class ChartIdentity:
    rank: int
    appid: int


@dataclass(frozen=True, order=True)
class WrongRank:
    appid: int
    expected_rank: int
    actual_rank: int


@dataclass
class WeeklyValidationResult:
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
    csv_sha256: str
    status: ValidationStatus
    weekly: WeeklyValidationResult
    schema_version: int = 1

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload
