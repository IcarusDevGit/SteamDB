## ADDED Requirements

### Requirement: Completed CSV reports unresolved tags
After producing and validating each weekly CSV, the extraction command SHALL report the count and alphabetically ordered unique names of unresolved tags, the affected game name, application identifier, and rank for each name, and the exact resolver command for the final CSV path.

#### Scenario: Completed week has unresolved tags
- **WHEN** a weekly CSV and sidecar report are completed with one or more unresolved tag names
- **THEN** the terminal output lists each unique unresolved name with its affected games and prints the command for resolving that specific CSV

#### Scenario: Completed week has no unresolved tags
- **WHEN** a weekly CSV and sidecar report are completed with no unresolved tag names
- **THEN** the terminal output explicitly reports an unresolved-tag count of zero

#### Scenario: Multiple weeks complete independently
- **WHEN** one invocation produces CSV artifacts for multiple weeks
- **THEN** each completed week receives its own unresolved summary and resolver command using that week's final classified CSV path

#### Scenario: Extraction fails before CSV creation
- **WHEN** a week fails before a CSV artifact is produced
- **THEN** the workflow reports the stage failure without claiming an unresolved-tag summary for that week

