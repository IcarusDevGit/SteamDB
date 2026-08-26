## Purpose

Defines a guarded persistence workflow in which extracted data is reviewed before database mutation and database operations remain centrally owned.

## ADDED Requirements

### Requirement: Validation precedes mutation
Completing extraction SHALL NOT update the database. The system SHALL require the operator to validate the generated CSV before invoking the database update workflow.

#### Scenario: CSV has not been approved
- **WHEN** extraction completes but the operator has not validated its CSV
- **THEN** no extracted records are written to the database

#### Scenario: CSV is approved
- **WHEN** the operator validates the CSV and explicitly starts the update workflow
- **THEN** the system may apply the validated records to the database

### Requirement: Centralized database access
All database queries used by extraction and update workflows SHALL be performed through the dedicated database access module.

#### Scenario: Workflow needs database state
- **WHEN** extraction or update logic needs to read or write database data
- **THEN** it delegates the query to the database access module

### Requirement: Update existing and missing records
The database update workflow SHALL update records already present in the database and SHALL insert validated games and tags that do not yet exist, subject to unresolved-tag handling.

#### Scenario: Validated data contains mixed record states
- **WHEN** an approved CSV contains existing records and new games or resolved tags
- **THEN** existing records are updated and missing resolved records are inserted without duplicating existing entities

