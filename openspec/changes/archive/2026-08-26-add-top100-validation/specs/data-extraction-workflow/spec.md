## MODIFIED Requirements

### Requirement: Reviewable helper output
The system SHALL process each requested week as an independent extraction unit, write exactly one week to each CSV, and automatically validate that CSV against Steam's corresponding global weekly Top 100 before proceeding to the next requested week. Passing CSVs and their reports SHALL be stored under `helpers/CSV`; CSVs with `failed` or `error` validation and their reports SHALL be stored under `helpers/CSV_error`. The workflow SHALL preserve and report every artifact produced even when another requested week fails extraction or validation.

#### Scenario: Extraction completes
- **WHEN** multiple requested weekly datasets are successfully enriched
- **THEN** the workflow writes and validates a separate single-week CSV for each requested date

#### Scenario: Post-extraction validation passes
- **WHEN** a weekly CSV exactly matches its corresponding weekly chart
- **THEN** the CSV and its sidecar report are stored under `helpers/CSV` and both paths are reported

#### Scenario: Post-extraction validation does not pass
- **WHEN** a weekly CSV mismatches its chart or the chart cannot be fetched or parsed
- **THEN** the CSV and its sidecar report are stored under `helpers/CSV_error` and both paths are reported

#### Scenario: Later requested week fails
- **WHEN** an earlier requested week has produced an outcome and a later week fails extraction or validation
- **THEN** the earlier week's CSV and report remain independently classified and available

#### Scenario: Requested weeks have mixed outcomes
- **WHEN** at least one requested week passes and another requested week fails extraction or validation
- **THEN** the command reports each weekly outcome and returns an unsuccessful overall process status without making a passing artifact ineligible
