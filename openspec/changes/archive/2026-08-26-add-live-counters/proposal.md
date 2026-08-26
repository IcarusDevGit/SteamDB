## Why

The asynchronous weekly extraction workflow and database-update operations can remain silent for long periods while provider-limited enrichment, validation, candidate discovery, or persistence is running, leaving operators unable to distinguish healthy progress, intentional waits, and a stalled process. The legacy collector reported every game and stage, so the reworked operator workflows need equivalent live visibility while preserving their safety and concurrency guarantees.

## What Changes

- Emit immediate terminal messages when each weekly workflow stage starts and completes.
- Report a live `[completed/total]` counter whenever an extraction record reaches its terminal enrichment state, including identifying and outcome details useful to an operator.
- Report live `[completed/total]` counters throughout approved CSV application and every `UpdateDB.py` repair operation, including dry-run discovery and explicitly authorized application.
- Identify database-operation stage transitions, effective targets, and per-candidate applied, proposed, skipped, or failed outcomes without weakening validation or transaction boundaries.
- Report provider retry and backoff activity so intentional waits are visible.
- Keep concurrent output readable by reporting consolidated record completion rather than every internal branch transition.
- Send operational progress to standard error while preserving the existing final per-week summary on standard output.
- Make progress reporting optional and injectable so library callers and tests do not require terminal output.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `data-extraction-workflow`: Require live, concurrency-safe operator progress reporting throughout weekly extraction, retry waits, CSV creation, and validation.
- `validated-database-update`: Require live stage and record counters while validating and applying an approved CSV.
- `modular-database-repair`: Require consistent live stage and candidate counters for dry-run and applied repair operations.

## Impact

- Affected code: `Python/main.py`, `Python/extraction_pipeline.py`, `Python/request_scheduler.py`, `Python/UpdateDB.py`, modules under `Python/database_updates/`, a small shared progress-event/reporter module, and related tests.
- CLI behavior: additional flushed progress messages appear on standard error; the existing final standard-output summaries, dry-run/apply semantics, transaction behavior, and exit codes remain compatible.
- APIs: extraction, provider scheduling, CSV application, and repair operations gain optional progress-reporting hooks; callers that omit them retain current behavior.
- Dependencies and external providers: no new dependency or provider integration is required.
