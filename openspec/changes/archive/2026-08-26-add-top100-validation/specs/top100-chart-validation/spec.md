## Purpose

Defines exact Steam Top 100 membership and rank validation, classification, and evidence for single-week CSV artifacts before they can be approved for database application.

## ADDED Requirements

### Requirement: Exact weekly rank and application validation
The system SHALL compare every extracted weekly entry to Steam's global weekly Top 100 using only the target week, rank, and Steam application identifier. A week SHALL pass only when every expected rank is present exactly once and contains the expected application identifier, with no extra entries.

#### Scenario: Weekly entries match exactly
- **WHEN** the extracted week and Steam global chart contain the same application identifier at every expected rank
- **THEN** that week passes chart validation

#### Scenario: Application is assigned to the wrong rank
- **WHEN** an expected application identifier exists in the extraction at a different rank
- **THEN** the report identifies its expected and actual ranks and the week fails validation

#### Scenario: Weekly membership differs
- **WHEN** an expected application is absent or an unexpected application is present
- **THEN** the report identifies the missing or unexpected entry and the week fails validation

### Requirement: Complete and unique weekly input
The system SHALL require each validated week to contain the complete expected Top 100 rank set and SHALL reject duplicate ranks or duplicate application identifiers within that week.

#### Scenario: Week contains all entries
- **WHEN** the extraction contains exactly one entry for each expected Top 100 rank
- **THEN** count and uniqueness validation succeeds

#### Scenario: Week has an incorrect entry count
- **WHEN** a week contains fewer or more entries than the Steam global Top 100
- **THEN** the report identifies the expected and actual counts and the week fails validation

#### Scenario: Week contains a duplicate
- **WHEN** a week contains a duplicate rank or application identifier
- **THEN** the report identifies the duplicate and the week fails validation

### Requirement: Validation input contains one week
The system SHALL require a validation CSV to contain exactly one distinct week and SHALL compare it only with the corresponding Steam global weekly chart.

#### Scenario: Single-week CSV is accepted
- **WHEN** every row in a CSV belongs to the same week
- **THEN** the validator obtains and compares that week's corresponding global weekly chart

#### Scenario: Multi-week CSV is rejected
- **WHEN** a CSV contains more than one distinct week
- **THEN** validation records an `error` and requires separate weekly CSVs

### Requirement: Digest-bound sidecar report
The system SHALL write a structured sidecar report beside the weekly CSV containing a SHA-256 digest of the exact CSV bytes, the CSV's week, counts and differences, and a `passed`, `failed`, or `error` status.

#### Scenario: Exact comparison succeeds
- **WHEN** the CSV week exactly matches its chart
- **THEN** the sidecar report records `passed`, the CSV digest, and no differences

#### Scenario: Comparison finds a mismatch
- **WHEN** membership, ordering, count, or uniqueness validation fails
- **THEN** the report records `failed`, the CSV digest, and actionable differences for the CSV week

#### Scenario: Chart cannot be validated
- **WHEN** Steam cannot be fetched or its chart cannot be parsed reliably
- **THEN** the report records `error`, the CSV digest, and the validation error

### Requirement: Validation preserves review artifacts
The system SHALL preserve the extraction CSV and write its validation report regardless of outcome. It SHALL place the CSV and report under `helpers/CSV` only for `passed`, and under `helpers/CSV_error` for `failed` or `error`.

#### Scenario: Validation passes
- **WHEN** chart validation records `passed`
- **THEN** the CSV and sidecar report are retained together under `helpers/CSV`

#### Scenario: Validation fails after extraction
- **WHEN** chart validation reports a mismatch
- **THEN** the CSV and sidecar report remain together under `helpers/CSV_error` for operator inspection and correction

#### Scenario: Validation cannot complete
- **WHEN** chart validation encounters a fetch or parser error
- **THEN** the CSV and `error` sidecar report remain together under `helpers/CSV_error` for retry and diagnosis

#### Scenario: Corrected CSV is revalidated
- **WHEN** an operator changes a failed CSV and runs validation again
- **THEN** the system performs a new comparison, replaces the sidecar with a result bound to the changed CSV bytes, and classifies both artifacts according to the new outcome

### Requirement: Validator process outcomes
The standalone validator SHALL return success only for an exact match, SHALL distinguish chart mismatch from fetch or parsing failure through its process result, and SHALL report the CSV and sidecar paths.

#### Scenario: Standalone validation passes
- **WHEN** the standalone validator confirms an exact match
- **THEN** it exits successfully and reports both artifact paths

#### Scenario: Standalone validation does not pass
- **WHEN** the standalone validator finds a mismatch or encounters an external validation error
- **THEN** it exits unsuccessfully while still reporting both preserved artifact paths

### Requirement: Enrichment fields are outside chart validation
Chart validation SHALL NOT decide pass or fail from game name, rating, tags, price, discount, or other enrichment values.

#### Scenario: Enrichment differs while rank identity matches
- **WHEN** all weekly rank and application pairs match but an enrichment value differs
- **THEN** the enrichment difference does not cause chart validation to fail
