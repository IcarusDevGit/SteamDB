# Validated Database Update Specification

## Purpose

Defines a guarded persistence workflow in which extracted data is reviewed before database mutation and database operations remain centrally owned.

## Requirements

### Requirement: Validation precedes mutation
Completing extraction SHALL NOT update the database. The system SHALL require the operator to provide a CSV containing exactly one week, explicitly authorize its application, pass structural and semantic input validation, and provide a successful single-week chart-validation report whose SHA-256 digest matches the exact CSV bytes before any database mutation begins.

#### Scenario: CSV has not been approved
- **WHEN** extraction completes but the operator has not validated and explicitly authorized its CSV
- **THEN** no extracted records are written to the database

#### Scenario: CSV is approved
- **WHEN** the operator explicitly authorizes a structurally and semantically valid single-week CSV with a successful matching chart-validation report for that same week
- **THEN** the system may apply the validated records to the database

#### Scenario: Approved CSV contains multiple weeks
- **WHEN** an explicitly authorized CSV contains more than one distinct week
- **THEN** the system rejects the input before mutation and requires separate weekly CSVs

#### Scenario: Approved CSV contains invalid or unresolved data
- **WHEN** an explicitly authorized CSV has missing required headers, invalid values, duplicate record identities, unresolved tags, or unacknowledged extraction errors
- **THEN** the system rejects the input before mutation and identifies the validation failure

#### Scenario: Chart validation did not pass
- **WHEN** the sidecar report is missing or its status is `failed` or `error`
- **THEN** the system rejects database application before mutation

#### Scenario: CSV changed after chart validation
- **WHEN** the sidecar report's CSV digest differs from the digest of the CSV being applied
- **THEN** the system rejects database application and requires the changed CSV to be revalidated

#### Scenario: Report covers a different week
- **WHEN** the passing sidecar report does not cover exactly the one week contained in the CSV
- **THEN** the system rejects database application before mutation

### Requirement: Centralized database access
All database queries used by extraction and update workflows SHALL be performed through the dedicated database access module.

#### Scenario: Workflow needs database state
- **WHEN** extraction or update logic needs to read or write database data
- **THEN** it delegates the query to the database access module

### Requirement: Update existing and missing records
The database update workflow SHALL reconcile the complete set of validated weekly records, insert validated games and resolved tags that do not yet exist, and preserve the stored attributes of games and tags already present. Changes to existing game or tag catalog attributes SHALL require a separately selected database update operation. The workflow SHALL avoid duplicating entities or violating weekly game and rank uniqueness.

#### Scenario: Validated data contains mixed record states
- **WHEN** an approved CSV contains existing and missing games or resolved tags
- **THEN** missing games and tags are inserted, existing game names and tag associations remain unchanged, existing tag names remain unchanged, and the validated weekly records are reconciled

#### Scenario: Existing catalog values differ from the CSV
- **WHEN** an approved CSV supplies a name or tag association that differs from the stored value for an existing game or tag
- **THEN** CSV application preserves the stored catalog value and does not implicitly perform a catalog repair

#### Scenario: Games exchange weekly ranks
- **WHEN** validated records assign existing games to ranks currently occupied by other games in the same week
- **THEN** the workflow reconciles the complete week without a transient or final weekly uniqueness conflict

### Requirement: Approved file application is atomic
The database update workflow SHALL apply an authorized CSV as one transaction so that no subset of its weeks or records remains committed after a persistence failure.

#### Scenario: Every record is persisted
- **WHEN** all records in an authorized multi-week CSV validate and persist successfully
- **THEN** the workflow commits all included records together

#### Scenario: A later record fails to persist
- **WHEN** persistence fails for any record in an authorized CSV
- **THEN** the workflow rolls back every mutation made for that CSV application

### Requirement: Optional CSV selection
The database update command SHALL accept an optional CSV path. When the operator supplies a path, the system SHALL select only that file. When the path is omitted, the system SHALL select every `.csv` file directly within `helpers/CSV` in deterministic filename order and SHALL reject the invocation if no eligible file exists.

#### Scenario: Operator selects one CSV
- **WHEN** the operator invokes the approved CSV application command with an explicit CSV path
- **THEN** the system applies only that CSV through the existing validated bulk-update workflow

#### Scenario: Operator omits the CSV path
- **WHEN** the operator invokes the approved CSV application command without a CSV path and `helpers/CSV` contains eligible CSV files
- **THEN** the system selects every directly contained `.csv` file in deterministic filename order

