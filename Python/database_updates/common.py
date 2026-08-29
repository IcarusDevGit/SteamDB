"""Shared immutable update results and CLI reporting helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class UpdateCandidate:
    """Describe a potential database mutation before it is applied."""
    identity: str
    values: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class UpdateResult:
    """Report aggregate outcomes and operator messages for one update command."""
    operation: str
    target: str
    proposed: int = 0
    applied: int = 0
    skipped: int = 0
    failed: int = 0
    messages: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        """Return whether every candidate avoided a recorded failure."""
        return self.failed == 0

    @property
    def exit_code(self) -> int:
        """Map the aggregate outcome to the command-line success convention."""
        return 0 if self.ok else 1

    def render(self) -> str:
        """Render the summary and detail messages as operator-facing text."""
        summary = (
            f"{self.operation}: target={self.target} proposed={self.proposed} "
            f"applied={self.applied} skipped={self.skipped} failed={self.failed}"
        )
        return "\n".join((summary, *self.messages))


def merge_results(operation: str, target: str, results) -> UpdateResult:
    """Combine child results while preserving message order."""
    values = tuple(results)
    return UpdateResult(
        operation=operation,
        target=target,
        proposed=sum(item.proposed for item in values),
        applied=sum(item.applied for item in values),
        skipped=sum(item.skipped for item in values),
        failed=sum(item.failed for item in values),
        messages=tuple(message for item in values for message in item.messages),
    )
