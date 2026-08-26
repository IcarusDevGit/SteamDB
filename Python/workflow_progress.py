"""Structured, optional progress reporting for operator workflows."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, TextIO


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    kind: str
    fields: Mapping[str, Any] = field(default_factory=dict)


class ProgressReporter(Protocol):
    def __call__(self, event: ProgressEvent) -> None: ...


Reporter = Callable[[ProgressEvent], None]


def emit(reporter: Reporter | None, kind: str, **fields: Any) -> None:
    if reporter is not None:
        reporter(ProgressEvent(kind, fields))


def _safe(value: Any) -> str:
    return " ".join(str(value).splitlines()).strip()


class TerminalProgressReporter:
    """Render progress as atomic, immediately visible single-line messages."""

    def __init__(self, stream: TextIO | None = None):
        self.stream = stream

    def __call__(self, event: ProgressEvent) -> None:
        fields = dict(event.fields)
        prefix = ""
        if "completed" in fields and "total" in fields:
            prefix = f"[{fields.pop('completed')}/{fields.pop('total')}] "
        details = " ".join(
            f"{key}={_safe(value)}" for key, value in fields.items() if value is not None
        )
        line = f"{prefix}event={_safe(event.kind)}"
        if details:
            line += f" {details}"
        print(line, file=self.stream or sys.stderr, flush=True)
