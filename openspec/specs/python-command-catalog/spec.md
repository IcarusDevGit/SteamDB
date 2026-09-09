# Python Command Catalog Specification

## Purpose

Provide operators and contributors with a complete, reproducible reference for every supported Python command and argument while preventing newly registered commands from remaining undocumented.

## Requirements

### Requirement: Supported command inventory
The system SHALL maintain one authoritative inventory of supported Python operator commands covering the extraction entry point, standalone validation entry point, and every public apply, resolve, and repair subcommand. The supported inventory SHALL exclude retired, comparison, test-only, and non-CLI modules.

#### Scenario: Enumerating the current command surface
- **WHEN** the command inventory is loaded
- **THEN** it includes extraction, standalone validation, apply CSV, resolve tags, repair ratings, repair rating-labels, repair prices, repair weekly-stats, repair game-names, repair game-tags, and repair weekly-identities commands
- **AND** it does not classify files under `Python_legacy/`, comparison utilities, tests, or internal helpers as supported commands

#### Scenario: Registering a new supported command
- **WHEN** a contributor adds a supported command through the required command-registration mechanism
- **THEN** that command becomes part of the authoritative inventory used by documentation generation and completeness validation

### Requirement: Complete command documentation
The generated catalog SHALL document each supported command's canonical invocation, purpose, positional arguments, optional arguments, accepted values, defaults, required status, repeatability, operational effects, safety requirements, and representative examples wherever those properties apply.

#### Scenario: Rendering an argument reference
- **WHEN** the catalog is generated for a command with positional arguments, flags, choices, or defaults
- **THEN** the generated command section describes each applicable property using data from the runtime command parser

#### Scenario: Rendering operational guidance
- **WHEN** a command performs external reads, writes artifacts, changes PostgreSQL, defaults to dry-run, or requires explicit approval
- **THEN** its catalog entry clearly states those effects and safeguards

#### Scenario: Documenting environment-derived defaults
- **WHEN** a command-line default can be supplied by an environment variable
- **THEN** the catalog identifies the environment variable and explains command-line precedence

### Requirement: Runtime parser alignment
The catalog generator SHALL obtain command syntax and argument structure from the same parser definitions used to execute the commands, rather than maintaining a second handwritten argument list.

#### Scenario: Argument changes
- **WHEN** a registered runtime parser adds, removes, renames, or changes an argument
- **THEN** regenerating the catalog reflects that parser change without a separate edit to an argument table

#### Scenario: Parser registration failure
- **WHEN** a registered command cannot construct or expose its parser metadata
- **THEN** catalog generation fails with an error that identifies the affected command

### Requirement: Deprecated compatibility aliases
The catalog SHALL list hidden compatibility aliases separately from supported commands, label them deprecated, identify their canonical replacements, and avoid presenting them as recommended examples.

#### Scenario: Viewing a legacy alias
- **WHEN** an operator reads the compatibility section
- **THEN** each retained alias is shown with its canonical supported replacement
- **AND** the alias is absent from the primary supported-command catalog

### Requirement: Reproducible committed catalog
The project SHALL commit the generated command catalog under `docs/`, link it from both the repository README and active Python README, and provide a deterministic generation command.

#### Scenario: Generating without source changes
- **WHEN** the generator is run repeatedly against the same source tree
- **THEN** it produces byte-for-byte equivalent catalog content

#### Scenario: Navigating from project documentation
- **WHEN** a reader opens either README documentation index
- **THEN** the reader can navigate directly to the generated command catalog

### Requirement: Catalog completeness and freshness validation
Automated tests SHALL fail when a supported command is not represented by the authoritative inventory, when inventory entries are invalid or duplicated, or when the committed catalog differs from freshly generated output.

#### Scenario: Unregistered command is introduced
- **WHEN** a supported command is added to the maintained command surface without satisfying the registration convention
- **THEN** the command-catalog validation fails and identifies the missing registration

#### Scenario: Catalog is stale
- **WHEN** command parser or registry metadata changes without regenerating the committed catalog
- **THEN** the freshness validation fails and instructs the contributor to regenerate it

#### Scenario: Registry identity collision
- **WHEN** two supported command entries resolve to the same canonical invocation or registry identity
- **THEN** validation fails with the conflicting entries identified
