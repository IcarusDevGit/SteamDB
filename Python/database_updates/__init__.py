"""Explicit database update command registry."""

from . import apply_validated_csv, resolve_csv_tags
from .repairs import prices, ratings, weekly_stats

APPLY_COMMANDS = (apply_validated_csv,)
REPAIR_COMMANDS = (ratings, prices, weekly_stats)
RESOLVE_COMMANDS = (resolve_csv_tags,)

__all__ = ["APPLY_COMMANDS", "REPAIR_COMMANDS", "RESOLVE_COMMANDS"]
