## Context

See `proposal.md` for motivation. The active apply command currently requires one positional CSV, validates its matching digest-bound report, and commits that CSV through one database transaction. Passing extraction pairs wait in `helpers/CSV`, whose repository-relative location is already centralized in `workflow_paths.py`.

The new orchestration must reuse that per-file boundary. Database atomicity cannot cover filesystem moves, and a multi-file database transaction would change the established failure and progress semantics.

## Goals / Non-Goals

**Goals:**

- Add deterministic default discovery without duplicating per-file validation or persistence logic.
- Keep each CSV as the unit of database atomicity and archive its evidence pair only after commit.
- Isolate batch failures, preserve diagnostics, and continue useful work on later files.
- Prevent archive-name collisions and partial artifact-pair moves as far as filesystem operations permit.

**Non-Goals:**

- Combining multiple weekly CSVs into one database transaction or one SQL operation.
- Recursively discovering CSVs or applying files from `helpers/CSV_error` or the archive.
- Changing validation evidence, approval requirements, bulk SQL, or database schema.
- Automatically deleting, replacing, or versioning an existing archived artifact.

## Decisions

### Separate selection/orchestration from the existing per-file application

Make the parser's CSV positional argument optional and resolve it into an ordered list: the explicit path as a one-item list, or non-recursive `*.csv` discovery under `workflow_paths.CSV_DIR`. A batch orchestrator calls the existing guarded per-file operation for each item and aggregates its applied counts.

Teaching the existing parser/validator to accept directories or multiple files was rejected because it would blur the current single-week validation and transaction boundary.

### Retain per-file transactions and continue after isolated failures

Each selected file independently attempts validation, database commit, and artifact disposition before the next begins. Successful files remain committed and archived. A failed default-batch file is quarantined with diagnostics when possible, its outcome is accumulated, and the loop continues with the next originally selected path.

A transaction spanning every file was rejected because it would require moving validation into a larger persistence boundary and still could not atomically include filesystem archival. Stopping at the first failure was rejected because one bad weekly artifact should not require the operator to restart the command for every later valid file.

### Quarantine failed batch artifacts with supplemental diagnostics

For default-batch inputs only, route failures from validation, persistence, archive preflight, or post-commit archival to `workflow_paths.CSV_ERROR_DIR`. Move the CSV and any existing validation report using collision-safe unique filenames, then best-effort write a separate `<stem>.upsert-error.json` containing the source path, failed stage, error type and message, timestamp, and whether the database transaction committed. Preserve the original validation report because it remains evidence about chart validation and must not be rewritten as an upsert diagnostic.

If quarantine or error-report creation itself fails, retain the original exception plus diagnostic failure details in the aggregate result and continue. Explicit single-file inputs are not quarantined because an operator-supplied path may be outside the managed helper lifecycle.

Overwriting the validation sidecar was rejected because a passing chart report and a later database failure describe different stages. Stopping when diagnostics cannot be written was rejected because diagnostics are best effort and should not block later independent files.

### Archive the exact evidence pair used for authorization

Add a repository-relative `CSV_UPSERTED_DIR` path for `helpers/CSV upserted`. After a successful commit, move the selected CSV and the report returned by evidence verification into that directory, preserving their filenames. Default batches always use adjacent reports. An explicit `--validation-report` remains valid only with an explicit CSV and archives that selected report.

Leaving successful pairs in `helpers/CSV` was rejected because a later default invocation would select them again. Copying rather than moving was rejected because the source directory represents work still eligible for application.

### Preflight archive destinations before database mutation

Before applying a file, resolve both archive destinations and reject the file if either already exists. After commit, move the report and CSV as a coordinated pair. If the second move fails, make a best-effort compensating move of the first artifact back to its source and report the archival failure explicitly.

Overwriting was rejected because it could destroy audit evidence. A success-archive collision is classified as that file's batch failure and routed through quarantine; only diagnostic destinations receive unique suffixes because retaining both failures is more important than stable quarantine names.

### Preserve approval and constrain report overrides

The existing `--approved` gate applies to the entire invocation and is checked before selection causes any mutation or move. `--validation-report` is rejected in default batch mode because one override cannot authorize multiple independently digest-bound CSVs.

## Risks / Trade-offs

- [A process or filesystem failure can occur after database commit but before both moves complete] → Preflight destinations, coordinate the two moves, attempt compensation or quarantine, and record explicitly that persistence succeeded even if artifact disposition failed.
- [A batch can have mixed outcomes] → Process deterministically, isolate each failure, continue every originally discovered file, and return per-file plus aggregate outcomes with an unsuccessful overall status.
- [Quarantine or diagnostic creation can also fail] → Treat diagnostics as best effort, retain both primary and diagnostic errors in output, and continue later files.
- [Filename ordering may not match chronological week order for arbitrary names] → Define filename ordering as the stable contract; current generated names contain their week and naturally sort chronologically.
- [An explicit report outside the CSV directory is moved] → Document that the report actually used for approval is archived with the successfully applied CSV.

## Migration Plan

1. Add the archive path constant and optional CLI argument while preserving explicit-file compatibility.
2. Introduce selection, preflight, failure isolation, per-file orchestration, result aggregation, post-commit pair archival, and best-effort quarantine diagnostics.
3. Update command metadata and regenerate operator documentation.
4. Add parser, discovery-order, approval, mixed-outcome continuation, quarantine, diagnostic failure, collision, archival, and compatibility tests, then run the focused and complete unit suites.
5. Roll back by restoring the required positional argument and removing batch orchestration; already archived pairs can be moved back to `helpers/CSV` manually if they need to be reapplied.
