## ADDED Requirements

### Requirement: Rating label validation and persistence
The validated database update workflow SHALL accept a nullable `rating_label` CSV field, SHALL treat `no_label` as the defined value for a successfully collected population below 10 reviews, SHALL reject other non-null values outside the defined Steam label set, and SHALL persist it to `weeksheet.rating_label` in the same transaction as the remaining weekly fields without replacing or reinterpreting numeric `rating`.

#### Scenario: Approved row has a valid label
- **WHEN** an approved CSV row contains one of the defined rating labels
- **THEN** the weekly upsert stores that value in `rating_label` and independently stores the row's numeric `rating`

#### Scenario: Approved row has no label
- **WHEN** an approved CSV row has an empty rating label
- **THEN** the weekly upsert stores a null `rating_label` to represent data that was not successfully collected

#### Scenario: Approved row has insufficient reviews
- **WHEN** an approved CSV row contains `no_label`
- **THEN** the weekly upsert stores `no_label` rather than null

#### Scenario: CSV contains an unknown label
- **WHEN** a CSV row contains a non-empty rating label outside the defined label set
- **THEN** validation rejects the CSV before database mutation
