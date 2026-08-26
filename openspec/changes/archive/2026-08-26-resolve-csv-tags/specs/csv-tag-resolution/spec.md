## Purpose

Provides a guarded operator workflow for resolving tag names in a completed review CSV, regenerating validation evidence, and keeping all database mutation behind the separately approved application command.

## ADDED Requirements

### Requirement: Resolver discovers mappings without mutation
The system SHALL provide a CSV tag-resolution command that is non-mutating by default, deduplicates unresolved names case-insensitively, and proposes mappings in precedence order from normalized database tags, configured exceptions, the Steam tag list, and explicit operator mappings.

#### Scenario: Database name differs only by formatting
- **WHEN** an unresolved name matches a database tag after trimming surrounding whitespace and applying case-insensitive comparison
- **THEN** the resolver proposes the existing database tag identifier and a trimmed canonical name without requesting Steam data

#### Scenario: Exception maps an alias
- **WHEN** an unresolved name has no normalized database match but is present in the exception mapping
- **THEN** the resolver proposes the exception's tag identifier and its known canonical database name when available

#### Scenario: Steam lookup is needed
- **WHEN** one or more unresolved names remain after database and exception matching
- **THEN** the resolver fetches the Steam tag list once for the invocation and proposes exact normalized name matches

#### Scenario: Command runs without application authorization
- **WHEN** the operator runs tag resolution without `--apply`
- **THEN** the command reports proposed, unresolved, and failed outcomes without changing the CSV, sidecar report, exception file, or database

### Requirement: Explicit mappings are validated
The resolver SHALL accept repeatable explicit `NAME=ID` mappings and SHALL reject malformed, non-positive, ambiguous, or catalog-contradicting mappings before changing any artifact.

#### Scenario: Valid explicit mapping is supplied
- **WHEN** an otherwise unresolved name receives one unambiguous positive tag identifier consistent with known catalog identities
- **THEN** the resolver proposes that mapping and identifies it as operator-supplied

#### Scenario: Explicit mappings conflict
- **WHEN** one name maps to multiple identifiers, one identifier maps to contradictory canonical names, or a mapping conflicts with an existing catalog identity
- **THEN** the resolver rejects application, describes the conflict, and changes no artifact

### Requirement: Applied resolution safely rewrites the reviewed artifact
With explicit `--apply` authorization, the resolver SHALL verify that the input CSV has a passing matching sidecar, update each affected row's aligned `tags`, `tag_ids`, and `unresolved_tags` fields, preserve unrelated fields and unresolved names without mappings, and replace each changed artifact through an atomic file operation.

#### Scenario: All names resolve
- **WHEN** every unresolved name receives a valid mapping and the operator supplies `--apply`
- **THEN** the corrected CSV contains aligned unique tag name/identifier pairs, contains no unresolved names, and remains unchanged in every unrelated field

#### Scenario: Some names remain unresolved
- **WHEN** at least one unresolved name has no valid mapping during an authorized run
- **THEN** resolved names are corrected, unresolved names remain listed, and the command returns an unsuccessful outcome that continues to block database application

#### Scenario: Original evidence is missing or stale
- **WHEN** the CSV lacks a passing sidecar whose digest and week match the unmodified input
- **THEN** the resolver refuses to edit the CSV or exception file

### Requirement: Corrected artifacts receive fresh validation evidence
After an authorized CSV rewrite, the resolver SHALL revalidate the changed CSV, bind a new sidecar report to its exact bytes, and report the final classified CSV and sidecar paths.

#### Scenario: Corrected chart identities still pass
- **WHEN** resolution changes only tag enrichment fields and chart revalidation succeeds
- **THEN** the corrected CSV and fresh passing sidecar are reported as eligible for approval once no unresolved tags remain

#### Scenario: Revalidation fails or errors
- **WHEN** the corrected CSV no longer matches the chart or chart validation cannot complete
- **THEN** the command reports the failed or error status and the resulting artifacts remain ineligible for database application

### Requirement: Resolution does not mutate the database
The resolver SHALL NOT insert or update tags, games, or weekly records; database mutation SHALL remain under separately authorized update operations.

#### Scenario: Mapping identifies a tag absent from the database
- **WHEN** Steam or an explicit mapping resolves a tag identifier not present in the catalog
- **THEN** the resolver records the mapping only in the reviewed artifact and applicable exception configuration for later approved application

#### Scenario: Resolved tag belongs to an existing game
- **WHEN** a corrected CSV associates a resolved tag with a game already present in the catalog
- **THEN** the resolver does not update that game's stored tag array

