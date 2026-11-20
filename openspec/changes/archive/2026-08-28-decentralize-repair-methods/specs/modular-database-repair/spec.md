## ADDED Requirements

### Requirement: Repair modules own repair-specific persistence
Each repair operation SHALL own the candidate-selection queries and mutation statements specific to that operation. Repair operations SHALL obtain PostgreSQL connections through the shared connection facility used by the main database workflow, and adding a repair SHALL NOT require adding repair-specific query or mutation methods to the main database workflow boundary.

#### Scenario: Contributor adds a repair operation
- **WHEN** a contributor implements a new named repair
- **THEN** its repair module contains the operation-specific candidate reads and writes while reusing the shared PostgreSQL connection facility

#### Scenario: Existing repair persistence is organized by operation
- **WHEN** rating, price, or weekly-stat repairs select or mutate their records
- **THEN** the corresponding repair module owns those database statements and transaction behavior

## MODIFIED Requirements

### Requirement: External discovery and persistence remain separated
A repair that obtains replacement data from an external provider SHALL finish candidate discovery and validation before opening its mutation transaction. Each repair module SHALL own its operation-specific database reads and transactional writes while obtaining connections through the shared database connection facility.

#### Scenario: Provider returns no reliable replacement
- **WHEN** the external provider has no valid replacement value for a candidate
- **THEN** the repair skips that candidate and does not overwrite the stored value

#### Scenario: Valid candidates are authorized for application
- **WHEN** discovery and validation complete and the operator authorizes application
- **THEN** the owning repair module transactionally persists only the validated targeted changes
