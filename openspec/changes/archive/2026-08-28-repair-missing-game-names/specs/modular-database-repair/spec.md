## ADDED Requirements

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
