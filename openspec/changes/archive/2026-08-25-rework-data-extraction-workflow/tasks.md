## 1. Foundations and Project Layout

- [x] 1.1 Inventory current Python modules and generated CSV/JSON/Markdown files, define their target module/helper paths, and verify the mapping covers every script and generated helper named in `Prompts/WorkflowRework.md`.
- [x] 1.2 Add a normalized per-game/per-week extraction record with explicit optional enrichment fields, and verify unit tests distinguish missing values from valid zero price, discount, or rating values.
- [x] 1.3 Add centralized repository and `helpers/` path utilities, update generated-file defaults to be cross-platform, and verify path tests resolve all script-generated `.csv`, `.json`, and `.md` files beneath `helpers/`.

## 2. Provider Clients and Request Scheduling

- [x] 2.1 Implement independently configurable limiters for Steam Web API, Steam Store, and ITAD requests, and verify clock-controlled tests enforce each provider's interval without one provider delaying another.
- [x] 2.2 Add bounded per-provider concurrency, queues, and backpressure plus provider-specific retry/backoff handling, and verify tests cover configured capacity, throttled responses, transient failures, and exhausted retries without request bursts.
- [x] 2.3 Refactor the weekly top-seller client to return normalized required fields for a target Tuesday, and verify fixture tests cover app id, name, rank, prior-week rank, consecutive weeks, categories, and date.
- [x] 2.4 Refactor ITAD lookup and historical price clients into asynchronous operations sharing the ITAD limiter, and verify tests cover resolved ids, absent ids, available history, and missing Steam history.
- [x] 2.5 Implement configurable size/time-bounded ITAD identifier lookup batching and result fan-out, and verify tests cover full batches, timeout-flushed partial batches, partial mappings, and end-of-input flushing.
- [x] 2.6 Refactor Steam review calculation into an asynchronous operation accepting a target-date cutoff, and verify fixture tests exclude review activity after that date.
- [x] 2.7 Refactor Steam Store HTML and app-details access into asynchronous operations behind the Steam Store limiter, and verify tests parse tags and fallback price/discount plus category names from representative responses.

## 3. Extraction Orchestration

- [x] 3.1 Implement CLI parsing and validation for one or more Tuesday dates while retaining the last-closed-Tuesday default, and verify CLI tests accept multiple Tuesdays and reject non-Tuesday or malformed dates before requests start.
- [x] 3.2 Implement record readiness states for the independent rating branch and the `ITAD id -> ITAD history -> conditional Steam HTML` branch, and verify dependency tests reject history without an id and HTML before the history outcome.
- [x] 3.3 Implement bounded cross-entry scheduling across provider queues, and verify a fake-clock integration test shows later entries progress while earlier entries wait without exceeding queue, semaphore, or rate limits.
- [x] 3.4 Implement record completion, error propagation, cancellation, worker draining, and deterministic output ordering, and verify partial provider failures cannot strand tasks or finalize incomplete active branches.
- [x] 3.5 Implement multi-week admission and a concurrency-safe in-memory cache for repeated games/tags across requested dates, and verify one run produces correctly dated records without unnecessary repeated enrichment.
- [x] 3.6 Implement ITAD-first price/discount precedence and post-history Steam HTML fallback, and verify HTML is never requested before the history result while available ITAD values remain authoritative.

## 4. Catalog and Tag Synchronization

- [x] 4.1 Load existing games and tags through the database module into a read-only extraction snapshot, and verify extraction tests make no database write calls.
- [x] 4.2 Collect Steam store tags only for games absent from the snapshot/run cache, and verify existing games cause no tag-page request while new games retain collected tag data.
- [x] 4.3 Normalize collected tag names through `Exceptions.json` and preserve unresolved names for manual handling, and verify tests cover mapped, known, and unresolved tags without invented ids.
- [x] 4.4 Resolve weekly category names through Steam app details only for category ids missing from the tags lookup, and verify known categories produce no app-details request.
- [x] 4.5 Build canonical game tag-id lists and missing tag records for later persistence, and verify tests keep tag names in tag records rather than the games table representation.

## 5. Validation Output and Database Update

- [x] 5.1 Update CSV serialization to include the week date and all normalized weekly/enrichment fields in a run-specific file under `helpers/`, and verify a multi-Tuesday fixture round-trips without losing optional values.
- [x] 5.2 Remove database mutation behavior from `main.py` and keep database updates behind explicit `UpdateDB.py` commands, and verify an extraction integration test completes with zero inserts or updates.
- [x] 5.3 Refactor `UpdateDB.py` to read validated helper CSVs, group rows by week, and gate unresolved tags through the manual exception flow, and verify unapproved or unresolved input cannot be silently applied.
- [x] 5.4 Move all SQL reads and transactional game, tag, and weeksheet upserts into `DB.py`, and verify database integration tests update existing rows and insert missing resolved entities without duplicates.

## 6. Migration and End-to-End Verification

- [x] 6.1 Move applicable generated helper artifacts into `helpers/`, update imports/defaults/tests/documentation, and verify repository search finds no active generated-file references to `CSV/` or hard-coded `C:/Dev/SteamDB` paths.
- [x] 6.2 Run the complete automated test suite and verify provider limiting, batching, backpressure, dependency ordering, cross-entry concurrency, fallback, tag resolution, CSV validation, and database-boundary tests all pass.
- [x] 6.3 Perform recorded dry runs for one historical Tuesday and multiple Tuesdays using mocked or safely rate-limited providers, and verify each output row is complete, HTML follows ITAD history, provider quotas are respected, and the multi-entry pipeline improves elapsed time over the sequential baseline.
- [x] 6.4 Apply an operator-approved test CSV through `UpdateDB.py` against a disposable database and verify games, tags, and weeksheet rows are inserted/updated as specified with no duplicate entities.
