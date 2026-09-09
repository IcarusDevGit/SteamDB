"""Test update parsing, repair discovery, dry runs, and command registration."""

import argparse
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

import UpdateDB
from database_updates.apply_validated_csv import REQUIRED_FIELDS, load_validated_csv
from database_updates.common import UpdateResult, merge_results
from database_updates.repairs import game_names, game_tags, prices, rating_labels, ratings, weekly_identities, weekly_stats


class FakeClients:
    """Return mixed provider outcomes for repair aggregation tests."""
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

    async def game_name(self, appid):
        if appid == 2:
            raise RuntimeError("name provider failed")
        return None if appid == 3 else f" Steam Game {appid} "

    async def rating_histogram(self, appid):
        if appid == 2:
            raise RuntimeError("histogram failed")
        return {"results": {"rollups": [
            {"date": 0, "recommendations_up": 8 if appid == 1 else 2,
             "recommendations_down": 2 if appid == 1 else 0},
        ]}}


class ScriptedCursor:
    """Record SQL while returning scripted rows and affected counts."""

    def __init__(self, *, rows=(), result_sets=None, rowcounts=(), failure=None):
        self.rows = list(rows)
        self.result_sets = [list(value) for value in (result_sets or [])]
        self.rowcounts = list(rowcounts)
        self.failure = failure
        self.calls = []
        self.rowcount = -1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params):
        self.calls.append((" ".join(statement.split()), params))
        if self.failure is not None:
            raise self.failure
        self.rowcount = self.rowcounts.pop(0) if self.rowcounts else -1

    def fetchall(self):
        return self.result_sets.pop(0) if self.result_sets else list(self.rows)


