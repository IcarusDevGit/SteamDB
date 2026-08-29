"""Shared repair argument and target helpers."""

from __future__ import annotations

from datetime import date

from workflow_progress import emit


def unit_started(reporter, operation, phase, identity, *, completed=None, total=None):
    """Report the bounded unit that is about to perform potentially slow work."""
    emit(reporter, "unit_started", operation=operation, phase=phase, identity=identity,
         completed=completed, total=total)


def unit_completed(reporter, operation, phase, identity, outcome, *, completed=None, total=None, error=None):
    """Report the terminal outcome of one bounded repair unit."""
    emit(reporter, "unit_completed", operation=operation, phase=phase, identity=identity,
         outcome=outcome, completed=completed, total=total, error=error)


def persistence_progress(reporter, operation, identity, completed, total, *, phase="persistence"):
    """Report SQL completion inside the still-pending repair transaction."""
    emit(reporter, "persistence_progress", operation=operation, phase=phase,
         identity=identity, completed=completed, total=total)


def add_target_arguments(parser, *, week_optional=True):
    """Add shared scope and explicit-apply options to a repair parser."""
    parser.add_argument("--week", type=valid_week, required=not week_optional, help="limit candidates to this Tuesday in YYYY-MM-DD form")
    parser.add_argument("--appid", type=positive_int, help="limit candidates to this positive Steam app ID")
    parser.add_argument("--limit", type=positive_int, help="maximum number of candidates to inspect")
    parser.add_argument("--apply", action="store_true", help="Apply validated repairs; default is dry-run")


def positive_int(value):
    """Parse a strictly positive command-line integer."""
    parsed = int(value)
    if parsed < 1:
        raise ValueError("value must be positive")
    return parsed


def valid_week(value):
    """Parse and normalize an ISO date that falls on Tuesday."""
    parsed = date.fromisoformat(value)
    if parsed.weekday() != 1:
        raise ValueError("week must be a Tuesday")
    return parsed.isoformat()


def describe_target(args):
    """Render the supplied repair bounds for results and safety checks."""
    parts = []
    if getattr(args, "week", None): parts.append(f"week={args.week}")
    if getattr(args, "appid", None): parts.append(f"appid={args.appid}")
    if getattr(args, "limit", None): parts.append(f"limit={args.limit}")
    return ",".join(parts) or "unbounded"


def require_apply_bound(args):
    """Reject an applied repair without a week, app ID, or row limit."""
    target = describe_target(args)
    if args.apply and target == "unbounded":
        raise ValueError("repair application requires --week, --appid, or --limit")
    return target
