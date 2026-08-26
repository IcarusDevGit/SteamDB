## 1. Progress Event Foundation

- [x] 1.1 Add the shared structured progress event and optional reporter interface, and verify collector tests can receive typed stage, record, and retry events without terminal output
- [x] 1.2 Add the single-line terminal reporter with `stderr` output, field sanitization, and immediate flushing, and verify focused tests cover formatting, newline normalization, stream selection, and flush behavior

## 2. Pipeline Live Counters

- [x] 2.1 Thread an optional reporter through extraction and pipeline construction while preserving reporter-free callers, and verify existing dry-run and pipeline tests still pass unchanged in behavior
- [x] 2.2 Emit weekly-fetch, identifier-lookup, and enrichment stage events at their true pipeline boundaries, and verify event-collector tests cover successful and failed stages
- [x] 2.3 Emit exactly one consolidated event after each record reaches terminal enrichment, including all specified identity, branch, tag-source, unresolved, error, and monotonic counter fields, and verify asynchronous tests cover out-of-rank completion plus absent and failed branches

## 3. Provider Retry Visibility

- [x] 3.1 Give each provider gate an optional provider label and reporter and emit retry events before actual backoff waits, and verify scheduler tests assert provider, upcoming attempt, and delay without reporting ordinary pacing or terminal failures as retries

## 4. CLI Workflow Reporting

- [x] 4.1 Wire the terminal reporter into production gate and pipeline construction and emit per-week, CSV-write, validation, completion, and failure stage events, verifying CLI tests observe the required stage order on `stderr`
- [x] 4.2 Preserve the existing final per-week summary on `stdout`, error/exit-code behavior, and multiweek continuation semantics, and verify redirected-stream tests cover passing, failed-validation, and extraction-error outcomes

## 5. Validated CSV Update Reporting

- [x] 5.1 Thread the optional reporter from `UpdateDB.py` through the approved CSV handler, including the promoted positional and `upsert-csv` aliases, and verify reporter-free direct callers and every command form retain existing behavior
- [x] 5.2 Emit stages for CSV/report validation, record preparation, transactional application, completion, and failure, and verify tests cover monotonic `[completed/total]` preparation counters without labeling records applied before commit
- [x] 5.3 Preserve the rendered update result on `stdout`, progress on flushed `stderr`, validation safeguards, atomic rollback, and exit codes, and verify redirected-stream tests cover success, rejected input, and persistence failure

## 6. Database Repair Reporting

- [x] 6.1 Thread the shared reporter through ratings, prices, and weekly-stat repairs plus their legacy aliases, and verify each command reports its effective bounded target before candidate work begins
- [x] 6.2 Emit discovery and external-lookup stages plus exactly one `proposed`, `applied`, `skipped`, or `failed` event per repair candidate, and verify tests cover monotonic counters, zero candidates, missing provider data, and mixed outcomes
- [x] 6.3 Distinguish dry-run proposals from explicitly authorized application and report applied outcomes only after the owning persistence boundary succeeds, verifying tests preserve non-mutating defaults and transactional failure behavior
- [x] 6.4 Preserve each repair's final rendered counts on `stdout`, progress on flushed `stderr`, and established exit codes, and verify all canonical and legacy command aliases behave consistently

## 7. Regression Verification

- [x] 7.1 Run the focused reporter, extraction pipeline, scheduler, extraction CLI, validated-update, and database-repair test modules and verify all live-counter acceptance scenarios pass
- [x] 7.2 Run the full Python test suite and verify extraction records, CSV behavior, validation classification, database safety boundaries, repair outcomes, and existing commands remain compatible
