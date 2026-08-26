## Context

The extraction CLI delegates a whole week to `ExtractionPipeline.run()` and regains control only after all concurrent enrichment finishes. The pipeline schedules rating, ITAD, Steam HTML, and tag work concurrently behind provider-specific gates, while `main.py` owns CSV creation, validation, final output, and exit status. Separately, `UpdateDB.py` is a thin dispatcher: approved CSV application and repair modules own validation, candidate iteration, external discovery, and persistence, and the dispatcher currently sees only the final operation result. Useful counters therefore cannot be implemented solely at either CLI boundary. See `proposal.md` for motivation and the delta specs for observable requirements.

The progress mechanism must preserve pipeline reuse, deterministic tests, readable output despite out-of-order completion, and the existing distinction between the final result and operational diagnostics.

## Goals / Non-Goals

**Goals:**

- Carry structured progress events across both CLIs, the extraction pipeline, provider scheduler, CSV application, and repair modules without coupling those layers to terminal formatting.
- Emit one atomic, immediately flushed terminal line per event.
- Count fully terminal records in actual completion order.
- Preserve current behavior when no reporter is supplied.

**Non-Goals:**

- Recreate the legacy workflow's sequential tag, rating, and price phases; those operations are concurrent now.
- Display an in-place progress bar, cursor animation, colors, or third-party terminal UI.
- Log every provider request or every branch-state transition.
- Add persistent log files, verbosity flags, or progress for database operations outside the `UpdateDB.py` apply/repair surface.

## Decisions

### Use structured events and an optional synchronous reporter

Introduce a small shared progress module containing a structured event representation, a no-op-compatible reporter protocol/callable, and CLI terminal formatting. Workflow layers emit events only when a reporter is present. A synchronous callable is sufficient because emission is a short in-memory format/write operation and avoids making every event site await an output callback.

Events carry a stable kind plus relevant fields rather than preformatted strings. Expected kinds cover stage start/completion/failure, record or candidate completion, and provider retry. This keeps terminal wording in one place and lets tests collect events without parsing console text.

Alternative considered: call `print()` directly throughout the pipeline and scheduler. Rejected because it couples reusable extraction code to a terminal, complicates tests, and scatters formatting rules.

### Count at the terminal point of each record's enrichment coroutine

After both enrichment branches and tag resolution have reached their terminal result, the per-record coroutine increments a run-local completed count and emits exactly one record event. Because asyncio tasks execute mutation and callback invocation without an `await` between them, the increment and emission form an ordered event-loop operation; no thread lock is needed. The event includes `completed`, `total`, week, rank, app ID, name, branch states, tag source, unresolved count, and error count.

Completion order is deliberately independent of rank order. A record with failed or absent branch data is still counted once its branches are terminal. Tag source is normalized to a small vocabulary such as `catalog`, `steam`, or `unavailable` rather than inferred by the terminal formatter.

Alternative considered: count each rating, price, and tag branch separately as the legacy workflow did. Rejected because concurrent branch messages would interleave, triple output volume, and make the headline counter ambiguous.

### Keep stage ownership with the layer doing the work

The pipeline emits weekly-fetch, identifier-lookup, and enrichment events. The CLI emits per-week, CSV-write, and validation events. The provider gate emits retry events immediately before backoff, using a provider label supplied when gates are constructed. Failures are reported at the boundary that catches them, without replacing the existing final error line.

This avoids synthetic stage reporting in `main.py` for work it cannot observe. It also ensures the identifier lookup and retry waits cannot create unexplained silence.

For database operations, `UpdateDB.py` creates and injects the terminal reporter, but the selected operation module emits events at its actual boundaries. Approved CSV application reports input/report validation, record preparation, transactional application, and completion. Repair modules report their effective target, candidate discovery, external lookup when applicable, dry-run proposal or authorized application, and completion. Legacy aliases pass through the same reporter path so they do not develop separate behavior.

### Count database work at stable unit boundaries

CSV application uses validated CSV records as its counter units. Each accepted record receives one preparation outcome; transactional persistence then emits stage-level start/completion or failure because per-row "applied" messages before commit could falsely imply durable writes. The final existing operation result remains authoritative for committed counts.

Repairs use discovered candidate records as their counter units. Each candidate emits exactly one terminal outcome (`proposed`, `applied`, `skipped`, or `failed`) with `completed`, `total`, operation name, target identity, and outcome. Dry runs report `proposed`; authorized runs report `applied` only after the owning persistence boundary confirms success. Operations that discover no candidates emit stages with `total=0` and retain their existing final summary.

Alternative considered: emit database counters only from `UpdateDB.dispatch()`. Rejected because the dispatcher cannot observe validation phases, loop progress, transaction completion, or individual repair outcomes.

### Preserve output-channel compatibility

The terminal reporter writes operational events to `sys.stderr` using `flush=True`. The extraction final `week=... status=...` summary and `UpdateDB.py`'s rendered operation result remain on `stdout`; existing errors and exit statuses remain intact. Tests that inject an extractor or database-operation dependencies receive a reporter argument or dependency entry, while direct library callers can omit reporting entirely.

Alternative considered: write everything to stdout to mirror the legacy scripts. Rejected because the current final summary is useful as a stable machine-readable output and mixing progress into it would be a compatibility regression.

## Risks / Trade-offs

- [A synchronous reporter supplied by a library caller could block the event loop] → Document that reporters must return promptly; the built-in terminal reporter performs one short write.
- [Concurrent completion makes output order differ between runs] → Specify monotonic completion order rather than rank order and test invariants instead of exact rank sequencing.
- [A record raises unexpectedly before states become terminal] → Preserve the pipeline's failure behavior, emit the enclosing stage failure, and do not falsely increment the record counter.
- [Retry messages could become noisy during provider trouble] → Emit only when an actual retry/backoff is scheduled, not for successful requests or ordinary rate-limit pacing.
- [Names or errors may contain control characters/newlines] → Normalize terminal fields to a single safe line before writing.
- [Per-record database messages could imply changes committed before transaction completion] → Report preparation per record but reserve `applied` and persistence completion language for confirmed transaction outcomes.
- [Repair modules have different discovery and persistence shapes] → Standardize the event envelope and outcome vocabulary while letting each module emit at its own stable boundaries.

## Migration Plan

1. Add the shared event and terminal reporter abstraction with unit tests.
2. Thread the optional reporter through gate construction, extraction, and pipeline execution.
3. Add pipeline record/stage and scheduler retry event sites.
4. Add extraction CLI stage events while retaining the existing summary and failure output.
5. Thread the reporter from `UpdateDB.py` into approved CSV and repair handlers, then add operation-owned stages and counters without changing validation or transaction semantics.
6. Run focused extraction, update, repair, and reporter tests followed by the full Python test suite.

Rollback consists of removing reporter wiring and event emission; extraction data, persistence formats, and database state require no migration.