#### Scenario: Default directory contains no CSVs
- **WHEN** the operator omits the CSV path and `helpers/CSV` contains no eligible `.csv` file
- **THEN** the system exits unsuccessfully without changing the database or moving artifacts

#### Scenario: Batch uses a report override
- **WHEN** the operator omits the CSV path and supplies `--validation-report`
- **THEN** the system rejects the invocation because each batch CSV must use its own matching adjacent report

### Requirement: Independent guarded batch application
The system SHALL require explicit approval for both single-file and default batch operation and SHALL apply each selected CSV independently through the existing validation and atomic bulk persistence workflow. In a batch, the system SHALL isolate an unsuccessful file, continue attempting every remaining selected file, preserve every successful per-file commit, and return an unsuccessful overall status when any file fails.

#### Scenario: Every selected CSV succeeds
- **WHEN** every selected CSV and matching report passes validation and every per-file persistence transaction commits
- **THEN** the system reports each successful file and an aggregate applied-record count

#### Scenario: A batch file fails validation or persistence
- **WHEN** one selected CSV fails validation or persistence
- **THEN** the system records that failure, preserves every successful per-file commit, and continues with the remaining selected files

#### Scenario: Batch has mixed outcomes
- **WHEN** at least one selected CSV succeeds and at least one selected CSV fails
- **THEN** the system reports aggregate successful and failed file and record counts and returns an unsuccessful overall status

#### Scenario: Approval is omitted
- **WHEN** an operator requests either single-file or batch application without explicit approval
- **THEN** the system rejects the operation before database mutation or artifact movement

### Requirement: Successfully applied artifacts are archived
After a selected CSV's database transaction commits successfully, the system SHALL move that CSV and the validation report used to authorize it into `helpers/CSV upserted`. The system SHALL leave the pair at its original location when validation or persistence fails and SHALL prevent a destination collision from overwriting an archived artifact.

#### Scenario: Single-file application succeeds
- **WHEN** an explicitly selected CSV commits successfully
- **THEN** the system moves the CSV and its verified validation report into `helpers/CSV upserted`

#### Scenario: One file in a batch succeeds
- **WHEN** a batch file commits successfully
- **THEN** the system archives that CSV/report pair before processing the next selected file

#### Scenario: Validation or persistence fails
- **WHEN** a selected CSV fails before its database transaction commits
- **THEN** its CSV and report remain at their original locations

#### Scenario: Archive destination already exists
- **WHEN** either destination path for a selected CSV/report pair already exists
- **THEN** the system rejects that file before database mutation and does not overwrite the archived artifact

### Requirement: Failed default-batch artifacts are quarantined
When a CSV selected by default batch discovery fails validation, persistence, archive preflight, or post-commit archival, the system SHALL attempt to move the CSV and any existing validation report into `helpers/CSV_error`, SHALL avoid overwriting existing diagnostic artifacts, and SHALL make a best-effort attempt to write a separate error report that identifies the failed stage and error. Quarantine or diagnostic-report failures SHALL be reported but SHALL NOT prevent the system from processing the remaining selected files. An explicitly selected single-file failure SHALL leave its artifacts at their supplied locations.

#### Scenario: Batch validation or persistence fails
- **WHEN** a default-batch CSV fails validation or its database transaction rolls back
- **THEN** the system moves the CSV and any existing validation report to `helpers/CSV_error`, attempts to write an upsert-error report, and continues the batch

#### Scenario: Batch archival fails after commit
- **WHEN** a default-batch CSV commits but cannot be fully archived in `helpers/CSV upserted`
- **THEN** the system records that the database commit succeeded, attempts to quarantine the remaining artifact pair and an upsert-error report, and continues the batch

#### Scenario: Diagnostic destination name already exists
- **WHEN** a failed batch artifact or error-report destination already exists in `helpers/CSV_error`
- **THEN** the system uses collision-safe unique names and does not overwrite existing diagnostic evidence

#### Scenario: Quarantine or error-report creation fails
- **WHEN** the system cannot move some failed artifacts or cannot create the upsert-error report
- **THEN** it reports the diagnostic failure, preserves whatever artifacts remain available, and continues processing later batch files

#### Scenario: Explicit single-file application fails
- **WHEN** an explicitly selected CSV fails validation, persistence, or archival
- **THEN** the system reports the failure and leaves its artifacts at their supplied locations
