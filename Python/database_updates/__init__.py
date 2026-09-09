"""Explicit database update command registry."""

from . import apply_validated_csv, resolve_csv_tags
from .repairs import game_names, game_tags, prices, rating_labels, ratings, weekly_identities, weekly_stats

APPLY_COMMANDS = (apply_validated_csv,)
REPAIR_COMMANDS = (ratings, rating_labels, prices, weekly_stats, game_names, game_tags, weekly_identities)
RESOLVE_COMMANDS = (resolve_csv_tags,)

__all__ = ["APPLY_COMMANDS", "REPAIR_COMMANDS", "RESOLVE_COMMANDS"]
