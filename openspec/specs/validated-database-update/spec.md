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
