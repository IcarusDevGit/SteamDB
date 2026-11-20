## ADDED Requirements

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

