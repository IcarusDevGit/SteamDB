"""Test structured progress events across pipeline, CLI, and update flows."""

import argparse
import asyncio
import csv
import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import UpdateDB
import main
from database_updates import apply_validated_csv
from database_updates.repairs import game_names, ratings, weekly_identities, weekly_stats
from extraction_pipeline import CatalogSnapshot, ExtractionPipeline, PipelineConfig
from request_scheduler import ProviderGate, ProviderPolicy, RetryableRequestError
from validation_models import ValidationStatus
from workflow_models import StoreData
from workflow_progress import ProgressEvent, TerminalProgressReporter, emit


def gates(reporter=None):
    """Build zero-delay gates that forward events to the supplied reporter."""
    policy = ProviderPolicy(interval=0, concurrency=10, queue_size=100, retries=0)
    return {
        name: ProviderGate(policy, provider=name, reporter=reporter)
        for name in ("steam_web", "steam_store", "itad")
    }


class ProgressClients:
    """Produce deterministic mixed-duration enrichment for event-order tests."""
    async def weekly(self, week):
        return [
            {"rank": 1, "appid": 10, "name": "Slow", "category_ids": []},
            {"rank": 2, "appid": 20, "name": "Fast", "category_ids": []},
        ]

    async def itad_lookup(self, appids):
        return {appid: f"itad-{appid}" for appid in appids}

    async def itad_history(self, itad_id, week):
        if itad_id == "itad-10":
            await asyncio.sleep(0.02)
        return 9.99, 0

    async def rating(self, appid, week):
        return 0.8

    async def steam_html(self, appid):
        return StoreData(price=9.99, discount=0, tags=["Action"])

    async def categories(self, appid, category_ids):
        return {}


class FlushStream(StringIO):
    """Record flush calls while retaining terminal output for assertions."""
    def __init__(self):
        super().__init__()
        self.flushes = 0

    def flush(self):
        self.flushes += 1
        super().flush()


class ProgressReportingTests(unittest.IsolatedAsyncioTestCase):
    """Verify event typing, sanitization, completion order, and retry reporting."""
    def test_typed_event_collection_and_terminal_sanitization(self):
        events = []
        emit(events.append, "stage_started", stage="bad\nname")
        self.assertIsInstance(events[0], ProgressEvent)
        stream = FlushStream()
        TerminalProgressReporter(stream)(
            ProgressEvent("candidate_completed", {
                "completed": 1, "total": 2, "name": "Game\nName", "outcome": "proposed",
            })
        )
        self.assertEqual(stream.getvalue(), "[1/2] event=candidate_completed name=Game Name outcome=proposed\n")
        self.assertEqual(stream.flushes, 1)

    async def test_pipeline_reports_actual_completion_order_and_stages(self):
        events = []
        pipeline = ExtractionPipeline(
            ProgressClients(), gates(events.append),
            CatalogSnapshot(games={10: [], 20: []}, tags_by_name={}),
            config=PipelineConfig(max_entries=2, itad_batch_size=10, itad_batch_wait=0),
            reporter=events.append,
        )
        records = await pipeline.run(["2026-08-04"])
        completed = [event for event in events if event.kind == "record_completed"]
        self.assertEqual(len(records), 2)
        self.assertEqual([event.fields["completed"] for event in completed], [1, 2])
        self.assertEqual([event.fields["appid"] for event in completed], [20, 10])
        self.assertTrue(all(event.fields["total"] == 2 for event in completed))
        self.assertTrue(all(event.fields["tag_source"] == "catalog" for event in completed))
        stages = {(event.kind, event.fields.get("stage")) for event in events}
        self.assertIn(("stage_started", "weekly_fetch"), stages)
        self.assertIn(("stage_completed", "identifier_lookup"), stages)
        self.assertIn(("stage_completed", "enrichment"), stages)

    async def test_provider_reports_only_scheduled_retry(self):
        events = []
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RetryableRequestError("busy", retry_after=0)
            return "ok"

        gate = ProviderGate(
            ProviderPolicy(interval=0, concurrency=1, queue_size=1, retries=1),
            provider="steam_store", reporter=events.append,
        )
        self.assertEqual(await gate.run(operation), "ok")
        retries = [event for event in events if event.kind == "provider_retry"]
        self.assertEqual(len(retries), 1)
        self.assertEqual(retries[0].fields["provider"], "steam_store")
        self.assertEqual(retries[0].fields["attempt"], 2)


