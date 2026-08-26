# Catalog Tag Synchronization Specification

## Purpose

Defines how weekly categories and Steam tags are collected, normalized, and prepared for consistent storage in the games and tags tables.

## Requirements

### Requirement: Conditional Steam tag collection
The system SHALL collect tags from a game's Steam store page only when that game is not already present in the games table.

#### Scenario: New game
- **WHEN** an extracted Steam application identifier is absent from the games table
- **THEN** the system collects its Steam store tags

#### Scenario: Existing game
- **WHEN** an extracted Steam application identifier already exists in the games table
- **THEN** the system does not request Steam store tags for that game

### Requirement: Tag exception mapping
The system SHALL map any collected tag name present in `Exceptions.json` to the corresponding tag identifier defined there before preparing database updates.

#### Scenario: Exception exists
- **WHEN** a collected tag name matches an entry in `Exceptions.json`
- **THEN** the game record uses the identifier mapped by that exception

### Requirement: Category name lookup on demand
The system SHALL request Steam app-details data for a weekly category identifier only when that category is not present in the tags table, and SHALL use the resolved name when preparing the missing tag for insertion.

#### Scenario: Unknown weekly category
- **WHEN** a weekly category identifier is absent from the tags table
- **THEN** the system resolves its name through Steam app details and prepares the identifier and name for insertion

#### Scenario: Known weekly category
- **WHEN** a weekly category identifier is already present in the tags table
- **THEN** the system does not make an app-details request for that category

### Requirement: Canonical game tag identifiers
Weekly categories and Steam store tags SHALL contribute only their canonical identifiers to the games table tag list, while the tags table SHALL store each identifier with its corresponding name.

#### Scenario: New game or tag encountered
- **WHEN** validated extraction data contains a game or tag absent from its destination table
- **THEN** the database update prepares the missing entity for insertion and associates the game with tag identifiers rather than tag names

### Requirement: Unresolved tag handling
Collected tag names that cannot be mapped through existing tags, Steam data, or exceptions SHALL remain available to the existing manual exception workflow rather than being silently discarded or assigned an invented identifier.

#### Scenario: Tag remains unresolved
- **WHEN** a collected tag has no known identifier after automatic resolution
- **THEN** the update workflow presents it for manual addition to the tags table or exceptions list
