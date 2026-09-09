"""Tests for the generated Python command catalog."""

from __future__ import annotations

import argparse
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

import command_catalog


class CommandCatalogTests(unittest.TestCase):
    def test_inventory_is_complete(self):
        command_catalog.validate_registry()
        self.assertEqual(
            {command.identity for command in command_catalog.COMMANDS},
            {"extract", "validate", "apply-csv", "resolve-tags", "repair-ratings", "repair-rating-labels", "repair-prices", "repair-weekly-stats", "repair-game-names", "repair-game-tags", "repair-weekly-identities"},
        )

    def test_every_parser_exposes_structured_arguments(self):
        inspected = {command.identity: command_catalog.inspect_arguments(command) for command in command_catalog.COMMANDS}
        extraction_arguments = {argument.names[0]: argument for argument in inspected["extract"]}
        self.assertIn("start_date", extraction_arguments)
        self.assertIn("end_date", extraction_arguments)
        self.assertEqual(extraction_arguments["start_date"].nargs, "?")
        self.assertEqual(extraction_arguments["end_date"].nargs, "?")
        self.assertIn("csv", {argument.names[0] for argument in inspected["apply-csv"]})
        mapping = next(argument for argument in inspected["resolve-tags"] if "--map" in argument.names)
        self.assertTrue(mapping.repeatable)
        field = next(argument for argument in inspected["repair-weekly-stats"] if "--field" in argument.names)
        self.assertEqual(field.choices, ("all", "last-week-rank", "consecutive-weeks"))
        game_names = {argument.names[0]: argument for argument in inspected["repair-game-names"]}
        self.assertEqual(set(game_names), {"-h", "--appid", "--limit", "--apply"})
        self.assertFalse(game_names["--appid"].required)
        self.assertFalse(game_names["--limit"].required)
        weekly_identities = {argument.names[0]: argument for argument in inspected["repair-weekly-identities"]}
        self.assertEqual(set(weekly_identities), {"-h", "--week", "--apply"})
        self.assertFalse(weekly_identities["--week"].required)

    def test_registry_rejects_duplicates_missing_commands_and_bad_parser(self):
        with self.assertRaisesRegex(ValueError, "duplicate command identities"):
            command_catalog.validate_registry((*command_catalog.COMMANDS, command_catalog.COMMANDS[0]))
        with self.assertRaisesRegex(ValueError, "missing=.*repair-prices"):
            command_catalog.validate_registry(tuple(command for command in command_catalog.COMMANDS if command.identity != "repair-prices"))
        broken = replace(command_catalog.COMMANDS[0], parser_module="missing_catalog_parser")
        with self.assertRaisesRegex(ValueError, "cannot expose parser metadata for extract"):
            command_catalog.validate_registry((broken, *command_catalog.COMMANDS[1:]))

    def test_aliases_require_unique_valid_replacements(self):
        bad = replace(command_catalog.ALIASES[0], replacement="missing")
        with self.assertRaisesRegex(ValueError, "invalid deprecated alias"):
            command_catalog.validate_registry(command_catalog.COMMANDS, (bad, *command_catalog.ALIASES[1:]))
        with self.assertRaisesRegex(ValueError, "duplicate deprecated alias"):
            command_catalog.validate_registry(command_catalog.COMMANDS, (*command_catalog.ALIASES, command_catalog.ALIASES[0]))

    def test_render_is_deterministic_complete_and_separates_aliases(self):
        first = command_catalog.render_catalog()
        self.assertEqual(first, command_catalog.render_catalog())
        for command in command_catalog.COMMANDS:
            self.assertIn(f"### `{command.invocation}`", first)
        primary, aliases = first.split("## Deprecated compatibility aliases", 1)
        self.assertNotIn("upsert-csv", primary)
        self.assertIn("upsert-csv", aliases)
        self.assertIn("PIPELINE_MAX_ENTRIES", primary)
        self.assertIn("--approved", primary)
        self.assertNotIn("No additional description provided", primary)

    def test_generation_constructs_parsers_without_dispatching_handlers(self):
        with patch("UpdateDB.dispatch", side_effect=AssertionError("handler dispatched")), \
             patch("db.psycopg2.connect", side_effect=AssertionError("database accessed")):
            rendered = command_catalog.render_catalog()
        self.assertIn("# Python command catalog", rendered)

    def test_committed_catalog_is_fresh(self):
        command_catalog.assert_catalog_fresh()

    def test_freshness_failure_is_actionable(self):
        with TemporaryDirectory() as directory:
            stale = Path(directory) / "commands.md"
            stale.write_text("old", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "python Python/generate_command_catalog.py"):
                command_catalog.assert_catalog_fresh(stale, renderer=lambda: "new")


if __name__ == "__main__":
    unittest.main()
