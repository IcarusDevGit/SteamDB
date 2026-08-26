import argparse
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import UpdateDB
from database_updates.apply_validated_csv import REQUIRED_FIELDS, load_validated_csv
from database_updates.common import UpdateResult, merge_results
from database_updates.repairs import prices, ratings, weekly_stats


class FakeClients:
    async def rating(self, appid, week):
        if appid == 2:
            raise RuntimeError("provider failed")
        return None if appid == 3 else 0.75

    async def itad_lookup(self, appids):
        return {appid: f"itad-{appid}" for appid in appids}

    async def itad_history(self, itad_id, week):
        if itad_id == "itad-2":
            raise RuntimeError("history failed")
        return (None, None) if itad_id == "itad-3" else (9.99, 20)

    async def steam_html(self, appid):
        from workflow_models import StoreData
        return StoreData() if appid == 3 else StoreData(price=19.99, discount=0)

    async def weekly(self, week):
        return [{"rank": 1, "last_week_rank": 2, "consecutive_weeks": 3}]


class DatabaseUpdateTests(unittest.TestCase):
    def test_result_aggregation_and_exit_status(self):
        combined = merge_results(
            "repair", "week=x",
            [UpdateResult("a", "x", proposed=2, applied=1), UpdateResult("b", "x", skipped=1, failed=1)],
        )
        self.assertEqual((combined.proposed, combined.applied, combined.skipped, combined.failed), (2, 1, 1, 1))
        self.assertEqual(combined.exit_code, 1)

    def _write(self, row=None, fields=None):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "input.csv"
        values = {
            "week_date": "2026-08-04", "rank": "1", "appid": "10", "name": "Game",
            "tags": "Action", "tag_ids": "1", "unresolved_tags": "", "rating": "0.8",
            "price": "9.99", "discount": "20", "last_week_rank": "2",
            "consecutive_weeks": "3", "errors": "",
        }
        values.update(row or {})
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields or sorted(REQUIRED_FIELDS))
            writer.writeheader()
            writer.writerow({key: values.get(key, "") for key in writer.fieldnames})
        self.addCleanup(directory.cleanup)
        return path

    def test_csv_validation_rejects_structural_and_semantic_errors(self):
        cases = [
            ({}, sorted(REQUIRED_FIELDS - {"appid"})),
            ({"week_date": "2026-08-05"}, None),
            ({"rank": "101"}, None),
            ({"appid": "0"}, None),
            ({"tag_ids": "1,2", "tags": "Action"}, None),
            ({"unresolved_tags": "Mystery"}, None),
            ({"errors": "provider timeout"}, None),
            ({"rating": "1.5"}, None),
            ({"discount": "101"}, None),
        ]
        for row, fields in cases:
            with self.subTest(row=row, fields=fields):
                with self.assertRaises(ValueError):
                    load_validated_csv(self._write(row, fields))

    def test_csv_validation_accepts_last_week_rank_above_chart_size(self):
        records = load_validated_csv(self._write({"last_week_rank": "147"}))
        self.assertEqual(records[0]["last_week_rank"], 147)

    def test_repair_defaults_to_dry_run_and_reports_mixed_outcomes(self):
        database = Mock()
        database.find_missing_ratings.return_value = [
            {"appid": value, "week_date": "2026-08-04"} for value in (1, 2, 3)
        ]
        args = argparse.Namespace(week="2026-08-04", appid=None, limit=None, apply=False)
        result = ratings.run(args, {"database": database, "clients": FakeClients()})
        self.assertEqual((result.proposed, result.applied, result.skipped, result.failed), (1, 0, 1, 1))
        database.apply_rating_repairs.assert_not_called()

    def test_repair_apply_requires_a_bound(self):
        args = argparse.Namespace(week=None, appid=None, limit=None, apply=True)
        with self.assertRaises(ValueError):
            ratings.run(args, {"database": Mock(), "clients": FakeClients()})

    def test_price_discovery_finishes_before_one_apply_call(self):
        database = Mock()
        database.find_missing_prices.return_value = [
            {"appid": value, "week_date": "2026-08-04"} for value in (1, 2, 3)
        ]
        database.apply_price_repairs.return_value = 1
        args = argparse.Namespace(week="2026-08-04", appid=None, limit=None, apply=True)
        result = prices.run(args, {"database": database, "clients": FakeClients()})
        database.apply_price_repairs.assert_called_once()
        self.assertEqual((result.applied, result.skipped, result.failed), (1, 1, 1))

    def test_weekly_stats_is_a_function_registered_command(self):
        database = Mock()
        database.apply_weekly_stat_repairs.return_value = 1
        args = argparse.Namespace(week="2026-08-04", limit=None, field="all", apply=True)
        result = weekly_stats.run(args, {"database": database, "clients": FakeClients()})
        self.assertEqual(result.applied, 1)
        parser = UpdateDB.build_parser()
        parsed = parser.parse_args(["repair", "weekly-stats", "--week", "2026-08-04"])
        self.assertIs(parsed.handler, weekly_stats.run)

    def test_unknown_repair_is_rejected_before_dispatch(self):
        with self.assertRaises(SystemExit):
            UpdateDB.build_parser().parse_args(["repair", "unknown"])

    def test_legacy_repair_aliases_use_active_handlers(self):
        parser = UpdateDB.build_parser()
        rating_alias = parser.parse_args(["update-null-ratings", "--week", "2026-08-04"])
        price_alias = parser.parse_args(["update-null-prices", "--appid", "10"])
        self.assertIs(rating_alias.handler, ratings.run)
        self.assertIs(price_alias.handler, prices.run)
        weekly_alias = parser.parse_args(["update_last_week_rank", "--date", "2026-08-04"])
        database = Mock()
        result = weekly_alias.handler(weekly_alias, {"database": database, "clients": FakeClients()})
        self.assertEqual(result.proposed, 1)
        database.apply_weekly_stat_repairs.assert_not_called()

    def test_documented_commands_parse(self):
        parser = UpdateDB.build_parser()
        commands = (
            ["apply", "csv", "helpers/example.csv", "--approved"],
            ["repair", "ratings", "--week", "2026-08-04"],
            ["repair", "ratings", "--appid", "730", "--apply"],
            ["repair", "prices", "--week", "2026-08-04", "--limit", "20", "--apply"],
            ["repair", "weekly-stats", "--week", "2026-08-04", "--apply"],
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(callable(parser.parse_args(command).handler))


if __name__ == "__main__":
    unittest.main()
