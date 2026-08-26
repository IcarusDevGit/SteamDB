"""Shared repair argument and target helpers."""

from __future__ import annotations

from datetime import date


def add_target_arguments(parser, *, week_optional=True):
    parser.add_argument("--week", type=valid_week, required=not week_optional)
    parser.add_argument("--appid", type=positive_int)
    parser.add_argument("--limit", type=positive_int)
    parser.add_argument("--apply", action="store_true", help="Apply validated repairs; default is dry-run")


def positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise ValueError("value must be positive")
    return parsed


def valid_week(value):
    parsed = date.fromisoformat(value)
    if parsed.weekday() != 1:
        raise ValueError("week must be a Tuesday")
    return parsed.isoformat()


def describe_target(args):
    parts = []
    if getattr(args, "week", None): parts.append(f"week={args.week}")
    if getattr(args, "appid", None): parts.append(f"appid={args.appid}")
    if getattr(args, "limit", None): parts.append(f"limit={args.limit}")
    return ",".join(parts) or "unbounded"


def require_apply_bound(args):
    target = describe_target(args)
    if args.apply and target == "unbounded":
        raise ValueError("repair application requires --week, --appid, or --limit")
    return target
