## ADDED Requirements

### Requirement: Missing weekly rating labels can be repaired
The system SHALL provide a named `rating-labels` repair that retrieves all selected `weeksheet` rows whose `rating_label` is null in one database query and retains them in an in-memory candidate collection. It SHALL group candidates by game, obtain one complete histogram per unique game, derive a cutoff-consistent label for every candidate week from that response, and retain successful results in a separate update collection. It SHALL preserve numeric `rating`, support week, application identifier, and maximum-candidate filters, and remain non-mutating unless application is explicitly authorized.

#### Scenario: Default discovery finds null labels
- **WHEN** an operator runs the rating-label repair without application authorization
- **THEN** one candidate query retrieves every null-label weekly row and the repair reports proposals without changing the database

#### Scenario: Operator narrows the repair
- **WHEN** an operator supplies a week, application identifier, or candidate limit
- **THEN** discovery and mutation inspect no row outside the reported target

#### Scenario: Historical reviews are insufficient
- **WHEN** a selected row has fewer than 10 eligible reviews through its historical cutoff
- **THEN** the repair proposes `no_label` so the successfully processed row is distinguishable from an uncollected row

#### Scenario: A game appears in multiple weeks
- **WHEN** the candidate collection contains multiple weekly rows for the same game
- **THEN** the repair makes one histogram request for that game and derives each row's label using its own historical cutoff

#### Scenario: Histogram collection fails
- **WHEN** a game's histogram request fails or cannot be validated
- **THEN** every affected candidate is reported as failed, excluded from the update collection, and left null for a later repair attempt

#### Scenario: Authorized repair applies a label
- **WHEN** all provider discovery has finished and the operator explicitly authorizes mutation
- **THEN** the repair persists the complete validated update collection in one bulk operation and one transaction while preserving every numeric `rating`

#### Scenario: Authorized default repair covers all null rows
- **WHEN** the operator supplies `--apply` without a week, application identifier, or candidate limit
- **THEN** the repair reports the complete null-label candidate set as its effective target and permits that set to be applied in one transaction

#### Scenario: Candidate changes before persistence
- **WHEN** a selected row gains a non-null `rating_label` after discovery but before mutation
- **THEN** the guarded update leaves that row unchanged and does not report it as applied
