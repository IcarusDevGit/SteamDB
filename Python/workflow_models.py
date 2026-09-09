"""Typed records shared by the isolated extraction, CSV, and update workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


RATING_LABELS = frozenset({
    "Overwhelmingly Positive", "Very Positive", "Positive", "Mostly Positive",
    "Mixed", "Mostly Negative", "Negative", "Very Negative",
    "Overwhelmingly Negative", "no_label",
})


def classify_rating_label(positive: int, total: int) -> str:
    """Return the configured Steam label for exact review counts."""
    if positive < 0 or total < 0 or positive > total:
        raise ValueError("review counts must satisfy 0 <= positive <= total")
    if total < 10:
        return "no_label"
    percent = positive / total
    if percent >= .95 and total >= 500:
        return "Overwhelmingly Positive"
    if percent >= .80:
        return "Very Positive" if total >= 50 else "Positive"
    if percent >= .70:
        return "Mostly Positive"
    if percent >= .40:
        return "Mixed"
    if percent >= .20:
        return "Mostly Negative"
    if total >= 500:
        return "Overwhelmingly Negative"
    return "Very Negative" if total >= 50 else "Negative"


@dataclass(frozen=True, slots=True)
class HistoricalRating:
    """Retain the counts needed to derive one historical rating and label."""
    positive: int
    total: int
    rating: float | None
    label: str


class BranchState(str, Enum):
    """Track whether one independent enrichment branch can still do work."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    ABSENT = "absent"
    FAILED = "failed"
    SKIPPED = "skipped"

    @property
    def terminal(self) -> bool:
        """Return whether the branch has reached a final outcome."""
        return self in {
            BranchState.SUCCEEDED,
            BranchState.ABSENT,
            BranchState.FAILED,
            BranchState.SKIPPED,
        }


@dataclass(slots=True)
class StoreData:
    """Hold the price, discount, and community tags parsed from Steam."""
    price: float | None = None
    discount: int | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExtractionRecord:
    """Accumulate one chart entry as independent enrichment branches finish."""
    week_date: str
    rank: int
    appid: int
    name: str
    last_week_rank: int | None = None
    consecutive_weeks: int | None = None
    category_ids: list[int] = field(default_factory=list)
    itad_id: str | None = None
    rating: float | None = None
    rating_label: str | None = None
    price: float | None = None
    discount: int | None = None
    tag_ids: list[int] = field(default_factory=list)
    tag_names: list[str] = field(default_factory=list)
    unresolved_tags: list[str] = field(default_factory=list)
    itad_state: BranchState = BranchState.PENDING
    rating_state: BranchState = BranchState.PENDING
    steam_html_state: BranchState = BranchState.PENDING
    errors: list[str] = field(default_factory=list)

    @classmethod
    def from_weekly(cls, item: dict[str, Any], week_date: str) -> "ExtractionRecord":
        """Create a partially populated record from a weekly-chart payload."""
        return cls(
            week_date=week_date,
            rank=int(item["rank"]),
            appid=int(item["appid"]),
            name=str(item.get("name") or ""),
            last_week_rank=item.get("last_week_rank"),
            consecutive_weeks=item.get("consecutive_weeks"),
            category_ids=list(item.get("category_ids", item.get("tag_ids", [])) or []),
        )

    @property
    def complete(self) -> bool:
        """Return whether every required enrichment branch is terminal."""
        return (
            self.itad_state.terminal
            and self.rating_state.terminal
            and self.steam_html_state.terminal
        )

    def to_csv_row(self) -> dict[str, Any]:
        """Serialize the normalized record into the validation CSV schema."""
        return {
            "week_date": self.week_date,
            "rank": self.rank,
            "appid": self.appid,
            "name": self.name,
            "tags": ", ".join(self.tag_names),
            "tag_ids": ",".join(str(value) for value in self.tag_ids),
            "unresolved_tags": ", ".join(self.unresolved_tags),
            "rating": self.rating,
            "rating_label": self.rating_label,
            "price": self.price,
            "discount": self.discount,
            "last_week_rank": self.last_week_rank,
            "consecutive_weeks": self.consecutive_weeks,
            "errors": " | ".join(self.errors),
        }
