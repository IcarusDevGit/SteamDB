import asyncio
import unittest

from extraction_pipeline import CatalogSnapshot, ExtractionPipeline, ItadLookupBatcher, PipelineConfig
from request_scheduler import ProviderGate, ProviderPolicy
from workflow_models import StoreData


def gates():
    policy = ProviderPolicy(interval=0, concurrency=2, queue_size=2, retries=0)
    return {name: ProviderGate(policy) for name in ("steam_web", "steam_store", "itad")}


class FakeClients:
    def __init__(self):
        self.events = []
        self.lookup_batches = []
        self.html_calls = []
        self.category_calls = []

    async def weekly(self, week_date):
        return [
            {"rank": 2, "appid": 20, "name": "Second", "last_week_rank": 4, "consecutive_weeks": 2, "category_ids": [1]},
            {"rank": 1, "appid": 10, "name": "First", "last_week_rank": 3, "consecutive_weeks": 5, "category_ids": [1, 29]},
        ]

    async def itad_lookup(self, appids):
        self.lookup_batches.append(list(appids))
        return {appid: f"itad-{appid}" for appid in appids if appid != 20}

    async def itad_history(self, itad_id, week_date):
        self.events.append(("history", itad_id))
        await asyncio.sleep(0.01)
        return (9.99, 25) if itad_id == "itad-10" else (None, None)

    async def rating(self, appid, week_date):
        self.events.append(("rating", appid))
        await asyncio.sleep(0)
        return appid / 100

    async def steam_html(self, appid):
        self.events.append(("html", appid))
        self.html_calls.append(appid)
        return StoreData(price=19.99, discount=0, tags=["Action"])

    async def categories(self, appid, category_ids):
        self.category_calls.append((appid, list(category_ids)))
        return {29: "Co-op"}


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_batcher_flushes_full_timeout_and_end_of_input_batches(self):
        calls = []

        async def lookup(appids):
            calls.append(list(appids))
            return {appid: f"id-{appid}" for appid in appids if appid != 4}

        full = ItadLookupBatcher(lookup, batch_size=2, max_wait=1)
        await full.start()
        first = asyncio.create_task(full.submit(1))
        second = asyncio.create_task(full.submit(2))
        self.assertEqual(await asyncio.gather(first, second), ["id-1", "id-2"])
        await full.close()

        partial = ItadLookupBatcher(lookup, batch_size=5, max_wait=0.01)
        self.assertEqual(await partial.submit(3), "id-3")
        await partial.close()

        final = ItadLookupBatcher(lookup, batch_size=5, max_wait=10)
        await final.start()
        missing = asyncio.create_task(final.submit(4))
        await asyncio.sleep(0)
        await final.close()
        self.assertIsNone(await missing)
        self.assertEqual(calls, [[1, 2], [3], [4]])

    async def test_batches_lookup_preserves_dependencies_and_sorts_output(self):
        clients = FakeClients()
        pipeline = ExtractionPipeline(
            clients,
            gates(),
            CatalogSnapshot(games={}, tags_by_name={"Action": 1}),
            config=PipelineConfig(max_entries=2, itad_batch_size=2),
        )
        records = await pipeline.run(["2026-08-04"])
        self.assertEqual(clients.lookup_batches, [[20, 10]])
        self.assertEqual([record.rank for record in records], [1, 2])
        self.assertNotIn(("history", "itad-20"), clients.events)
        for appid in clients.html_calls:
            html_index = clients.events.index(("html", appid))
            history_events = [event for event in clients.events[:html_index] if event == ("history", f"itad-{appid}")]
            if appid == 10:
                self.assertTrue(history_events)
        self.assertTrue(all(record.complete for record in records))
        self.assertEqual(clients.category_calls, [(10, [29])])

    async def test_itad_price_wins_and_existing_game_skips_tag_html(self):
        clients = FakeClients()
        pipeline = ExtractionPipeline(
            clients,
            gates(),
            CatalogSnapshot(games={10: [1]}, tags_by_name={"Action": 1}),
            config=PipelineConfig(max_entries=2, itad_batch_size=10),
        )
        records = await pipeline.run(["2026-08-04"])
        first = next(record for record in records if record.appid == 10)
        self.assertEqual((first.price, first.discount), (9.99, 25))
        self.assertNotIn(10, clients.html_calls)
        self.assertEqual(first.tag_ids, [1])

    async def test_community_tag_wins_when_category_has_same_name(self):
        clients = FakeClients()

        async def weekly(week_date):
            return [{
                "rank": 1,
                "appid": 10,
                "name": "First",
                "category_ids": [49],
            }]

        async def steam_html(appid):
            return StoreData(price=19.99, discount=0, tags=["PvP"])

        async def categories(appid, category_ids):
            return {49: "PvP"}

        clients.weekly = weekly
        clients.steam_html = steam_html
        clients.categories = categories
        records = await ExtractionPipeline(
            clients,
            gates(),
            CatalogSnapshot(games={}, tags_by_name={"PvP": 1775}),
            config=PipelineConfig(max_entries=1, itad_batch_size=10),
        ).run(["2026-08-04"])

        self.assertEqual(records[0].tag_ids, [1775])
        self.assertEqual(records[0].tag_names, ["PvP"])

    async def test_cross_entry_progress_occurs(self):
        clients = FakeClients()
        await ExtractionPipeline(
            clients,
            gates(),
            CatalogSnapshot(games={}, tags_by_name={"Action": 1}),
            config=PipelineConfig(max_entries=2, itad_batch_size=1),
        ).run(["2026-08-04"])
        self.assertTrue(any(event[0] == "rating" for event in clients.events))
        self.assertEqual(len(clients.lookup_batches), 2)

    async def test_multiweek_deduplicates_lookup_and_store_html(self):
        clients = FakeClients()
        records = await ExtractionPipeline(
            clients, gates(), CatalogSnapshot(games={}, tags_by_name={"Action": 1}),
            config=PipelineConfig(max_entries=4, itad_batch_size=10),
        ).run(["2026-08-04", "2026-08-11"])
        flattened = [appid for batch in clients.lookup_batches for appid in batch]
        self.assertEqual(sorted(flattened), [10, 20])
        self.assertEqual(clients.html_calls.count(20), 1)
        self.assertEqual(len(records), 4)
        self.assertEqual({record.week_date for record in records}, {"2026-08-04", "2026-08-11"})

    async def test_provider_failure_reaches_terminal_record_state(self):
        clients = FakeClients()

        async def failed_history(itad_id, week_date):
            raise RuntimeError("history unavailable")

        clients.itad_history = failed_history
        records = await ExtractionPipeline(
            clients, gates(), CatalogSnapshot(games={}, tags_by_name={"Action": 1}),
            config=PipelineConfig(max_entries=2, itad_batch_size=10),
        ).run(["2026-08-04"])
        self.assertTrue(all(record.complete for record in records))
        failed = next(record for record in records if record.appid == 10)
        self.assertTrue(any(error.startswith("itad_history:") for error in failed.errors))


if __name__ == "__main__":
    unittest.main()