class CliAndUpdateProgressTests(unittest.TestCase):
    """Verify progress stages emitted by CLI and persistence workflows."""
    def _csv(self, directory):
        path = Path(directory) / "approved.csv"
        fields = sorted(apply_validated_csv.REQUIRED_FIELDS)
        row = {
            "week_date": "2026-08-04", "rank": "1", "appid": "10", "name": "Game",
            "tags": "Action", "tag_ids": "1", "unresolved_tags": "", "rating": "0.8",
            "price": "9.99", "discount": "20", "last_week_rank": "2",
            "consecutive_weeks": "3", "errors": "",
        }
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow(row)
        path.with_name(f"{path.stem}.validation.json").write_text(json.dumps({
            "schema_version": 1, "status": "passed",
            "csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "weekly": {"week": "2026-08-04"},
        }), encoding="utf-8")
        return path

    def test_extraction_cli_separates_progress_and_final_summary(self):
        async def extractor(dates, config=None, reporter=None):
            emit(reporter, "record_completed", completed=1, total=1, week=dates[0], rank=1,
                 appid=10, name="Game", rating="succeeded", itad="succeeded",
                 steam_html="skipped", tag_source="catalog", unresolved=0, errors=0)
            return [{"week_date": dates[0], "rank": 1, "appid": 10, "name": "Game"}]

        def validator(path):
            return Mock(status=ValidationStatus.PASSED), Path(path), Path(path).with_suffix(".json")

        stdout, stderr = StringIO(), StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(stdout), redirect_stderr(stderr):
            code = main.main(["2026-08-04", "--output", str(Path(directory) / "out.csv")],
                             extractor=extractor, validator=validator)
        self.assertEqual(code, 0)
        self.assertIn("week=2026-08-04 status=passed", stdout.getvalue())
        self.assertNotIn("event=", stdout.getvalue())
        self.assertIn("[1/1] event=record_completed", stderr.getvalue())
        self.assertIn("stage=validation", stderr.getvalue())

    def test_approved_csv_reports_preparation_before_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._csv(directory)
            database = Mock()
            database.apply_validated_records.return_value = 1
            events = []
            count = apply_validated_csv.apply_csv(
                path, approved=True, database=database, reporter=events.append,
            )
        self.assertEqual(count, 1)
        candidates = [event for event in events if event.kind == "candidate_completed"]
        self.assertEqual(candidates[0].fields["outcome"], "prepared")
        persistence = [event for event in events if event.fields.get("stage") == "persistence"]
        self.assertEqual([event.kind for event in persistence], ["stage_started", "stage_completed"])
        self.assertTrue(all(event.fields["records"] == 1 for event in persistence))
        self.assertTrue(all(event.fields["unique_tags"] == 1 for event in persistence))

    def test_approved_csv_reports_candidate_counts_when_persistence_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._csv(directory)
            database = Mock()
            database.apply_validated_records.side_effect = RuntimeError("bulk failed")
            events = []
            with self.assertRaisesRegex(RuntimeError, "bulk failed"):
                apply_validated_csv.apply_csv(
                    path, approved=True, database=database, reporter=events.append,
                )
        persistence = [event for event in events if event.fields.get("stage") == "persistence"]
        self.assertEqual([event.kind for event in persistence], ["stage_started", "stage_failed"])
        self.assertTrue(all(event.fields["records"] == 1 for event in persistence))
        self.assertTrue(all(event.fields["unique_tags"] == 1 for event in persistence))

    def test_repairs_report_mixed_outcomes_and_legacy_alias_uses_reporter(self):
        class Clients:
            async def rating(self, appid, week):
                if appid == 2:
                    raise RuntimeError("failed")
                return None if appid == 3 else 0.8

            async def weekly(self, week):
                return [{"rank": 1, "last_week_rank": 2, "consecutive_weeks": 3}]

        candidates = [
            {"appid": appid, "week_date": "2026-08-04"} for appid in (1, 2, 3)
        ]
        events = []
        args = argparse.Namespace(week="2026-08-04", appid=None, limit=None, apply=False)
        with patch.object(ratings, "find_candidates", return_value=candidates):
            ratings.run(args, {"clients": Clients(), "reporter": events.append})
        outcomes = [event.fields["outcome"] for event in events if event.kind == "candidate_completed"]
        self.assertEqual(outcomes, ["proposed", "failed", "skipped"])

        alias_events = []
        result = UpdateDB.dispatch(
            ["update_last_week_rank", "--date", "2026-08-04"],
            dependencies={"clients": Clients(), "reporter": alias_events.append},
        )
        self.assertEqual(result.proposed, 1)
        self.assertTrue(any(event.kind == "candidate_completed" for event in alias_events))

    def test_game_name_repair_reports_whitespace_candidates_before_persistence(self):
        class Clients:
            async def game_name(self, appid):
                if appid == 2:
                    raise RuntimeError("failed")
                return None if appid == 3 else " Refreshed "

        candidates = [{"appid": appid, "current_name": "   "} for appid in (1, 2, 3)]
        events = []
        args = argparse.Namespace(appid=None, limit=None, apply=True)
        with (
            patch.object(game_names, "find_candidates", return_value=candidates),
            patch.object(game_names, "apply_updates", return_value=1) as apply,
        ):
            result = game_names.run(args, {"clients": Clients(), "reporter": events.append})
        apply.assert_called_once()
        self.assertEqual(result.target, "whitespace-names")
        self.assertEqual((result.applied, result.skipped, result.failed), (1, 1, 1))
        outcomes = [event.fields["outcome"] for event in events if event.kind == "candidate_completed"]
        self.assertEqual(outcomes, ["applied", "failed", "skipped"])
        stages = [(event.kind, event.fields.get("stage")) for event in events]
        self.assertLess(stages.index(("stage_completed", "external_lookup")), stages.index(("stage_started", "persistence")))

    def test_weekly_identity_repair_validates_all_weeks_before_persistence(self):
        stored = {
            "2026-08-04": [{"rank": 1, "appid": 10, "price": 1, "discount": 0, "rating": .5}],
            "2026-08-11": [{"rank": 1, "appid": 30, "price": 2, "discount": 0, "rating": .6}],
        }
        expected = {
            "2026-08-04": [{"rank": 1, "appid": 20, "name": "Twenty", "last_week_rank": 2, "consecutive_weeks": 1}],
            "2026-08-11": [{"rank": 1, "appid": 40, "name": "Forty", "last_week_rank": 2, "consecutive_weeks": 1}],
        }
        events = []
        reporter = events.append
        args = argparse.Namespace(week=None, apply=True)
        with (
            patch.object(weekly_identities, "load_state", return_value=(stored, {10, 20, 30, 40})),
            patch.object(weekly_identities, "apply_plans", return_value=2) as apply,
        ):
            result = weekly_identities.run(args, {
                "global_chart_fetcher": lambda week: ("url", expected[week]),
                "reporter": reporter,
            })
        apply.assert_called_once()
        self.assertIs(apply.call_args.kwargs["reporter"], reporter)
        self.assertEqual(result.applied, 2)
        stages = [(event.kind, event.fields.get("stage")) for event in events]
        self.assertLess(stages.index(("stage_completed", "discovery")), stages.index(("stage_started", "persistence")))

    def test_every_repair_exposes_provider_unit_boundaries(self):
        class Clients(ProgressClients):
            async def rating(self, appid, week):
                if appid == 2:
                    raise RuntimeError("rating failed")
                return .8

            async def game_name(self, appid):
                return "Name"

            async def weekly(self, week):
                return [{"rank": 1, "last_week_rank": 2, "consecutive_weeks": 3}]

            async def itad_lookup(self, appids):
                return {appid: f"itad-{appid}" for appid in appids}

            async def itad_history(self, itad_id, week):
                return None, None

            async def steam_html(self, appid):
                return StoreData(price=9.99, discount=0)

        candidates = [{"appid": appid, "week_date": "2026-08-04"} for appid in (1, 2)]
        events = []
        args = argparse.Namespace(week="2026-08-04", appid=None, limit=None, apply=False)
        with patch.object(ratings, "find_candidates", return_value=candidates):
            ratings.run(args, {"clients": Clients(), "reporter": events.append})
        rating_units = [event for event in events if event.kind == "unit_completed"]
        self.assertEqual([event.fields["outcome"] for event in rating_units], ["completed", "failed"])
        self.assertEqual([event.fields["completed"] for event in rating_units], [1, 2])

        events.clear()
        with patch("database_updates.repairs.prices.find_candidates", return_value=candidates[:1]):
            from database_updates.repairs import prices
            prices.run(args, {"clients": Clients(), "reporter": events.append})
        phases = {event.fields["phase"] for event in events if event.kind.startswith("unit_")}
        self.assertEqual(phases, {"itad_lookup", "itad_history", "steam_fallback", "candidate"})

        events.clear()
        name_args = argparse.Namespace(appid=None, limit=None, apply=False)
        with patch.object(game_names, "find_candidates", return_value=[{"appid": 1, "current_name": ""}]):
            game_names.run(name_args, {"clients": Clients(), "reporter": events.append})
        self.assertTrue(any(event.fields.get("phase") == "steam_game_name" for event in events))

        events.clear()
        stat_args = argparse.Namespace(week="2026-08-04", limit=None, field="all", apply=False)
        weekly_stats.run(stat_args, {"clients": Clients(), "reporter": events.append})
        self.assertTrue(any(event.fields.get("phase") == "steam_weekly_chart" for event in events))

    def test_repair_cli_streams_progress_and_embedded_calls_can_be_silent(self):
        class Clients:
            async def rating(self, appid, week):
                return .8

        candidate = [{"appid": 1, "week_date": "2026-08-04"}]
        stdout, stderr = StringIO(), FlushStream()
        with (
            patch.object(ratings, "find_candidates", return_value=candidate),
            patch("UpdateDB.TerminalProgressReporter", return_value=TerminalProgressReporter(stderr)),
            redirect_stdout(stdout),
        ):
            exit_code = UpdateDB.main(
                ["repair", "ratings", "--week", "2026-08-04"],
                dependencies={"clients": Clients()},
            )
        self.assertEqual(exit_code, 0)
        self.assertIn("event=unit_started", stderr.getvalue())
        self.assertGreater(stderr.flushes, 0)
        self.assertIn("repair ratings: target=week=2026-08-04", stdout.getvalue())

        silent_out, silent_err = StringIO(), StringIO()
        args = argparse.Namespace(week="2026-08-04", appid=None, limit=None, apply=False)
        with (
            patch.object(ratings, "find_candidates", return_value=candidate),
            redirect_stdout(silent_out), redirect_stderr(silent_err),
        ):
            ratings.run(args, {"clients": Clients()})
        self.assertEqual((silent_out.getvalue(), silent_err.getvalue()), ("", ""))

    def test_candidate_selection_failure_reports_failed_stage(self):
        events = []
        args = argparse.Namespace(week="2026-08-04", appid=None, limit=None, apply=False)
        with patch.object(ratings, "find_candidates", side_effect=RuntimeError("database stalled")):
            with self.assertRaisesRegex(RuntimeError, "database stalled"):
                ratings.run(args, {"reporter": events.append})
        self.assertEqual(
            [(event.kind, event.fields.get("stage")) for event in events],
            [("stage_started", "discovery"), ("stage_failed", "discovery")],
        )


if __name__ == "__main__":
    unittest.main()
