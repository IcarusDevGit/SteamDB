## 1. Paths and Command Contract

- [x] 1.1 Add the repository-relative `helpers/CSV upserted` workflow path and verify path tests resolve it beneath the repository helpers directory.
- [x] 1.2 Make the canonical apply-CSV positional path optional while preserving explicit single-file and legacy invocation forms, and verify parser tests cover all supported forms.
- [x] 1.3 Reject `--validation-report` without an explicit CSV and reject an empty default CSV directory, verifying both cases fail before database or filesystem mutation.

## 2. Selection and Per-File Orchestration

- [x] 2.1 Implement non-recursive, deterministic `*.csv` discovery under `helpers/CSV` and verify tests exclude nested and non-CSV files and assert filename order.
- [x] 2.2 Route explicit and discovered files through the existing guarded per-file bulk-upsert workflow, aggregate applied counts, and verify `--approved` remains mandatory before any selected file is applied.
- [x] 2.3 Isolate validation and persistence failures, continue processing every remaining discovered file, preserve successful commits, and verify mixed outcomes and call order with mocked database calls.

## 3. Successful Artifact Archival

- [x] 3.1 Preflight CSV and report archive destinations without overwriting existing files, and verify a batch collision prevents database mutation for that file and routes it through failure quarantine.
- [x] 3.2 Move the exact verified CSV/report pair into `helpers/CSV upserted` after each successful commit, and verify both default-adjacent and explicit-report single-file cases.
- [x] 3.3 Coordinate pair moves with best-effort compensation when the second move fails, and verify the result distinguishes a successful database commit from failed archival before continuing the batch.

## 4. Failed Batch Quarantine

- [x] 4.1 Move a failed default-batch CSV and any existing validation report into `helpers/CSV_error` using collision-safe unique destinations, and verify existing diagnostic artifacts are never overwritten.
- [x] 4.2 Best-effort write a separate upsert-error JSON report containing source, stage, exception, timestamp, and commit state, and verify it does not replace or alter the chart-validation report.
- [x] 4.3 Continue later batch files when quarantine movement or error-report creation fails, preserve both primary and diagnostic errors in results, and verify remaining files are still attempted.
- [x] 4.4 Leave explicit single-file artifacts at their supplied locations on failure and verify quarantine applies only to default-batch selections.

## 5. Operator Output and Documentation

- [x] 5.1 Extend progress and result reporting with per-file outcomes, aggregate success/failure and record counts, and an unsuccessful overall status for mixed batches; verify single-file output remains compatible.
- [x] 5.2 Update command-catalog metadata and examples for optional/default selection, success archival, and failure quarantine, regenerate committed command documentation, and verify catalog freshness tests pass.
- [x] 5.3 Update README and troubleshooting guidance for default batch execution, explicit single-file execution, mixed outcomes, `helpers/CSV upserted`, `helpers/CSV_error`, and upsert-error reports; verify documented commands match runtime help.

## 6. Regression Verification

- [x] 6.1 Run the focused CSV update, workflow-path, progress-reporting, and command-catalog tests and verify they pass.
- [x] 6.2 Run the complete Python unit suite and verify existing per-file validation, approval, bulk persistence, rollback, and compatibility behavior remains green.
