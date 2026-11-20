## Context

The CLI already installs an immediately flushing structured terminal reporter, but repair modules use it inconsistently. Ratings, prices, and game names report only completed lookups; weekly stats reports only coarse stages; most row-by-row mutation functions provide no progress; and weekly identities covers persistence by week but not the provider subrequests within each week. Provider errors can also be held until final aggregation. See `proposal.md` and the repair delta specification for the observable contract.

Repair-specific SQL must remain in its repair module, all provider work must precede mutation, and each authorized repair must preserve its current transaction boundary.

## Goals / Non-Goals

**Goals:**

- Make every potentially slow repair unit visible before and after it runs.
- Use one event vocabulary and field shape across all repair modules.
- Preserve immediate flushing, optional reporters, dry runs, atomicity, summaries, aliases, and exit behavior.
- Make provider fallback, retry, and failure states diagnosable from terminal output.

**Non-Goals:**

- Adding new repair commands, command-line flags, database methods, or schemas.
- Changing which candidates qualify, which data providers are authoritative, or how repair values are calculated.
- Committing individual persistence rows to obtain progress.
- Printing periodic time-based heartbeat noise while a bounded request is still within its configured timeout.

## Decisions

### Define progress around bounded work units

Each repair will retain stage events and add unit events at the boundary of work that can block: external request start and terminal outcome, plus persisted candidate or week completion. Events will carry `operation`, `phase` or provider step, `identity`, and `completed`/`total` where the total is known. A start event makes the active operation visible during a bounded request; its configured timeout and terminal failure event distinguish a slow request from an indefinite silent gap.

Periodic heartbeats were rejected because they add concurrency, timer, and log-volume complexity without showing actual forward movement. Stage-only reporting was rejected because it caused the reported operator problem.

### Use a shared repair progress convention without centralizing repair behavior

Small shared helpers may standardize identity formatting and event emission, but selection SQL, mutation SQL, provider decisions, and outcome classification remain in their owning repair modules. Ratings, game names, and weekly stats have one provider step per candidate or week. Prices explicitly distinguish shared ITAD identifier lookup, ITAD history, and Steam fallback. Weekly identities exposes the rendered-chart and complete-chart request boundaries in addition to its existing per-week discovery and persistence events.

A generic repair engine was rejected because the operations have materially different candidate identities, fallback rules, and transaction shapes.

### Pass the same optional reporter through every slow boundary

Run functions will pass their reporter to discovery, provider orchestration, and persistence helpers. Production CLI calls continue to receive `TerminalProgressReporter`; tests and embedded callers may inject a collector or omit reporting. When existing provider scheduling performs retries, its retry/backoff events must use that reporter. This avoids parallel handwritten printing and preserves structured testability.

### Emit persistence progress inside, but never through, the transaction boundary

Mutation helpers will emit after each guarded row update or reconciled week while the transaction remains open. Commit occurs once after all units succeed; rollback occurs once on failure. A persistence event therefore means that SQL for a unit completed inside the pending transaction, not that it was committed.

### Give every started scope a terminal event

Candidate selection, external lookup, and persistence will wrap failures with a matching stage-failed event before re-raising. Candidate/provider units will report completed, unavailable, or failed as soon as their outcome is known. Final result rendering remains an aggregate rather than the first place an operator learns about an error.

## Risks / Trade-offs

- [Concurrent lookup events arrive out of candidate order] → Keep completed counts monotonic and treat identity, rather than input order, as the correlation key.
- [Per-row persistence output is noisy for large repairs] → Emit one concise line per completed bounded unit with completed/total counts; do not emit individual SQL statements.
- [A progress event says work completed before commit] → Use persistence-phase wording and retain an explicit stage-completed event only after commit.
- [Reporter failure interferes with database work] → Retain the existing lightweight reporter contract and cover rollback behavior when reporting raises.
- [Legacy aliases diverge from canonical commands] → Verify aliases dispatch through the same progress-aware handlers.

## Migration Plan

1. Characterize progress and failure gaps for every registered repair with focused tests.
2. Add or refine shared event conventions and thread reporters through provider and persistence boundaries.
3. Update ratings, prices, weekly stats, game names, and weekly identities, preserving their current outcomes and transactions.
4. Run focused progress/repair tests, disposable PostgreSQL coverage, the complete active suite, and strict OpenSpec validation.
5. Roll back by removing the added event emissions and reporter parameters; no data or schema rollback is required.
