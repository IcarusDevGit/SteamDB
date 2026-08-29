"""Exercise shared models, safe artifact paths, and provider scheduling."""

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from request_scheduler import AsyncRateLimiter, ProviderGate, ProviderPolicy, RetryableRequestError
from workflow_models import BranchState, ExtractionRecord
import workflow_paths


class FakeClock:
    """Advance deterministic async time while recording requested sleeps."""
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def now(self):
        return self.value

    async def sleep(self, delay):
        self.sleeps.append(delay)
        self.value += delay
        await asyncio.sleep(0)


class ModelPathSchedulerTests(unittest.IsolatedAsyncioTestCase):
    """Verify model invariants, path containment, pacing, and retry limits."""
    def test_record_preserves_zero_and_missing_values(self):
        record = ExtractionRecord("2026-08-04", 1, 10, "Game", rating=0.0, price=0.0, discount=0)
        row = record.to_csv_row()
        self.assertEqual(row["rating"], 0.0)
        self.assertEqual(row["price"], 0.0)
        self.assertEqual(row["discount"], 0)
        self.assertIsNone(ExtractionRecord("2026-08-04", 2, 11, "Unknown").price)

    def test_complete_requires_all_terminal_branches(self):
        record = ExtractionRecord("2026-08-04", 1, 10, "Game")
        self.assertFalse(record.complete)
        record.itad_state = BranchState.ABSENT
        record.rating_state = BranchState.SUCCEEDED
        record.steam_html_state = BranchState.SKIPPED
        self.assertTrue(record.complete)

    def test_helper_paths_stay_under_helpers(self):
        path = workflow_paths.extraction_csv_path(datetime(2026, 8, 25, tzinfo=timezone.utc))
        self.assertEqual(path.parent, workflow_paths.HELPERS_DIR)
        self.assertEqual(path.name, "steam_top_100_20260825T000000Z.csv")
        with self.assertRaises(ValueError):
            workflow_paths.helper_path("../escape.csv")

    def test_weekly_classified_paths_include_week_and_stay_in_directories(self):
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        staging = workflow_paths.weekly_extraction_csv_path("2026-08-04", now)
        self.assertEqual(staging.parent, workflow_paths.CSV_ERROR_DIR)
        self.assertIn("2026-08-04", staging.name)
        passed = workflow_paths.classified_csv_path(staging.name, passed=True)
        self.assertEqual(passed.parent, workflow_paths.CSV_DIR)
        with self.assertRaises(ValueError):
            workflow_paths.classified_csv_path("../escape.csv", passed=True)

    def test_upsert_archive_path_is_repository_relative(self):
        self.assertEqual(workflow_paths.CSV_UPSERTED_DIR, workflow_paths.HELPERS_DIR / "CSV upserted")
        self.assertEqual(workflow_paths.CSV_UPSERTED_DIR.parent, workflow_paths.HELPERS_DIR)

    async def test_rate_limiter_spaces_starts(self):
        clock = FakeClock()
        limiter = AsyncRateLimiter(1.0, clock=clock.now, sleep=clock.sleep)
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()
        self.assertEqual(clock.sleeps, [1.0, 1.0])

    async def test_provider_gates_do_not_block_each_other(self):
        slow_clock = FakeClock()
        fast_clock = FakeClock()
        slow = ProviderGate(
            ProviderPolicy(5, 1, 2),
            limiter=AsyncRateLimiter(5, clock=slow_clock.now, sleep=slow_clock.sleep),
            sleep=slow_clock.sleep,
        )
        fast = ProviderGate(
            ProviderPolicy(0, 1, 2),
            limiter=AsyncRateLimiter(0, clock=fast_clock.now, sleep=fast_clock.sleep),
            sleep=fast_clock.sleep,
        )
        calls = []

        async def operation(name):
            calls.append(name)
            return name

        await slow.run(lambda: operation("slow-1"))
        await asyncio.gather(slow.run(lambda: operation("slow-2")), fast.run(lambda: operation("fast")))
        self.assertLess(calls.index("fast"), calls.index("slow-2"))

    async def test_retry_after_is_honored_and_bounded(self):
        clock = FakeClock()
        gate = ProviderGate(
            ProviderPolicy(0, 1, 1, retries=1),
            limiter=AsyncRateLimiter(0, clock=clock.now, sleep=clock.sleep),
            sleep=clock.sleep,
        )
        attempts = 0

        async def flaky():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RetryableRequestError("limited", retry_after=2)
            return "ok"

        self.assertEqual(await gate.run(flaky), "ok")
        self.assertEqual(attempts, 2)
        self.assertGreaterEqual(sum(clock.sleeps), 2)

    async def test_provider_gate_caps_concurrent_operations(self):
        gate = ProviderGate(ProviderPolicy(0, concurrency=2, queue_size=3, retries=0))
        active = maximum = 0

        async def operation():
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1

        await asyncio.gather(*(gate.run(operation) for _ in range(6)))
        self.assertEqual(maximum, 2)


if __name__ == "__main__":
    unittest.main()
