# Modular Database Repair Specification

## Purpose

Defines a safe, extensible operator workflow for inspecting and applying targeted database repairs without expanding the public update entry point into a monolith.

## Requirements

### Requirement: Stable repair command surface
The system SHALL expose database repairs through the existing update entry point, organize repairs as named operations, and report an error for an unknown operation without performing database writes.

#### Scenario: Operator selects a known repair
- **WHEN** the operator invokes the update entry point with a registered repair name
- **THEN** the system dispatches that repair with the supplied target options

#### Scenario: Operator selects an unknown repair
- **WHEN** the operator invokes a repair name that is not registered
- **THEN** the system reports the supported commands and performs no database writes

### Requirement: Repairs are non-mutating by default
Every repair operation SHALL inspect and report proposed changes without mutating the database unless the operator explicitly authorizes application.

#### Scenario: Repair is invoked without application authorization
- **WHEN** the operator runs a repair without the explicit apply option
- **THEN** the system reports the proposed repair outcome and leaves the database unchanged

#### Scenario: Repair is explicitly applied
- **WHEN** the operator runs a repair with explicit application authorization and validation succeeds
- **THEN** the system applies only the targeted validated changes

### Requirement: Repairs support bounded targeting
Each repair operation SHALL support at least one operation-appropriate target that bounds its candidate records, such as week, application id, or maximum record count, and SHALL state the effective target before application.

#### Scenario: Operator supplies a target
- **WHEN** the operator limits a repair to a week or application id
- **THEN** the system inspects and applies no records outside that target

#### Scenario: Repair would have an unbounded target
- **WHEN** an apply request does not provide an operation-appropriate bound
- **THEN** the system refuses mutation unless that repair explicitly defines and reports a safe bounded default

### Requirement: Repair outcomes are reported consistently
Every repair SHALL report proposed, applied, skipped, and failed counts and SHALL return a failing process result when validation or application fails.

#### Scenario: Repair completes with mixed candidate outcomes
- **WHEN** some candidates are applicable and others are unavailable or invalid
- **THEN** the system reports each outcome category without representing skipped or failed candidates as applied

#### Scenario: Repair application fails
- **WHEN** a repair cannot validate or persist its authorized changes
- **THEN** the command reports the failure and exits unsuccessfully

### Requirement: External discovery and persistence remain separated
A repair that obtains replacement data from an external provider SHALL finish candidate discovery and validation before opening its mutation transaction. Each repair module SHALL own its operation-specific database reads and transactional writes while obtaining connections through the shared database connection facility.

#### Scenario: Provider returns no reliable replacement
- **WHEN** the external provider has no valid replacement value for a candidate
- **THEN** the repair skips that candidate and does not overwrite the stored value

#### Scenario: Valid candidates are authorized for application
- **WHEN** discovery and validation complete and the operator authorizes application
- **THEN** the owning repair module transactionally persists only the validated targeted changes

### Requirement: Repair modules own repair-specific persistence
Each repair operation SHALL own the candidate-selection queries and mutation statements specific to that operation. Repair operations SHALL obtain PostgreSQL connections through the shared connection facility used by the main database workflow, and adding a repair SHALL NOT require adding repair-specific query or mutation methods to the main database workflow boundary.

#### Scenario: Contributor adds a repair operation
- **WHEN** a contributor implements a new named repair
- **THEN** its repair module contains the operation-specific candidate reads and writes while reusing the shared PostgreSQL connection facility

#### Scenario: Existing repair persistence is organized by operation
- **WHEN** rating, price, or weekly-stat repairs select or mutate their records
- **THEN** the corresponding repair module owns those database statements and transaction behavior

### Requirement: Game names can be repaired by application ID
The system SHALL provide a named repair that selects catalog games whose stored name becomes empty after trimming whitespace and obtains an English display name from Steam using each game's application ID. The default selection SHALL exclude populated and null names. The repair SHALL allow the operator to narrow selection by application ID or maximum candidate count, SHALL validate a replacement as nonblank before proposing it, and SHALL update the targeted game only when the operator explicitly authorizes mutation and its stored name remains whitespace-only.

#### Scenario: Default repair selects whitespace-only names
- **WHEN** the operator runs the game-name repair without an application ID or candidate limit
- **THEN** the repair selects every game whose stored name is an empty or whitespace-only string
- **AND** it excludes games whose stored name is populated or null

#### Scenario: Game name resolves successfully
- **WHEN** Steam returns a nonblank English display name for a selected application's ID
- **THEN** the repair proposes that normalized name and replaces the targeted whitespace-only stored name only when the operator explicitly authorizes mutation

#### Scenario: Steam does not provide a usable name
- **WHEN** Steam reports an unavailable application, returns no name, or returns a blank name for a candidate
- **THEN** the repair skips that candidate, reports the unavailable result, and leaves the stored name unchanged

#### Scenario: Operator narrows the repair
- **WHEN** an operator supplies an application ID or maximum candidate count
- **THEN** the repair inspects and mutates no whitespace-name candidate outside the reported bound

