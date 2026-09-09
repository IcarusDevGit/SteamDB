## MODIFIED Requirements

### Requirement: Supported command inventory
The system SHALL maintain one authoritative inventory of supported Python operator commands covering the extraction entry point, standalone validation entry point, and every public apply, resolve, and repair subcommand. The supported inventory SHALL exclude retired, comparison, test-only, and non-CLI modules.

#### Scenario: Enumerating the current command surface
- **WHEN** the command inventory is loaded
- **THEN** it includes extraction, standalone validation, apply CSV, resolve tags, repair ratings, repair rating-labels, repair prices, repair weekly-stats, repair game-names, repair game-tags, and repair weekly-identities commands
- **AND** it does not classify files under `Python_legacy/`, comparison utilities, tests, or internal helpers as supported commands

#### Scenario: Registering a new supported command
- **WHEN** a contributor adds a supported command through the required command-registration mechanism
- **THEN** that command becomes part of the authoritative inventory used by documentation generation and completeness validation
