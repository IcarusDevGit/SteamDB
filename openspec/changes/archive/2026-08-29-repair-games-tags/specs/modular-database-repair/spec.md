## ADDED Requirements

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