class ScriptedConnection:
    """Expose transaction state around one scripted cursor."""

    def __init__(self, cursor):
        self.cursor_value = cursor
        self.committed = self.rolled_back = self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class DatabaseUpdateTests(unittest.TestCase):
    """Cover validated CSV input and bounded database repair workflows."""
    def test_result_aggregation_and_exit_status(self):
        combined = merge_results(
            "repair", "week=x",
            [UpdateResult("a", "x", proposed=2, applied=1), UpdateResult("b", "x", skipped=1, failed=1)],
        )
        self.assertEqual((combined.proposed, combined.applied, combined.skipped, combined.failed), (2, 1, 1, 1))
        self.assertEqual(combined.exit_code, 1)

    def _write(self, row=None, fields=None):
        """Create one cleanup-managed CSV with optional invalid overrides."""
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

    def test_csv_rating_label_validation_distinguishes_missing_and_no_label(self):
        self.assertIsNone(load_validated_csv(self._write({"rating_label": ""}))[0]["rating_label"])
        self.assertEqual(
            load_validated_csv(self._write({"rating_label": "no_label"}))[0]["rating_label"],
            "no_label",
        )
        with self.assertRaisesRegex(ValueError, "invalid rating_label"):
            load_validated_csv(self._write({"rating_label": "Unknown"}))

    def test_rating_and_price_candidate_sql_owns_filters_limits_and_closure(self):
        rating_cursor = ScriptedCursor(rows=[(10, "2026-08-04")])
        rating_connection = ScriptedConnection(rating_cursor)
        candidates = ratings.find_candidates(
            week="2026-08-04", appid=10, limit=1,
            connection_factory=lambda: rating_connection,
        )
        self.assertEqual(candidates, [{"appid": 10, "week_date": "2026-08-04"}])
        rating_sql, rating_params = rating_cursor.calls[0]
        self.assertIn("rating IS NULL", rating_sql)
        self.assertIn("week_date = %s", rating_sql)
        self.assertIn("game_id = %s", rating_sql)
        self.assertTrue(rating_sql.endswith("LIMIT %s"))
        self.assertEqual(rating_params, ("2026-08-04", 10, 1))
        self.assertTrue(rating_connection.closed)

        price_cursor = ScriptedCursor(rows=[(20, "2026-08-11")])
        price_connection = ScriptedConnection(price_cursor)
        prices.find_candidates(connection_factory=lambda: price_connection)
        price_sql, price_params = price_cursor.calls[0]
        self.assertIn("price IS NULL OR discount IS NULL", price_sql)
        self.assertEqual(price_params, ())
        self.assertTrue(price_connection.closed)

    def test_rating_and_price_updates_are_guarded_counted_and_transactional(self):
        rating_cursor = ScriptedCursor(rowcounts=[1, 0])
        rating_connection = ScriptedConnection(rating_cursor)
        applied = ratings.apply_updates(
            [
                {"rating": 0.9, "week_date": "2026-08-04", "appid": 10},
                {"rating": 0.8, "week_date": "2026-08-04", "appid": 20},
            ],
            connection_factory=lambda: rating_connection,
        )
        self.assertEqual(applied, 1)
        self.assertIn("rating IS NULL", rating_cursor.calls[0][0])
        self.assertTrue(rating_connection.committed)
        self.assertFalse(rating_connection.rolled_back)
        self.assertTrue(rating_connection.closed)

        failure = RuntimeError("price update failed")
        price_cursor = ScriptedCursor(failure=failure)
        price_connection = ScriptedConnection(price_cursor)
        with self.assertRaisesRegex(RuntimeError, "price update failed"):
            prices.apply_updates(
                [{"price": 5.0, "discount": 50, "week_date": "2026-08-04", "appid": 10}],
                connection_factory=lambda: price_connection,
            )
        self.assertIn("COALESCE(price, %s)", price_cursor.calls[0][0])
        self.assertIn("price IS NULL OR discount IS NULL", price_cursor.calls[0][0])
        self.assertTrue(price_connection.rolled_back)
        self.assertFalse(price_connection.committed)
        self.assertTrue(price_connection.closed)

    def test_weekly_stat_updates_cover_field_variants_counts_and_rollback(self):
        cursor = ScriptedCursor(rowcounts=[1, 1, 0])
        connection = ScriptedConnection(cursor)
        applied = weekly_stats.apply_updates(
            [
                {"week_date": "2026-08-04", "rank": 1, "last_week_rank": 2, "consecutive_weeks": 3},
                {"week_date": "2026-08-04", "rank": 2, "last_week_rank": 4},
                {"week_date": "2026-08-04", "rank": 3, "consecutive_weeks": 5},
            ],
            connection_factory=lambda: connection,
        )
        self.assertEqual(applied, 2)
        self.assertIn("last_week_rank = %s, consecutive_weeks = %s", cursor.calls[0][0])
        self.assertIn("SET last_week_rank = %s", cursor.calls[1][0])
        self.assertIn("SET consecutive_weeks = %s", cursor.calls[2][0])
        self.assertTrue(connection.committed)
        self.assertTrue(connection.closed)

        failed_cursor = ScriptedCursor(failure=RuntimeError("weekly update failed"))
        failed_connection = ScriptedConnection(failed_cursor)
        with self.assertRaisesRegex(RuntimeError, "weekly update failed"):
            weekly_stats.apply_updates(
                [{"week_date": "2026-08-04", "rank": 1, "last_week_rank": 2}],
                connection_factory=lambda: failed_connection,
            )
        self.assertTrue(failed_connection.rolled_back)
        self.assertTrue(failed_connection.closed)

    def test_game_name_candidate_sql_defaults_to_whitespace_names_and_supports_bounds(self):
        cursor = ScriptedCursor(rows=[(10, ""), (20, "   ")])
        connection = ScriptedConnection(cursor)
        candidates = game_names.find_candidates(connection_factory=lambda: connection)
        self.assertEqual(candidates, [
            {"appid": 10, "current_name": ""},
            {"appid": 20, "current_name": "   "},
        ])
        self.assertEqual(cursor.calls[0], ("SELECT id, name FROM games WHERE BTRIM(name) = '' ORDER BY id", ()))
        self.assertTrue(connection.closed)

        bounded_cursor = ScriptedCursor(rows=[(20, "Existing")])
        bounded_connection = ScriptedConnection(bounded_cursor)
        game_names.find_candidates(
            appid=20, limit=1, connection_factory=lambda: bounded_connection,
        )
        sql, params = bounded_cursor.calls[0]
        self.assertEqual(sql, "SELECT id, name FROM games WHERE BTRIM(name) = '' AND id = %s ORDER BY id LIMIT %s")
        self.assertEqual(params, (20, 1))
        self.assertTrue(bounded_connection.closed)

    def test_game_name_updates_are_whitespace_guarded_and_transactional(self):
        cursor = ScriptedCursor(rowcounts=[1, 0])
        connection = ScriptedConnection(cursor)
        applied = game_names.apply_updates(
            [{"appid": 10, "name": "New Name"}, {"appid": 999, "name": "Missing"}],
            connection_factory=lambda: connection,
        )
        self.assertEqual(applied, 1)
        self.assertEqual(cursor.calls[0], ("UPDATE games SET name = %s WHERE id = %s AND BTRIM(name) = '';", ("New Name", 10)))
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertTrue(connection.closed)

        failed_cursor = ScriptedCursor(failure=RuntimeError("name update failed"))
        failed_connection = ScriptedConnection(failed_cursor)
        with self.assertRaisesRegex(RuntimeError, "name update failed"):
            game_names.apply_updates(
                [{"appid": 10, "name": "New Name"}],
                connection_factory=lambda: failed_connection,
            )
        self.assertTrue(failed_connection.rolled_back)
        self.assertFalse(failed_connection.committed)
        self.assertTrue(failed_connection.closed)

    def test_game_name_repair_defaults_to_whitespace_names_dry_run_and_can_apply(self):
        candidates = [
            {"appid": value, "current_name": "" if value == 1 else "   "}
            for value in (1, 2, 3)
        ]
        dry_args = argparse.Namespace(appid=None, limit=None, apply=False)
        with (
            patch.object(game_names, "find_candidates", return_value=candidates) as find,
            patch.object(game_names, "apply_updates") as apply,
        ):
            result = game_names.run(dry_args, {"clients": FakeClients()})
        find.assert_called_once_with(appid=None, limit=None, connection_factory=ANY)
        apply.assert_not_called()
        self.assertEqual(result.target, "whitespace-names")
        self.assertEqual((result.proposed, result.applied, result.skipped, result.failed), (1, 0, 1, 1))

        apply_args = argparse.Namespace(appid=None, limit=None, apply=True)
        with (
            patch.object(game_names, "find_candidates", return_value=[candidates[0]]),
            patch.object(game_names, "apply_updates", return_value=1) as apply,
        ):
            result = game_names.run(apply_args, {"clients": FakeClients()})
        apply.assert_called_once_with(
            [{"appid": 1, "name": "Steam Game 1"}], connection_factory=ANY, reporter=None,
        )
        self.assertEqual((result.target, result.applied), ("whitespace-names", 1))

    def test_repair_defaults_to_dry_run_and_reports_mixed_outcomes(self):
        candidates = [
            {"appid": value, "week_date": "2026-08-04"} for value in (1, 2, 3)
        ]
        args = argparse.Namespace(week="2026-08-04", appid=None, limit=None, apply=False)
        with (
            patch.object(ratings, "find_candidates", return_value=candidates),
            patch.object(ratings, "apply_updates") as apply,
        ):
            result = ratings.run(args, {"clients": FakeClients()})
        self.assertEqual((result.proposed, result.applied, result.skipped, result.failed), (1, 0, 1, 1))
        apply.assert_not_called()

    def test_repair_apply_requires_a_bound(self):
        args = argparse.Namespace(week=None, appid=None, limit=None, apply=True)
        with self.assertRaises(ValueError):
            ratings.run(args, {"clients": FakeClients()})

    def test_rating_label_repair_groups_games_and_allows_full_set_apply(self):
        candidates = [
            {"appid": 1, "week_date": "2026-08-04"},
            {"appid": 1, "week_date": "2026-08-11"},
            {"appid": 2, "week_date": "2026-08-04"},
            {"appid": 3, "week_date": "2026-08-04"},
        ]
        clients = FakeClients()
        clients.rating_histogram = Mock(side_effect=clients.rating_histogram)
        args = argparse.Namespace(week=None, appid=None, limit=None, apply=True)
        with (
            patch.object(rating_labels, "find_candidates", return_value=candidates) as find,
            patch.object(rating_labels, "apply_updates", return_value=3) as apply,
        ):
            result = rating_labels.run(args, {"clients": clients})
        find.assert_called_once_with(week=None, appid=None, limit=None, connection_factory=ANY)
        self.assertEqual(clients.rating_histogram.call_count, 3)
        apply.assert_called_once()
        updates = apply.call_args.args[0]
        self.assertEqual([row["rating_label"] for row in updates],
                         ["Positive", "Positive", "no_label"])
        self.assertEqual((result.target, result.proposed, result.applied, result.failed),
                         ("all-null-rating-labels", 3, 3, 1))

    def test_rating_label_candidate_query_and_bulk_guard(self):
        cursor = ScriptedCursor(rows=[(10, "2026-08-04")])
        connection = ScriptedConnection(cursor)
        rows = rating_labels.find_candidates(
            week="2026-08-04", appid=10, limit=1,
            connection_factory=lambda: connection,
        )
        self.assertEqual(rows, [{"appid": 10, "week_date": "2026-08-04"}])
        self.assertEqual(len(cursor.calls), 1)
        self.assertIn("rating_label IS NULL", cursor.calls[0][0])
        self.assertEqual(cursor.calls[0][1], ("2026-08-04", 10, 1))

        bulk_cursor = ScriptedCursor()
        bulk_cursor.rowcount = 1
        bulk_connection = ScriptedConnection(bulk_cursor)
        with patch.object(rating_labels, "execute_values") as bulk:
            def execute(cursor_arg, statement, values, page_size):
                self.assertIn("rating_label IS NULL", statement)
                self.assertEqual(values, [("2026-08-04", 10, "no_label")])
                cursor_arg.rowcount = 1
            bulk.side_effect = execute
            applied = rating_labels.apply_updates(
                [{"week_date": "2026-08-04", "appid": 10, "rating_label": "no_label"}],
                connection_factory=lambda: bulk_connection,
            )
        self.assertEqual(applied, 1)
        bulk.assert_called_once()
        self.assertTrue(bulk_connection.committed)

    def test_price_discovery_finishes_before_one_apply_call(self):
        candidates = [
            {"appid": value, "week_date": "2026-08-04"} for value in (1, 2, 3)
        ]
        args = argparse.Namespace(week="2026-08-04", appid=None, limit=None, apply=True)
        with (
            patch.object(prices, "find_candidates", return_value=candidates),
            patch.object(prices, "apply_updates", return_value=1) as apply,
        ):
            result = prices.run(args, {"clients": FakeClients()})
        apply.assert_called_once()
        self.assertEqual((result.applied, result.skipped, result.failed), (1, 1, 1))

    def test_weekly_stats_is_a_function_registered_command(self):
        args = argparse.Namespace(week="2026-08-04", limit=None, field="all", apply=True)
        with patch.object(weekly_stats, "apply_updates", return_value=1):
            result = weekly_stats.run(args, {"clients": FakeClients()})
        self.assertEqual(result.applied, 1)
        parser = UpdateDB.build_parser()
        parsed = parser.parse_args(["repair", "weekly-stats", "--week", "2026-08-04"])
        self.assertIs(parsed.handler, weekly_stats.run)

    def test_game_names_is_registered_and_accepts_default_candidate_apply(self):
        parser = UpdateDB.build_parser()
        parsed = parser.parse_args(["repair", "game-names", "--apply"])
        self.assertIs(parsed.handler, game_names.run)
        self.assertTrue(parsed.apply)
        self.assertIsNone(parsed.appid)
        self.assertIsNone(parsed.limit)
        narrowed = parser.parse_args(["repair", "game-names", "--appid", "730", "--limit", "5"])
        self.assertEqual((narrowed.appid, narrowed.limit), (730, 5))
        with self.assertRaises(SystemExit):
            parser.parse_args(["repair", "game-names", "--week", "2026-08-04"])

    def test_weekly_identity_state_comparison_and_targeting(self):
        cursor = ScriptedCursor(result_sets=[
            [("2026-08-04", 1, 10, 9.99, 20, 0.8, "Very Positive"),
             ("2026-08-04", 2, 20, 5.0, 0, 0.9, "Positive")],
            [(10,), (20,), (30,)],
        ])
        connection = ScriptedConnection(cursor)
        stored, catalog = weekly_identities.load_state(
            week="2026-08-04", connection_factory=lambda: connection,
        )
        self.assertEqual(set(stored), {"2026-08-04"})
        self.assertEqual(catalog, {10, 20, 30})
        self.assertIn("WHERE week_date = %s", cursor.calls[0][0])
        self.assertTrue(connection.closed)

        global_rows = [
            {"rank": 1, "appid": 20, "name": "Twenty", "last_week_rank": 3, "consecutive_weeks": 2},
            {"rank": 2, "appid": 30, "name": "Thirty", "last_week_rank": None, "consecutive_weeks": 1},
        ]
        plan = weekly_identities.build_plan("2026-08-04", stored["2026-08-04"], global_rows, catalog)
        self.assertEqual(plan.missing, ((2, 30),))
        self.assertEqual(plan.unexpected, ((1, 10),))
        self.assertEqual(plan.moved, ((20, 2, 1),))
        self.assertEqual(plan.unchanged, 0)
        retained = next(row for row in plan.rows if row["appid"] == 20)
        inserted = next(row for row in plan.rows if row["appid"] == 30)
        self.assertEqual((retained["price"], retained["discount"], retained["rating"]), (5.0, 0, 0.9))
        self.assertEqual(retained["rating_label"], "Positive")
        self.assertEqual((inserted["price"], inserted["discount"], inserted["rating"]), (None, None, None))

    def test_weekly_identity_reconciliation_is_atomic_and_catalog_preserving(self):
        plan = weekly_identities.WeekPlan(
            "2026-08-04",
            ({"week_date": "2026-08-04", "rank": 1, "appid": 20, "name": "Twenty",
              "price": 5.0, "discount": 0, "rating": 0.9, "rating_label": "Positive",
              "last_week_rank": 3, "consecutive_weeks": 2},),
            ((1, 20),), ((1, 10),), (), 0,
        )
        cursor = ScriptedCursor()
        connection = ScriptedConnection(cursor)
        events = []

        def report(event):
            self.assertFalse(connection.committed)
            events.append(event)

        self.assertEqual(weekly_identities.apply_plans(
            [plan], connection_factory=lambda: connection, reporter=report,
        ), 1)
        statements = [call[0] for call in cursor.calls]
        self.assertTrue(any("ON CONFLICT (id) DO NOTHING" in sql for sql in statements))
        self.assertTrue(any("DELETE FROM weeksheet" in sql for sql in statements))
        self.assertTrue(any("rank = rank + 1000000" in sql for sql in statements))
        self.assertTrue(any("ON CONFLICT (week_date, game_id) DO UPDATE" in sql for sql in statements))
        self.assertTrue(connection.committed)
        self.assertTrue(connection.closed)
        self.assertEqual(
            [
                (event.kind, event.fields["phase"], event.fields["completed"],
                 event.fields["total"], event.fields["identity"])
                for event in events
            ],
            [
                ("persistence_progress", "catalog", 1, 1, "week=2026-08-04"),
                ("persistence_progress", "weekly_reconciliation", 1, 1, "week=2026-08-04"),
            ],
        )

        failed_cursor = ScriptedCursor(failure=RuntimeError("reconcile failed"))
        failed_connection = ScriptedConnection(failed_cursor)
        with self.assertRaisesRegex(RuntimeError, "reconcile failed"):
            weekly_identities.apply_plans([plan], connection_factory=lambda: failed_connection)
        self.assertTrue(failed_connection.rolled_back)
        self.assertTrue(failed_connection.closed)

    def test_all_row_repairs_report_persistence_before_commit_and_rollback_on_reporter_failure(self):
        cases = [
            (ratings.apply_updates, {"rating": .8, "week_date": "2026-08-04", "appid": 10}, "repair_ratings"),
            (prices.apply_updates, {"price": 5, "discount": 10, "week_date": "2026-08-04", "appid": 10}, "repair_prices"),
            (weekly_stats.apply_updates, {"last_week_rank": 2, "week_date": "2026-08-04", "rank": 1}, "repair_weekly_stats"),
            (game_names.apply_updates, {"name": "Ten", "appid": 10}, "repair_game_names"),
        ]
        for apply, row, operation in cases:
            with self.subTest(operation=operation):
                connection = ScriptedConnection(ScriptedCursor(rowcounts=[1]))
                events = []

                def report(event):
                    self.assertFalse(connection.committed)
                    events.append(event)

                self.assertEqual(apply(
                    [row], connection_factory=lambda: connection, reporter=report,
                ), 1)
                self.assertEqual(events[0].kind, "persistence_progress")
                self.assertEqual(events[0].fields["operation"], operation)
                self.assertEqual((events[0].fields["completed"], events[0].fields["total"]), (1, 1))
                self.assertTrue(connection.committed)

                failed = ScriptedConnection(ScriptedCursor(rowcounts=[1]))
                with self.assertRaisesRegex(RuntimeError, "report failed"):
                    apply(
                        [row], connection_factory=lambda: failed,
                        reporter=lambda event: (_ for _ in ()).throw(RuntimeError("report failed")),
                    )
                self.assertTrue(failed.rolled_back)
                self.assertFalse(failed.committed)

    def test_weekly_identity_dry_run_and_parser_cover_all_stored_weeks(self):
        stored = {"2026-08-04": [{"rank": 1, "appid": 10, "price": 1, "discount": 0, "rating": 0.5}]}
        expected = [{"rank": 1, "appid": 20, "name": "Twenty", "last_week_rank": 2, "consecutive_weeks": 1}]
        args = argparse.Namespace(week=None, apply=False)
        with (
            patch.object(weekly_identities, "load_state", return_value=(stored, {10, 20})),
            patch.object(weekly_identities, "apply_plans") as apply,
        ):
            result = weekly_identities.run(args, {"global_chart_fetcher": lambda week: ("url", expected)})
        self.assertEqual((result.target, result.proposed, result.applied), ("all-stored-weeks", 1, 0))
        self.assertIn("missing=1 unexpected=1 moved=0 unchanged=0", result.messages[0])
        apply.assert_not_called()

        parser = UpdateDB.build_parser()
        parsed = parser.parse_args(["repair", "weekly-identities", "--apply"])
        self.assertIs(parsed.handler, weekly_identities.run)
        self.assertTrue(parsed.apply)
        with self.assertRaises(SystemExit):
            parser.parse_args(["repair", "weekly-identities", "--appid", "10"])

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
        with patch.object(weekly_stats, "apply_updates") as apply:
            result = weekly_alias.handler(weekly_alias, {"clients": FakeClients()})
        self.assertEqual(result.proposed, 1)
        apply.assert_not_called()

    def test_documented_commands_parse(self):
        parser = UpdateDB.build_parser()
        commands = (
            ["apply", "csv", "helpers/example.csv", "--approved"],
            ["repair", "ratings", "--week", "2026-08-04"],
            ["repair", "ratings", "--appid", "730", "--apply"],
            ["repair", "prices", "--week", "2026-08-04", "--limit", "20", "--apply"],
            ["repair", "weekly-stats", "--week", "2026-08-04", "--apply"],
            ["repair", "game-names", "--apply"],
            ["repair", "game-tags", "--apply"],
            ["repair", "weekly-identities", "--week", "2026-08-04"],
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(callable(parser.parse_args(command).handler))


if __name__ == "__main__":
    unittest.main()
