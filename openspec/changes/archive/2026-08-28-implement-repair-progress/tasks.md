## 1. Characterize the Progress Contract

- [x] 1.1 Add focused tests for every registered repair's candidate-selection stage start/completion/failure and external request start/terminal events; verify identities, provider phases, monotonic completed/total counts, and immediate candidate failures are covered.
- [x] 1.2 Add focused persistence tests for ratings, prices, weekly stats, game names, and weekly identities; verify each emits bounded unit progress before the single commit and rolls back on SQL or reporter failure.
- [x] 1.3 Add CLI stream tests proving repair progress is flushed to standard error, final summaries remain on standard output, embedded calls without reporters remain silent, and canonical commands plus compatibility aliases share the same behavior.

## 2. Standardize Repair Progress Boundaries

- [x] 2.1 Add minimal shared repair-progress helpers or conventions for unit start, terminal outcome, and persistence events; verify structured fields render safely and existing progress event consumers remain compatible.
- [x] 2.2 Thread the optional reporter through candidate selection and mutation helpers while keeping all repair-specific SQL in its owning module; verify dry runs still perform no persistence and reporter-free callers produce no output.
- [x] 2.3 Ensure candidate-selection, external-lookup, and persistence exceptions emit matching stage-failed events before propagating; verify command exit codes and aggregate outcome fields remain unchanged.

## 3. Instrument Every Repair Operation

- [x] 3.1 Instrument rating discovery and persistence with candidate/provider start, terminal outcome, and row persistence progress; verify mixed success, unavailable, failure, dry-run, apply, rollback, and completion-order tests pass.
- [x] 3.2 Instrument price discovery with distinct shared ITAD lookup, ITAD history, and Steam fallback progress, then add row persistence progress; verify fallback paths, shared lookup failure, mixed outcomes, dry-run, apply, and rollback tests pass.
- [x] 3.3 Instrument weekly-stat chart lookup and row persistence with bounded progress; verify field variants, limits, provider failure, dry-run, atomic apply, and completion counts pass.
- [x] 3.4 Instrument game-name discovery and persistence with candidate/provider start, terminal outcome, and row progress; verify default whitespace selection, narrowed targets, unavailable names, guarded updates, dry-run, apply, and rollback tests pass.
- [x] 3.5 Extend weekly-identity discovery to expose per-week rendered-chart and complete-chart request boundaries while preserving its existing catalog and reconciliation progress; verify exact-100 validation failures, all-week discovery, one-week targeting, dry-run, apply, and cross-week rollback tests pass.

## 4. Integration, Documentation, and Verification

- [x] 4.1 Extend the disposable PostgreSQL scenario to collect progress from each applied repair and verify persistence events occur before one commit without changing repaired data or transaction rollback behavior.
- [x] 4.2 Update database-repair operator guidance to describe the shared progress phases, provider-step identities, standard-error stream, final standard-output summary, and pending-transaction meaning of persistence completion; verify documentation links and examples remain valid.
- [x] 4.3 Run focused repair/progress/parser tests, the disposable PostgreSQL scenario, and the complete active Python suite; verify all pass without repair-specific additions to `Python/db.py` or changes under `Python_legacy/`.
- [x] 4.4 Run strict OpenSpec validation for `implement-repair-progress` and verify the proposal, design, task list, and modular-database-repair delta are coherent and valid.
