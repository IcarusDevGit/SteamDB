## MODIFIED Requirements

### Requirement: Update existing and missing records
The database update workflow SHALL reconcile the complete set of validated weekly records, insert validated games and resolved tags that do not yet exist, and preserve the stored attributes of games and tags already present. Changes to existing game or tag catalog attributes SHALL require a separately selected database update operation. The workflow SHALL avoid duplicating entities or violating weekly game and rank uniqueness.

#### Scenario: Validated data contains mixed record states
- **WHEN** an approved CSV contains existing and missing games or resolved tags
- **THEN** missing games and tags are inserted, existing game names and tag associations remain unchanged, existing tag names remain unchanged, and the validated weekly records are reconciled

#### Scenario: Existing catalog values differ from the CSV
- **WHEN** an approved CSV supplies a name or tag association that differs from the stored value for an existing game or tag
- **THEN** CSV application preserves the stored catalog value and does not implicitly perform a catalog repair

#### Scenario: Games exchange weekly ranks
- **WHEN** validated records assign existing games to ranks currently occupied by other games in the same week
- **THEN** the workflow reconciles the complete week without a transient or final weekly uniqueness conflict
