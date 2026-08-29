"""Check that the extraction pipeline realizes its intended concurrency."""

import asyncio
import time
import unittest

from extraction_pipeline import CatalogSnapshot, ExtractionPipeline, PipelineConfig
from request_scheduler import ProviderGate, ProviderPolicy
from workflow_models import StoreData


class TimedClients:
    """Simulate equal-latency providers and record dependency ordering."""
    def __init__(self, entries=5):
        self.entries = entries
        self.events = []

    async def weekly(self, week_date):
        return [{"rank": i, "appid": i, "name": f"Game {i}", "category_ids": []} for i in range(1, self.entries + 1)]

    async def itad_lookup(self, appids):
        await asyncio.sleep(0.01)
        return {appid: f"id-{appid}" for appid in appids}

    async def itad_history(self, itad_id, week_date):
        await asyncio.sleep(0.02)
        self.events.append((itad_id, "history"))
        return None, None

    async def rating(self, appid, week_date):
        await asyncio.sleep(0.02)
        return 0.8

    async def steam_html(self, appid):
        self.events.append((f"id-{appid}", "html"))
        await asyncio.sleep(0.02)
        return StoreData(price=9.99, discount=0, tags=[])

    async def categories(self, appid, category_ids):
        return {}


class DryRunTests(unittest.IsolatedAsyncioTestCase):
    """Compare concurrent pipeline timing with a conservative serial baseline."""
    async def test_single_and_multi_tuesday_dry_runs_beat_sequential_baseline(self):
        policy = ProviderPolicy(interval=0, concurrency=5, queue_size=10, retries=0)
        gates = {name: ProviderGate(policy) for name in ("steam_web", "steam_store", "itad")}
        clients = TimedClients()
        started = time.perf_counter()
        records = await ExtractionPipeline(
            clients, gates, CatalogSnapshot(),
            config=PipelineConfig(max_entries=5, itad_batch_size=5, itad_batch_wait=0),
        ).run(["2026-08-04", "2026-08-11"])
        elapsed = time.perf_counter() - started
        sequential_baseline = 10 * (0.02 + 0.02 + 0.02)
        self.assertEqual(len(records), 10)
        self.assertLess(elapsed, sequential_baseline * 0.75)
        for appid in range(1, 6):
            self.assertLess(
                clients.events.index((f"id-{appid}", "history")),
                clients.events.index((f"id-{appid}", "html")),
            )


if __name__ == "__main__":
    unittest.main()
