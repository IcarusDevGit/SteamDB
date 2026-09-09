## MODIFIED Requirements

### Requirement: Historical rating cutoff
The system SHALL calculate each game's numeric Steam rating and Steam rating label from the same review histogram aggregate containing data only through the closed requested chart week.

#### Scenario: Future reviews exist
- **WHEN** review data includes activity at or after the Tuesday following the requested chart week
- **THEN** that later activity affects neither the calculated numeric rating nor the calculated rating label

#### Scenario: Rating enrichment completes
- **WHEN** eligible historical histogram data is available for an entry
- **THEN** the extraction record and reviewable CSV contain the numeric rating and the label produced from the same historical aggregate

#### Scenario: Rating enrichment finds insufficient reviews
- **WHEN** the historical aggregate contains fewer than 10 eligible reviews
- **THEN** the extraction record and reviewable CSV contain `no_label` rather than a null rating label
