"""Typed records shared by the isolated extraction, CSV, and update workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BranchState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    ABSENT = "absent"
    FAILED = "failed"
    SKIPPED = "skipped"

    @property
    def terminal(self) -> bool:
        return self in {
            BranchState.SUCCEEDED,
            BranchState.ABSENT,
            BranchState.FAILED,
            BranchState.SKIPPED,
        }


@dataclass(slots=True)
class StoreData:
    price: float | None = None
    discount: int | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExtractionRecord:
    week_date: str
    rank: int
    appid: int
    name: str
    last_week_rank: int | None = None
    consecutive_weeks: int | None = None
    category_ids: list[int] = field(default_factory=list)
    itad_id: str | None = None
    rating: float | None = None
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
        return (
            self.itad_state.terminal
            and self.rating_state.terminal
            and self.steam_html_state.terminal
        )

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "week_date": self.week_date,
            "rank": self.rank,
            "appid": self.appid,
            "name": self.name,
            "tags": ", ".join(self.tag_names),
            "tag_ids": ",".join(str(value) for value in self.tag_ids),
            "unresolved_tags": ", ".join(self.unresolved_tags),
            "rating": self.rating,
            "price": self.price,
            "discount": self.discount,
            "last_week_rank": self.last_week_rank,
            "consecutive_weeks": self.consecutive_weeks,
            "errors": " | ".join(self.errors),
        }
