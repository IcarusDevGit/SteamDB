## 0. Promote and Isolate the Python Trees

- [x] 0.1 Rename the former `Python/` tree to `Python_legacy/` and promote `Python_temp/` to `Python/`, preserving all existing files and verifying the expected entry points exist in both directories.
- [x] 0.2 Update active tests, documentation, helper reports, and architecture evidence to reference the appropriate promoted or legacy tree, and verify repository search finds no active `Python_temp` references.
- [x] 0.3 Add or update isolation checks and verify both trees compile independently without importing modules from the other tree.

## 1. Establish the Modular Command Boundary

- [x] 1.1 Create `Python/database_updates/` and its `repairs/` subpackage with explicit exports, and verify an import smoke test succeeds without executing a command or opening a database connection.
- [x] 1.2 Add shared immutable candidate/result representations and reporting helpers for proposed, applied, skipped, and failed outcomes, and verify unit tests cover aggregation and successful versus failing exit status.
- [x] 1.3 Refactor `Python/UpdateDB.py` into a thin parser and explicit function registry for `apply` and `repair` command groups, and verify CLI tests cover help, known-command dispatch, and rejection of unknown commands with zero writes.

## 2. Modularize Approved CSV Application

- [x] 2.1 Move approved CSV parsing and application coordination into `database_updates/apply_validated_csv.py` using the common function contract, and verify existing CSV round-trip and approval-gate tests pass through the new CLI path.
- [x] 2.2 Validate required headers, dates, numeric bounds, duplicate week/rank and week/game identities, tag ID/name alignment, unresolved tags, and extraction errors before persistence, and verify table-driven malformed CSV tests fail before `db.py` receives an apply call.
- [x] 2.3 Change the database application boundary to accept every validated record from one approved file under a single commit/rollback scope, and verify a disposable-database test rolls back earlier weeks when a later record fails.
- [x] 2.4 Implement conflict-safe weekly set reconciliation that preserves records outside the authorized input scope, and verify disposable-database tests cover two games exchanging ranks, repeated idempotent application, new entities, and unaffected rows.

## 3. Add the Repair Operation Framework

- [x] 3.1 Add shared repair options that default to dry-run and require explicit `--apply` authorization for mutation, and verify a fake repair integration test reports candidates while making zero writes by default.
- [x] 3.2 Add operation-local target validation with support for week, application id, or bounded limit as appropriate, and verify apply mode rejects an unbounded target while reporting the effective bound for accepted targets.
- [x] 3.3 Define and test the repair execution sequence of candidate query, external discovery, validation, reporting, and optional transactional application, verifying provider failure skips unreliable values and never produces a partial streaming update.
- [x] 3.4 Register a representative repair module through functions rather than a class and verify it can be added to the command table without changing dispatcher control flow.

## 4. Migrate and Rationalize Legacy Repairs

- [x] 4.1 Inventory every legacy `Python_legacy/UpdateDB.py` command and repository call site, classify each as required, superseded, or compatibility-only, and verify the resulting migration table names the replacement path for every command.
- [x] 4.2 Move each retained repair into a focused function-based module with no embedded SQL or direct connection ownership, and verify module tests cover its discovery, validation, dry-run, bounded apply, and result reporting behavior.
- [x] 4.3 Add thin aliases only for legacy invocations classified as compatibility requirements, and verify alias tests dispatch to the same handler without duplicating implementation.
- [x] 4.4 Remove superseded commands from the isolated dispatcher and document their reviewed-extraction replacement, and verify repository documentation contains no unsupported invocation examples.

## 5. Verification and Operator Documentation

- [x] 5.1 Update the isolated workflow README with the package layout, command syntax, dry-run/apply safety model, targeting examples, and instructions for adding a function-based repair, and verify every documented command parses successfully.
- [x] 5.2 Run the complete `Python` unit suite and verify command dispatch, validation, dry-run safety, provider failure, result reporting, and existing extraction behavior all pass.
- [x] 5.3 Run the authorized disposable PostgreSQL integration suite and verify atomic multi-week application, rollback, rank swaps, idempotency, targeted repair writes, and preservation of out-of-scope records.
