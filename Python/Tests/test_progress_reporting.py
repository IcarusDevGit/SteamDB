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
from unittest.mock import Mock

import UpdateDB
import main
from database_updates import apply_validated_csv
from database_updates.repairs import ratings, weekly_stats
from extraction_pipeline import CatalogSnapshot, ExtractionPipeline, PipelineConfig
from request_scheduler import ProviderGate, ProviderPolicy, RetryableRequestError
from validation_models import ValidationStatus
from workflow_models import StoreData
from workflow_progress import ProgressEvent, TerminalProgressReporter, emit


def gates(reporter=None):
    policy = ProviderPolicy(interval=0, concurrency=10, queue_size=100, retries=0)
    return {
        name: ProviderGate(policy, provider=name, reporter=reporter)
        for name in ("steam_web", "steam_store", "itad")
    }


class ProgressClients:
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
    def __init__(self):
        super().__init__()
        self.flushes = 0

    def flush(self):
        self.flushes += 1
        super().flush()


class ProgressReportingTests(unittest.IsolatedAsyncioTestCase):
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

        database = Mock()
        database.find_missing_ratings.return_value = [
            {"appid": appid, "week_date": "2026-08-04"} for appid in (1, 2, 3)
        ]
        events = []
        args = argparse.Namespace(week="2026-08-04", appid=None, limit=None, apply=False)
        ratings.run(args, {"database": database, "clients": Clients(), "reporter": events.append})
        outcomes = [event.fields["outcome"] for event in events if event.kind == "candidate_completed"]
        self.assertEqual(outcomes, ["proposed", "failed", "skipped"])

        alias_events = []
        result = UpdateDB.dispatch(
            ["update_last_week_rank", "--date", "2026-08-04"],
            dependencies={"database": database, "clients": Clients(), "reporter": alias_events.append},
        )
        self.assertEqual(result.proposed, 1)
        self.assertTrue(any(event.kind == "candidate_completed" for event in alias_events))


if __name__ == "__main__":
    unittest.main()
