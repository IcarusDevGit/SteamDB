## ADDED Requirements

### Requirement: Stored weekly identities can be compared with the global chart
The system SHALL provide a named repair that selects every distinct date already present in `weeksheet` by default and compares each stored rank/application identity set with Steam's corresponding global weekly Top 100. The repair SHALL permit an operator to select one stored week, SHALL obtain exactly 100 unique global application identifiers at ranks 1 through 100 independently of configurable extraction-country settings, and SHALL remain non-mutating unless application is explicitly authorized.

#### Scenario: Default discovery covers every stored date
- **WHEN** the operator runs the weekly-identity repair without a week target
- **THEN** the repair compares every distinct date present in `weeksheet`
- **AND** it does not create a chart for a date absent from `weeksheet`

#### Scenario: Operator selects one stored week
- **WHEN** the operator supplies a week target that exists in `weeksheet`
- **THEN** the repair compares only that week and reports the effective target

#### Scenario: Stored identities differ from global identities
- **WHEN** a stored week contains missing global games, unexpected games, or games at incorrect ranks
- **THEN** the dry-run reports each difference category and the unchanged identity count without mutating the database

#### Scenario: Global chart cannot be trusted
- **WHEN** Steam cannot provide exactly 100 unique global application identifiers at ranks 1 through 100 or the rendered global chart prefix disagrees with the complete response
- **THEN** the repair reports failure and performs no database mutation

### Requirement: Global weekly identities are reconciled without invented enrichment
When application is explicitly authorized, the system SHALL atomically reconcile every selected mismatched week to the validated global membership and rank set. It SHALL preserve price, discount, and rating by week/application identity for retained games; SHALL use global response values for rank, application identifier, name, last-week rank, and consecutive weeks; SHALL leave price, discount, and rating null for newly inserted weekly identities; and SHALL not obtain enrichment from any other provider.

#### Scenario: Existing global game moves rank
- **WHEN** a stored game remains in the global chart at a different rank
- **THEN** the repair moves that week/game identity to the global rank while preserving its stored price, discount, and rating

#### Scenario: US-only game is removed from a week
- **WHEN** a stored weekly game is absent from the validated global chart
- **THEN** the repair removes that weekly row without deleting the game's catalog entry

#### Scenario: Missing global game is introduced
- **WHEN** a validated global game is absent from the stored week
- **THEN** the repair inserts its weekly identity and global rank, last-week rank, and consecutive-weeks values with null price, discount, and rating

#### Scenario: Missing global game is absent from the catalog
- **WHEN** a required global application identifier has no `games` catalog row and the global response supplies a usable name
- **THEN** the repair inserts the catalog game with that name and an empty tag set before inserting its weekly row

#### Scenario: Required catalog identity lacks a usable global name
- **WHEN** a required global application identifier is absent from `games` and the global Top 100 response has no usable name
- **THEN** validation fails and no selected week is mutated

#### Scenario: Multiple weeks are repaired
- **WHEN** every selected global chart validates and the operator authorizes application
- **THEN** all selected mismatched weeks commit together or every repair mutation rolls back

#### Scenario: Multi-week persistence remains observable
- **WHEN** the repair begins applying one or more mismatched weeks
- **THEN** it reports bounded progress during catalog preparation and weekly reconciliation
- **AND** weekly reconciliation progress identifies the current week and completed/total week counts
- **AND** progress reporting does not introduce intermediate commits or weaken the all-or-nothing transaction
