## Why

Several database repairs emit a stage-start message and then remain silent throughout slow provider requests or row-by-row persistence. Operators cannot distinguish normal work from a stalled request or database operation, which violates the project's established expectation of immediate, ongoing terminal progress.

## What Changes

- Establish one terminal-progress contract for every public repair command.
- Report bounded progress throughout candidate selection, provider lookup, fallback-provider work, and persistence rather than only at stage boundaries.
- Identify the active repair, phase, candidate or week, and completed/total counts wherever work is enumerable.
- Surface provider retries, backoff waits, candidate failures, and stage failures as they occur.
- Keep progress immediately flushed on standard error while preserving final summaries on standard output and optional reporting for non-CLI callers.
- Preserve each repair's existing dry-run behavior and atomic transaction boundary; progress events do not create intermediate commits.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `modular-database-repair`: Require consistent live operator progress and terminal failure visibility across ratings, prices, weekly stats, game names, weekly identities, and future repair operations.

## Impact

- Updates all modules under `Python/database_updates/repairs/` that have silent provider or persistence intervals.
- May extend shared repair helpers, provider scheduling integration, and structured progress event coverage without moving repair-specific SQL into `Python/db.py`.
- Expands focused progress, repair, parser/alias, and disposable PostgreSQL tests.
- Updates database-repair operator documentation; command syntax and database schemas remain unchanged.