#### Scenario: Authorized default repair
- **WHEN** the operator supplies `--apply` without an application ID or candidate limit
- **THEN** the repair transactionally applies every valid resolved name in the default whitespace-only selection

#### Scenario: Candidate changes before mutation
- **WHEN** a selected game's stored name becomes populated or null after discovery but before mutation
- **THEN** the guarded update leaves that game unchanged and does not report it as applied

### Requirement: Empty catalog game tags can be repaired from Steam HTML
The system SHALL provide a named repair that selects every catalog game whose tag collection is null or empty by default and obtains community tag names from that application's English Steam store HTML. The repair SHALL resolve discovered names through the existing catalog and configured tag aliases, SHALL propose only unique resolved tag identifiers, and SHALL not create tag identities for unresolved names. It SHALL allow the operator to narrow selection by application ID or maximum candidate count and SHALL remain non-mutating unless application is explicitly authorized.

#### Scenario: Default repair selects all empty-tag games
- **WHEN** the operator runs the game-tag repair without an application ID or candidate limit
- **THEN** the repair selects every game whose tag collection is null or empty
- **AND** it excludes every game with at least one stored tag identifier

#### Scenario: Steam tags resolve successfully
- **WHEN** Steam HTML supplies one or more community tag names that resolve to catalog tag identifiers
- **THEN** the repair proposes the unique resolved identifiers in source order
- **AND** it stores them only when the operator explicitly authorizes mutation

#### Scenario: Steam supplies unresolved tag names
- **WHEN** one or more Steam community tag names do not resolve through the catalog or configured aliases
- **THEN** the repair reports each unresolved name without inventing or inserting a tag identity
- **AND** it may still propose and apply the successfully resolved identifiers for that game

#### Scenario: Steam supplies no usable resolved tags
- **WHEN** Steam is unavailable, the store page has no community tags, or none of its tag names resolve
- **THEN** the repair reports the candidate as unavailable, skipped, or failed as appropriate
- **AND** it leaves the stored tag collection unchanged

#### Scenario: Operator narrows the repair
- **WHEN** the operator supplies an application ID or maximum candidate count
- **THEN** the repair inspects and mutates no empty-tag candidate outside the reported bound

#### Scenario: Authorized default repair
- **WHEN** the operator supplies `--apply` without an application ID or candidate limit
- **THEN** the repair transactionally applies every valid proposal in the default empty-tag selection

#### Scenario: Candidate changes before mutation
- **WHEN** a selected game gains at least one stored tag after discovery but before mutation
- **THEN** the guarded update leaves that game unchanged and does not report it as applied

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

### Requirement: Repair workflows provide live operator progress
Every public repair command SHALL emit immediately flushed terminal progress throughout candidate selection, external lookup, and authorized persistence. Progress SHALL identify the repair operation and active phase; enumerable work SHALL additionally report completed and total units plus the candidate, rank, or week identity needed to locate the current work. A repair SHALL report failures at the stage or candidate where they occur rather than remaining silent until its final summary.

#### Scenario: Repair selects database candidates
- **WHEN** a repair begins and completes candidate selection
- **THEN** the terminal reports both stage transitions and the number of selected candidates

#### Scenario: External candidate lookup runs
- **WHEN** a repair starts an external request for a candidate or selected week
- **THEN** the terminal identifies the provider step and candidate or week before the request begins
- **AND** it reports that unit as completed, unavailable, or failed when the request reaches a terminal state

#### Scenario: Price repair changes provider step
- **WHEN** price discovery performs shared ITAD lookup, per-candidate ITAD history, or Steam fallback work
- **THEN** progress identifies the active provider step and the affected candidate set or candidate identity

#### Scenario: Provider request is retried
- **WHEN** a repair retries a transient provider failure or waits for provider backoff
- **THEN** progress identifies the provider, upcoming attempt, and wait duration before waiting

#### Scenario: Authorized persistence processes multiple records
- **WHEN** a repair transaction persists enumerable candidates or weeks
- **THEN** progress reports monotonic completed/total persistence counts and the identity of each completed unit
- **AND** the transaction retains its existing all-or-nothing commit boundary

#### Scenario: Repair stage fails
- **WHEN** candidate selection, external lookup, or persistence terminates with an error
- **THEN** the terminal immediately reports the failed stage and error before the command exits unsuccessfully

### Requirement: Repair progress preserves stream compatibility
Command-line repair progress SHALL be written immediately to standard error, while the existing final repair result SHALL remain on standard output with unchanged outcome fields and exit-code behavior. Repair functions SHALL accept optional reporting so non-command-line callers can run without terminal output.

#### Scenario: Repair runs from the command line
- **WHEN** an operator invokes a repair through the update entry point
- **THEN** each progress event is flushed to standard error as it occurs
- **AND** the final proposed, applied, skipped, and failed summary remains on standard output

#### Scenario: Repair is embedded without a reporter
- **WHEN** a non-command-line caller invokes repair discovery or persistence without a reporter
- **THEN** the repair performs the same work without writing terminal progress

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
