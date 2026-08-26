## MODIFIED Requirements

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
