"""Test empty catalog game-tag discovery, resolution, and persistence."""

import argparse
import asyncio
import unittest
from unittest.mock import ANY, patch

import UpdateDB
from database_updates.repairs import game_tags
from workflow_models import StoreData


class Cursor:
    def __init__(self, rows=(), rowcounts=(), failure=None):
        self.rows = list(rows)
        self.rowcounts = list(rowcounts)
        self.failure = failure
        self.calls = []
        self.rowcount = -1

    def __enter__(self): return self
    def __exit__(self, *args): return False

    def execute(self, sql, params):
        self.calls.append((" ".join(sql.split()), params))
        if self.failure:
            raise self.failure
        self.rowcount = self.rowcounts.pop(0) if self.rowcounts else -1

    def fetchall(self): return list(self.rows)


class Connection:
    def __init__(self, cursor):
        self.value = cursor
        self.committed = self.rolled_back = self.closed = False

    def cursor(self): return self.value
    def commit(self): self.committed = True
    def rollback(self): self.rolled_back = True
    def close(self): self.closed = True


class Clients:
    async def steam_html(self, appid):
        if appid == 4:
            raise RuntimeError("Steam failed")
        values = {
            1: ["Action", "action", "Unknown"],
            2: ["Mystery"],
            3: [],
        }
        return StoreData(tags=values[appid])


class GameTagRepairTests(unittest.TestCase):
    def test_candidate_query_covers_null_and_empty_with_optional_bounds(self):
        cursor = Cursor(rows=[(730,)])
        connection = Connection(cursor)
        self.assertEqual(
            game_tags.find_candidates(appid=730, limit=1, connection_factory=lambda: connection),
            [{"appid": 730}],
        )
        sql, params = cursor.calls[0]
        self.assertIn("COALESCE(cardinality(tags), 0) = 0", sql)
        self.assertIn("AND id = %s", sql)
        self.assertIn("ORDER BY id", sql)
        self.assertTrue(sql.endswith("LIMIT %s"))
        self.assertEqual(params, (730, 1))
        self.assertTrue(connection.closed)

    def test_default_target_and_parser_allow_unbounded_apply(self):
        parser = UpdateDB.build_parser()
        args = parser.parse_args(["repair", "game-tags", "--apply"])
        self.assertIs(args.handler, game_tags.run)
        self.assertEqual(game_tags._target(args), "empty-tags")
        narrowed = parser.parse_args(["repair", "game-tags", "--appid", "730", "--limit", "5"])
        self.assertEqual((narrowed.appid, narrowed.limit), (730, 5))

    def test_discovery_resolves_unique_subset_and_isolates_outcomes(self):
        rows = [{"appid": value} for value in (1, 2, 3, 4)]
        results = asyncio.run(game_tags.discover(
            rows, Clients(), {"Action": 19}, exceptions={},
        ))
        first = results[0][1]
        self.assertEqual((first.ids, first.names, first.unresolved), ([19], ["Action"], ["Unknown"]))
        self.assertEqual(results[1][1].unresolved, ["Mystery"])
        self.assertFalse(results[2][1].ids)
        self.assertEqual(results[3][2], "Steam failed")

    def test_updates_are_guarded_counted_atomic_and_observable(self):
        cursor = Cursor(rowcounts=[1, 0])
        connection = Connection(cursor)
        events = []
        applied = game_tags.apply_updates(
            [{"appid": 1, "tag_ids": [19]}, {"appid": 2, "tag_ids": [9]}],
            connection_factory=lambda: connection, reporter=events.append,
        )
        self.assertEqual(applied, 1)
        self.assertTrue(all("COALESCE(cardinality(tags), 0) = 0" in sql for sql, _ in cursor.calls))
        self.assertEqual(cursor.calls[0][1], ([19], 1))
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertTrue(connection.closed)
        self.assertEqual([event.fields["completed"] for event in events], [1, 2])

        failed = Connection(Cursor(failure=RuntimeError("write failed")))
        with self.assertRaisesRegex(RuntimeError, "write failed"):
            game_tags.apply_updates(
                [{"appid": 1, "tag_ids": [19]}], connection_factory=lambda: failed,
            )
        self.assertTrue(failed.rolled_back)
        self.assertFalse(failed.committed)
        self.assertTrue(failed.closed)
        self.assertEqual(game_tags.apply_updates([], connection_factory=lambda: None), 0)

    def test_run_dry_run_and_apply_report_mixed_results(self):
        candidates = [{"appid": value} for value in (1, 2, 3, 4)]
        dry = argparse.Namespace(appid=None, limit=None, apply=False)
        dependencies = {"clients": Clients(), "snapshot": {"tags_by_name": {"Action": 19}}, "exceptions": {}}
        with (
            patch.object(game_tags, "find_candidates", return_value=candidates) as find,
            patch.object(game_tags, "apply_updates") as apply,
        ):
            result = game_tags.run(dry, dependencies)
        find.assert_called_once_with(appid=None, limit=None, connection_factory=ANY)
        apply.assert_not_called()
        self.assertEqual((result.target, result.proposed, result.applied), ("empty-tags", 1, 0))
        self.assertEqual((result.skipped, result.failed), (2, 1))
        self.assertTrue(any("Unknown" in message for message in result.messages))
        self.assertTrue(any("Mystery" in message for message in result.messages))

        authorized = argparse.Namespace(appid=None, limit=None, apply=True)
        with (
            patch.object(game_tags, "find_candidates", return_value=[candidates[0]]),
            patch.object(game_tags, "apply_updates", return_value=1) as apply,
        ):
            result = game_tags.run(authorized, dependencies)
        apply.assert_called_once_with(
            [{"appid": 1, "tag_ids": [19]}], connection_factory=ANY, reporter=None,
        )
        self.assertEqual(result.applied, 1)


if __name__ == "__main__":
    unittest.main()
