## Context

See `proposal.md` for motivation and the three delta specs for behavioral requirements. The current `Python/main.py` runs enrichment in whole-dataset passes, accepts one date, writes to `CSV/`, and still contains database-upsert code. Request timing is implemented independently inside scraper modules, while `Python/db.py` mixes connection ownership with granular CRUD and `Python/UpdateDB.py` contains the explicit persistence commands.

The rework spans orchestration, provider clients, tag resolution, file layout, and persistence boundaries. It must retain PostgreSQL compatibility, respect independent Steam API, Steam Store, and ITAD limits, and preserve `ITAD id -> ITAD history -> conditional Steam HTML` for every entry while allowing unrelated work to overlap.

## Goals / Non-Goals

**Goals:**

- Make one orchestration path responsible for date iteration and bounded, dependency-aware asynchronous enrichment.
- Express enrichment data as a stable record with explicit readiness and terminal states.
- Centralize provider throttling, concurrency, retry, and backpressure controls.
- Keep extraction read-only with respect to persistent business data and make CSV application explicit.
- Preserve existing database tables and migrate generated helper artifacts predictably.

**Non-Goals:**

- Changing the PostgreSQL schema unless implementation reveals a missing field required by the specs.
- Circumventing or constantly maximizing undocumented provider thresholds.
- Automating operator approval of extracted CSV data.
- Replacing the existing manual unresolved-tag decision process.
- Guaranteeing that asynchronously completed records are serialized in completion order.

## Decisions

### Use a thin entry point and a bounded asynchronous workflow orchestrator

`main.py` will parse one or more dates, validate them as Tuesdays, construct shared dependencies, and invoke an asynchronous workflow service. The workflow will fetch the requested charts, admit records through a bounded input queue, and schedule eligible stages for multiple records concurrently. Provider-specific modules will expose awaitable operations over explicit values instead of controlling overall traversal.

Bounded queues and worker/semaphore limits provide backpressure, prevent thousands of live network tasks, and allow capacity to be tuned independently of provider request rates. A strict one-game-at-a-time workflow was considered, but it serializes independent provider waits. An unrestricted task per request was also considered, but it risks memory growth, request bursts, and difficult cancellation.

### Represent each entry as a dependency graph

Each record progresses through explicit readiness states. ITAD history becomes eligible only after ITAD id resolution. Steam HTML becomes eligible only after the ITAD history outcome, because that result determines price fallback; the same HTML response may also supply tags for new games. Historical rating becomes eligible as soon as app id and target date exist and may overlap with the ITAD chain. An entry is ready for serialization only when every required and conditionally activated branch reaches a terminal state.

This preserves correctness without imposing completion order between entries. A fixed coroutine containing sequential calls was considered, but it cannot efficiently fill separate provider budgets while individual requests wait.

### Model throttling and concurrency per provider

A shared request scheduler will maintain a limiter and concurrency semaphore for each provider/host group: Steam Web API, Steam Store, and ITAD. Before a client sends a request, it obtains both concurrency capacity and rate permission. When one provider is waiting, the scheduler continues eligible stages for other providers and entries. Retry/backoff responses update only the affected provider's next-eligible time and reduce pressure without blocking unrelated queues.

Fixed `sleep()` calls inside each scraper were considered, but they cannot coordinate multiple endpoints belonging to the same provider, create bursts when many tasks wake together, and cause avoidable global idle time.

### Batch ITAD identifier lookups before dispatching history work

The ITAD shop-id lookup accepts multiple shop identifiers in one request. A batching stage will collect eligible identifiers up to a configurable maximum size or a short maximum wait, submit one rate-limited lookup, and fan the returned mappings back to their records. Only mapped records enter the ITAD history queue; unmapped records complete that branch without a history request and proceed to the post-history Steam HTML decision.

Batch size and timeout will be conservative and configurable because the live account limit and endpoint acceptance are authoritative. One lookup per entry was considered, but it consumes unnecessary quota and extends the ITAD bottleneck.

### Use one normalized extraction record per game and week

Introduce a typed record containing week metadata, core weekly fields, optional ITAD id, optional rating/price/discount, collected tag/category identifiers, unresolved tag names, branch states, and actionable errors. Absence is represented by `None` or an omitted optional value, not fabricated zero values. CSV serialization happens only after enrichment reaches a terminal state.

