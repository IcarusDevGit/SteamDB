"""Dependency-aware asynchronous extraction workflow."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Protocol

from request_scheduler import ProviderGate
from tag_resolution import load_exceptions, merge_category_ids, resolve_tags
from workflow_models import BranchState, ExtractionRecord, HistoricalRating, StoreData
from workflow_progress import Reporter, emit


class ExtractionClients(Protocol):
    """Define provider operations consumed by the extraction orchestrator."""
    async def weekly(self, week_date: str) -> list[dict]: ...
    async def itad_lookup(self, appids: list[int]) -> dict[int, str | None]: ...
    async def itad_history(self, itad_id: str, week_date: str) -> tuple[float | None, int | None]: ...
    async def rating(self, appid: int, week_date: str) -> HistoricalRating: ...
    async def steam_html(self, appid: int) -> StoreData: ...
    async def game_name(self, appid: int) -> str | None: ...
    async def categories(self, appid: int, category_ids: list[int]) -> dict[int, str]: ...


@dataclass(slots=True)
class CatalogSnapshot:
    """Provide the pipeline with existing game-tag and tag-name mappings."""
    games: dict[int, list[int]] = field(default_factory=dict)
    tags_by_name: dict[str, int] = field(default_factory=dict)

    @property
    def tag_names_by_id(self) -> dict[int, str]:
        """Invert the catalog tag mapping for canonical-name lookup."""
        return {int(tag_id): name for name, tag_id in self.tags_by_name.items()}


@dataclass(frozen=True)
class PipelineConfig:
    """Set entry concurrency and ITAD identifier batching thresholds."""
    max_entries: int = 100
    itad_batch_size: int = 100
    itad_batch_wait: float = 0.05


class ItadLookupBatcher:
    """Collect lookup requests until size, timeout, or explicit close."""

    _STOP = object()

    def __init__(self, lookup, *, batch_size: int, max_wait: float):
        """Configure the lookup callback and batch flush thresholds."""
        if batch_size < 1 or max_wait < 0:
            raise ValueError("batch size must be positive and max wait cannot be negative")
        self.lookup = lookup
        self.batch_size = batch_size
        self.max_wait = max_wait
        self.queue = asyncio.Queue()
        self.worker = None

    async def start(self):
        """Start the single queue consumer if it is not already running."""
        if self.worker is None:
            self.worker = asyncio.create_task(self._run())

    async def submit(self, appid: int) -> str | None:
        """Queue an application ID and await its result from a shared batch."""
        if self.worker is None:
            await self.start()
        future = asyncio.get_running_loop().create_future()
        await self.queue.put((appid, future))
        return await future

    async def close(self):
        """Flush pending work, stop the consumer, and make restart possible."""
        if self.worker is None:
            return
        await self.queue.put(self._STOP)
        await self.worker
        self.worker = None

    async def _run(self):
        """Drain queued requests into size- or time-bounded lookup batches."""
        stopping = False
        while not stopping:
            item = await self.queue.get()
            if item is self._STOP:
                return
            batch = [item]
            # Once the first item arrives, cap how long later items may coalesce.
            deadline = asyncio.get_running_loop().time() + self.max_wait
            while len(batch) < self.batch_size:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    next_item = await asyncio.wait_for(self.queue.get(), remaining)
                except TimeoutError:
                    break
                if next_item is self._STOP:
                    stopping = True
                    break
                batch.append(next_item)
            appids = [appid for appid, _ in batch]
            try:
                mappings = await self.lookup(appids)
                for appid, future in batch:
                    if not future.done():
                        future.set_result(mappings.get(appid))
            except Exception as exc:
                for _, future in batch:
                    if not future.done():
                        future.set_exception(exc)
            if stopping:
                return


class ExtractionPipeline:
    """Coordinate provider calls and enrich weekly entries into terminal records.

    The pipeline owns per-run concurrency limits and shared request caches while
    provider gates own rate limiting, queue capacity, and retries.
    """
    def __init__(
        self,
        clients: ExtractionClients,
        gates: dict[str, ProviderGate],
        snapshot: CatalogSnapshot,
        *,
        config: PipelineConfig = PipelineConfig(),
        exceptions: dict[str, int] | None = None,
        reporter: Reporter | None = None,
    ):
        """Bind provider clients, gates, catalog state, and progress reporting."""
        self.clients = clients
        self.gates = gates
        self.snapshot = snapshot
        self.config = config
        self.exceptions = exceptions if exceptions is not None else load_exceptions()
        self.reporter = reporter
        self._entry_capacity = asyncio.Semaphore(config.max_entries)
        self._store_cache: dict[int, asyncio.Task[StoreData]] = {}
        self._category_cache: dict[tuple[int, tuple[int, ...]], asyncio.Task[dict[int, str]]] = {}
        self._cache_lock = asyncio.Lock()

    async def run(self, week_dates: Iterable[str]) -> list[ExtractionRecord]:
        """Extract and enrich all requested weeks, returning stable sorted output.

        Weekly-fetch or identifier-lookup failures abort the run. Individual
        enrichment failures are recorded on their record as terminal states.
        """
        records: list[ExtractionRecord] = []
        for week_date in week_dates:
            emit(self.reporter, "stage_started", week=week_date, stage="weekly_fetch")
            try:
                items = await self.gates["steam_web"].run(lambda d=week_date: self.clients.weekly(d))
            except Exception as exc:
                emit(self.reporter, "stage_failed", week=week_date, stage="weekly_fetch", error=exc)
                raise
            records.extend(ExtractionRecord.from_weekly(item, week_date) for item in items)
            emit(
                self.reporter, "stage_completed", week=week_date,
                stage="weekly_fetch", records=len(items),
            )

        # Ratings can begin while the shared ITAD identifier lookup is assembled.
        rating_tasks = {id(record): asyncio.create_task(self._rating_branch(record)) for record in records}
        emit(self.reporter, "stage_started", stage="identifier_lookup", records=len(records))
        try:
            mappings = await self._lookup_all(records)
        except Exception as exc:
            emit(self.reporter, "stage_failed", stage="identifier_lookup", error=exc)
            raise
        emit(self.reporter, "stage_completed", stage="identifier_lookup", records=len(records))
        emit(self.reporter, "stage_started", stage="enrichment", records=len(records))
        completed = 0
        total = len(records)

        async def enrich(record: ExtractionRecord) -> None:
            """Finish dependent branches for one record within entry capacity."""
            nonlocal completed
            async with self._entry_capacity:
                record.itad_id = mappings.get(record.appid)
                await asyncio.gather(self._itad_and_store_branch(record), rating_tasks[id(record)])
                # Tag resolution depends on store/category data produced above.
                await self._tag_branch(record)
                if not record.complete:
                    raise RuntimeError(f"record {record.appid} did not reach terminal state")
                completed += 1
                if record.appid in self.snapshot.games:
                    tag_source = "catalog"
                elif record.steam_html_state is BranchState.SUCCEEDED:
                    tag_source = "steam"
                else:
                    tag_source = "unavailable"
                emit(
                    self.reporter,
                    "record_completed",
                    completed=completed,
                    total=total,
                    week=record.week_date,
                    rank=record.rank,
                    appid=record.appid,
                    name=record.name,
                    rating=record.rating_state.value,
                    itad=record.itad_state.value,
                    steam_html=record.steam_html_state.value,
                    tag_source=tag_source,
                    unresolved=len(record.unresolved_tags),
                    errors=len(record.errors),
                )

        try:
            await asyncio.gather(*(enrich(record) for record in records))
        except Exception as exc:
            emit(self.reporter, "stage_failed", stage="enrichment", error=exc)
            raise
        emit(self.reporter, "stage_completed", stage="enrichment", records=completed)
        return sorted(records, key=lambda record: (record.week_date, record.rank, record.appid))

    async def _lookup_all(self, records: list[ExtractionRecord]) -> dict[int, str | None]:
        """Deduplicate application IDs and resolve them through batched ITAD calls."""
        unique_appids = list(dict.fromkeys(record.appid for record in records))
        batcher = ItadLookupBatcher(
            lambda appids: self.gates["itad"].run(lambda: self.clients.itad_lookup(appids)),
            batch_size=self.config.itad_batch_size,
            max_wait=self.config.itad_batch_wait,
        )
        await batcher.start()
        submissions = {appid: asyncio.create_task(batcher.submit(appid)) for appid in unique_appids}
        # Yield once so submit tasks enqueue before the explicit close sentinel.
        await asyncio.sleep(0)
        await batcher.close()
        return {appid: await task for appid, task in submissions.items()}

    async def _rating_branch(self, record: ExtractionRecord) -> None:
        """Populate rating data and convert provider failures to record errors."""
        record.rating_state = BranchState.RUNNING
        try:
            historical = await self.gates["steam_store"].run(
                lambda: self.clients.rating(record.appid, record.week_date)
            )
            if isinstance(historical, HistoricalRating):
                record.rating = historical.rating
                record.rating_label = historical.label
            else:
                # Preserve compatibility for injected callers that still return
                # the former numeric-only contract.
                record.rating = historical
            record.rating_state = BranchState.SUCCEEDED if historical is not None else BranchState.ABSENT
        except Exception as exc:
            record.rating_state = BranchState.FAILED
            record.errors.append(f"rating: {exc}")

    async def _itad_and_store_branch(self, record: ExtractionRecord) -> None:
        """Resolve historical price data, falling back to Steam when needed.

        Steam HTML is also fetched when catalog tags are unavailable. Failures
        are isolated to the record and expressed through branch state and errors.
        """
        record.itad_state = BranchState.RUNNING
        if record.itad_id is None:
            record.itad_state = BranchState.ABSENT
        else:
            try:
                record.price, record.discount = await self.gates["itad"].run(
                    lambda: self.clients.itad_history(record.itad_id or "", record.week_date)
                )
                record.itad_state = (
                    BranchState.SUCCEEDED
                    if record.price is not None or record.discount is not None
                    else BranchState.ABSENT
                )
            except Exception as exc:
                record.itad_state = BranchState.FAILED
                record.errors.append(f"itad_history: {exc}")

        needs_tags = record.appid not in self.snapshot.games
        needs_price = record.price is None and record.discount is None
        if not (needs_tags or needs_price):
            record.steam_html_state = BranchState.SKIPPED
            return
        record.steam_html_state = BranchState.RUNNING
        try:
            store_data = await self._store_data(record.appid)
            if needs_price:
                record.price, record.discount = store_data.price, store_data.discount
            if needs_tags:
                resolution = resolve_tags(
                    store_data.tags,
                    self.snapshot.tags_by_name,
                    exceptions=self.exceptions,
                    canonical_by_id=self.snapshot.tag_names_by_id,
                )
                record.tag_ids.extend(resolution.ids)
                record.tag_names.extend(resolution.names)
                record.unresolved_tags.extend(resolution.unresolved)
            record.steam_html_state = BranchState.SUCCEEDED
        except Exception as exc:
            record.steam_html_state = BranchState.FAILED
            record.errors.append(f"steam_html: {exc}")

    async def _store_data(self, appid: int) -> StoreData:
        """Return one shared in-flight or completed Steam HTML task per app ID."""
        async with self._cache_lock:
            task = self._store_cache.get(appid)
            if task is None:
                task = asyncio.create_task(
                    self.gates["steam_store"].run(lambda: self.clients.steam_html(appid))
                )
                self._store_cache[appid] = task
        return await task

    async def _tag_branch(self, record: ExtractionRecord) -> None:
        """Prefer catalog tags, otherwise merge community and category metadata."""
        existing_ids = self.snapshot.games.get(record.appid)
        if existing_ids is not None:
            record.tag_ids = list(existing_ids)
            record.tag_names = [
                self.snapshot.tag_names_by_id[tag_id]
                for tag_id in existing_ids
                if tag_id in self.snapshot.tag_names_by_id
            ]
            return
        unknown = [tag_id for tag_id in record.category_ids if tag_id not in self.snapshot.tag_names_by_id]
        resolved_names: dict[int, str] = {}
        if unknown:
            key = (record.appid, tuple(sorted(set(unknown))))
            async with self._cache_lock:
                task = self._category_cache.get(key)
                if task is None:
                    task = asyncio.create_task(
                        self.gates["steam_store"].run(
                            lambda: self.clients.categories(record.appid, unknown)
                        )
                    )
                    self._category_cache[key] = task
            resolved_names = await task
        categories = merge_category_ids(record.category_ids, self.snapshot.tags_by_name, resolved_names)
        # Community tags are authoritative when a Steam category has the same
        # display name.  Keep pairs aligned while also suppressing duplicate IDs.
        combined_ids: list[int] = []
        combined_names: list[str] = []
        seen_ids: set[int] = set()
        seen_names: set[str] = set()
        for tag_id, name in zip(
            record.tag_ids + categories.ids,
            record.tag_names + categories.names,
        ):
            if tag_id in seen_ids or name in seen_names:
                continue
            seen_ids.add(tag_id)
            seen_names.add(name)
            combined_ids.append(tag_id)
            combined_names.append(name)
        record.tag_ids = combined_ids
        record.tag_names = combined_names
        record.unresolved_tags = list(dict.fromkeys(record.unresolved_tags + categories.unresolved))
