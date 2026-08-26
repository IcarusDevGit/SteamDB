## MODIFIED Requirements

### Requirement: Validation precedes mutation
Completing extraction SHALL NOT update the database. The system SHALL require the operator to validate the generated CSV, explicitly authorize its application, and pass structural and semantic input validation before any database mutation begins.

#### Scenario: CSV has not been approved
- **WHEN** extraction completes but the operator has not validated and explicitly authorized its CSV
- **THEN** no extracted records are written to the database

#### Scenario: CSV is approved
- **WHEN** the operator validates and explicitly authorizes a CSV whose required fields, values, tag mappings, and record identities are valid
- **THEN** the system may apply the validated records to the database

#### Scenario: Approved CSV contains invalid or unresolved data
- **WHEN** an explicitly authorized CSV has missing required headers, invalid values, duplicate record identities, unresolved tags, or unacknowledged extraction errors
- **THEN** the system rejects the input before mutation and identifies the validation failure

### Requirement: Update existing and missing records
The database update workflow SHALL reconcile the complete set of validated records, update records already present, and insert validated games and resolved tags that do not yet exist without duplicating entities or violating weekly game and rank uniqueness.

#### Scenario: Validated data contains mixed record states
- **WHEN** an approved CSV contains existing records and new games or resolved tags
- **THEN** existing records are updated and missing resolved records are inserted without duplicating existing entities

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