This avoids key-name drift such as `Tags` versus `tags` and preserves the distinction between a real zero and missing provider data. Continuing with arbitrary dictionaries was considered but would keep integration and state-transition errors discoverable only at runtime.

### Make fallback and conditional requests explicit workflow branches

ITAD lookup is the prerequisite for ITAD history. Rating collection is an independent branch and does not wait for ITAD. ITAD history is attempted only with a resolved ITAD id; an unmapped id or missing history leaves price/discount absent. The post-history decision requests Steam Store HTML when price fallback is needed or the game is absent from the database and tags must be collected. Steam app-details is requested only for weekly category ids absent from the tags table.

Combining every Steam need into unconditional requests was considered, but it wastes quota and violates the conditional tag/category requirements.

### Snapshot lookup state and defer all writes

At extraction startup, the workflow reads existing games/tags lookup state through `DB.py` and uses that snapshot to decide which enrichment requests are necessary. Extraction never calls upsert methods. A concurrency-safe in-memory run cache deduplicates repeated games and resolutions across requested weeks without persisting them. `UpdateDB.py` reads only operator-approved helper CSV input, resolves or manually gates unknown tags, and delegates transactional upserts to `DB.py`.

Immediate upserts during enrichment were considered, but they prevent meaningful CSV validation and can leave partial weeks after provider failures.

### Complete and shut down the pipeline explicitly

Every stage will emit success, absent-data, or failure as a terminal outcome, so a failed request cannot leave a dependent record waiting forever. Fatal cancellation propagates to workers; normal completion flushes partial ITAD batches, stops admission, drains queues, joins workers, and only then serializes deterministically by requested week and rank.

Implicit task cleanup at process exit was considered, but it can drop batched records and hide partial failures.

### Consolidate generated artifacts under `helpers`

All script-generated CSV, JSON, and Markdown paths will be resolved relative to a repository-level `helpers/` directory. Existing source-controlled inputs of those types will move only if they are script helper artifacts; documentation and OpenSpec files are excluded. CLI defaults will use relative, cross-platform paths rather than the current absolute Windows paths.

Keeping the `CSV/` directory alongside JSON files in other locations was considered, but it preserves the organizational problem and makes operator cleanup and discovery harder.

## Risks / Trade-offs

- [Provider limits may be undocumented or change] -> Keep limiter configuration explicit, conservative, and overridable; honor retry headers and exponential backoff.
- [Concurrency can amplify rate-limit mistakes or overload endpoints] -> Combine provider limiters, per-provider semaphores, bounded queues, jittered backoff, and runtime metrics; never derive concurrency directly from queue size.
- [Asynchronous failures can strand dependent stages] -> Give every branch explicit success, absent-data, and failure terminal states; propagate cancellation and drain workers before finalizing output.
- [Batching adds latency for small runs] -> Flush a partial ITAD lookup batch after a short configurable wait and immediately at end of input.
- [A single combined CSV may be ambiguous across dates] -> Include the target week date in every row and use a run-specific filename; allow the updater to group records by week.
- [Moving helper files can break scripts or operator habits] -> Centralize path construction, update all CLI defaults/tests/docs, and retain a documented one-time migration mapping.
- [Snapshot database state can repeat work for duplicate games across requested weeks] -> Maintain a concurrency-safe in-memory run cache without persisting it during extraction.
- [Partial external failures can yield incomplete rows] -> Distinguish required weekly identity fields from optional enrichment, record actionable errors, and never substitute fabricated values.

## Migration Plan

1. Add normalized record/state, helper-path, provider-limiter, bounded-queue, and provider-adapter boundaries with unit tests.
2. Refactor existing fetch/scraper behavior behind asynchronous adapters while retaining compatibility wrappers where useful.
3. Replace `main.py` orchestration with multi-date, dependency-aware asynchronous extraction, batched ITAD lookup, graceful shutdown, and no database mutation path.
4. Refactor tag resolution and `UpdateDB.py` to consume validated helper CSVs and delegate all queries to `DB.py`.
5. Move generated helper artifacts/defaults to `helpers/`, update tests and documentation, and compare a dry extraction for one Tuesday and multiple Tuesdays against a sequential baseline.
6. Roll back by restoring the former entry-point/module wiring and prior helper paths; database rollback is unnecessary because extraction remains read-only until explicit update.
