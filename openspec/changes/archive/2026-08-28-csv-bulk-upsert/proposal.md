## Why

Operators currently have to invoke the approved-CSV command separately for every passing weekly artifact, even though each file follows the same guarded bulk-upsert workflow. The command should make the common operation convenient while retaining explicit single-file control and should archive successfully applied artifact pairs so they are not selected again by a later default run.

## What Changes

- Make the CSV positional argument to `UpdateDB.py apply csv` optional.
- When no CSV is supplied, discover and apply every `.csv` file directly under `helpers/CSV` in deterministic filename order.
- Preserve the existing explicit single-file form and run the same validation, approval, and bulk-upsert workflow for every selected file.
- After each file is successfully committed, move that CSV and its matching validation report into `helpers/CSV upserted`.
- Isolate each default-batch failure: move the failed CSV and any existing validation report into `helpers/CSV_error`, create a best-effort upsert-error report, and continue with the remaining files.
- Reject a default batch when no CSV files are available and restrict `--validation-report` overrides to explicit single-file operation.
- Report per-file progress and aggregate successful and failed results, returning an unsuccessful overall status when any file fails without changing the requirement for `--approved`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `validated-database-update`: Allow an explicitly authorized invocation to select either one CSV or all eligible CSVs, apply each through the existing atomic bulk workflow, archive successful pairs, and quarantine failed default-batch artifacts without interrupting the batch.

## Impact

- Affects the `Python/UpdateDB.py` command shape, `Python/database_updates/apply_validated_csv.py` orchestration, repository-relative workflow paths, progress/result aggregation, command-catalog metadata and generated documentation, and CSV update tests.
- Creates the repository-relative `helpers/CSV upserted` archive directory as needed and reuses `helpers/CSV_error` for failed batch artifacts and diagnostics.
- Does not change CSV or validation-report formats, database schema, per-file validation rules, the `--approved` safeguard, or the existing per-file bulk persistence transaction.
