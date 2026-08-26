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
A repair that obtains replacement data from an external provider SHALL finish candidate discovery and validation before requesting database mutation, and all database reads and writes SHALL use the dedicated database access boundary.

#### Scenario: Provider returns no reliable replacement
- **WHEN** the external provider has no valid replacement value for a candidate
- **THEN** the repair skips that candidate and does not overwrite the stored value

#### Scenario: Valid candidates are authorized for application
- **WHEN** discovery and validation complete and the operator authorizes application
- **THEN** the repair delegates the validated changes to the database boundary for transactional persistence
