"""Thin command-line dispatcher for approved updates and targeted repairs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from database_updates import APPLY_COMMANDS, REPAIR_COMMANDS
from database_updates import apply_validated_csv
from database_updates.repairs import prices, ratings, weekly_stats

# Compatibility imports for callers of the former focused updater module.
load_approved_csv = apply_validated_csv.load_validated_csv
apply_csv = apply_validated_csv.apply_csv


def _legacy_csv(args, dependencies=None):
    args.csv = args.csv_option
    return apply_validated_csv.run(args, dependencies)


def _legacy_weekly(field):
    def handler(args, dependencies=None):
        args.field = field
        return weekly_stats.run(args, dependencies)
    return handler


def _register_legacy_aliases(subparsers):
    csv_parser = subparsers.add_parser("upsert-csv", help=argparse.SUPPRESS)
    csv_parser.add_argument("--csv", dest="csv_option", type=Path, required=True)
    csv_parser.add_argument("--validation-report", type=Path)
    csv_parser.add_argument("--approved", action="store_true")
    csv_parser.set_defaults(handler=_legacy_csv)

    for name, module in (("update-null-ratings", ratings), ("update-null-prices", prices)):
        parser = subparsers.add_parser(name, help=argparse.SUPPRESS)
        from database_updates.repairs.common import add_target_arguments
        add_target_arguments(parser)
        parser.set_defaults(handler=module.run)

    for name, field in (
        ("update-last-week-rank", "last-week-rank"),
        ("update_last_week_rank", "last-week-rank"),
        ("update-consecutive-weeks", "consecutive-weeks"),
        ("update_consecutive_weeks", "consecutive-weeks"),
    ):
        parser = subparsers.add_parser(name, help=argparse.SUPPRESS)
        from database_updates.repairs.common import positive_int, valid_week
        parser.add_argument("--week", "--date", dest="week", type=valid_week, required=True)
        parser.add_argument("--limit", type=positive_int)
        parser.add_argument("--apply", action="store_true")
        parser.set_defaults(handler=_legacy_weekly(field))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply reviewed data or run bounded database repairs")
    commands = parser.add_subparsers(dest="command", required=True)

    apply_parser = commands.add_parser("apply", help="Apply reviewed data")
    apply_commands = apply_parser.add_subparsers(dest="apply_command", required=True)
    for module in APPLY_COMMANDS:
        module.register_parser(apply_commands)

    repair_parser = commands.add_parser("repair", help="Inspect or apply a targeted repair")
    repair_commands = repair_parser.add_subparsers(dest="repair_command", required=True)
    for module in REPAIR_COMMANDS:
        module.register_parser(repair_commands)

    _register_legacy_aliases(commands)
    return parser


def dispatch(argv=None, *, dependencies=None):
    values = list(sys.argv[1:] if argv is None else argv)
    # Preserve the promoted prototype's ``UpdateDB.py file.csv --approved`` invocation.
    if values and values[0] not in {
        "apply", "repair", "upsert-csv", "update-null-ratings", "update-null-prices",
        "update-last-week-rank", "update_last_week_rank",
        "update-consecutive-weeks", "update_consecutive_weeks", "-h", "--help",
    }:
        values = ["apply", "csv", *values]
    args = build_parser().parse_args(values)
    return args.handler(args, dependencies)


def main(argv=None, *, dependencies=None) -> int:
    try:
        result = dispatch(argv, dependencies=dependencies)
    except (OSError, PermissionError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(result.render())
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
