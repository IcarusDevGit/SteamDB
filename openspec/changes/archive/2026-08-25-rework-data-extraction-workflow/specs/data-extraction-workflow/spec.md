## Purpose

Defines a predictable, rate-limit-aware workflow for collecting and enriching weekly Steam seller data for operator-selected Tuesdays.

## ADDED Requirements

### Requirement: Multi-Tuesday extraction
The system SHALL accept one or more Tuesday dates in a single extraction run and SHALL collect the weekly top-seller dataset for every requested date.

#### Scenario: Multiple valid Tuesdays
- **WHEN** an operator starts extraction with multiple Tuesday dates
- **THEN** the output contains a distinct weekly dataset for every requested date

#### Scenario: Invalid weekly date
- **WHEN** an operator supplies a date that is not a Tuesday
- **THEN** the system rejects that date with a clear validation error before collecting its data

### Requirement: Weekly seller fields
For each weekly entry, the system SHALL retain the Steam application identifier, game name, rank, prior-week rank, consecutive weeks, categories, and target date returned or derived from the weekly source.

#### Scenario: Weekly entry collected
- **WHEN** the weekly top-seller source returns an entry
- **THEN** the extraction record includes all available required weekly seller fields

### Requirement: Dependency-aware asynchronous enrichment
The system SHALL permit bounded enrichment work for multiple entries to be in progress concurrently. For each entry, ITAD price history retrieval MUST wait for a resolved ITAD game identifier, and any conditional Steam HTML access MUST wait until ITAD history retrieval establishes whether fallback data is required. Historical Steam rating collection SHALL be independently eligible once the entry's Steam application identifier and target date are known.

#### Scenario: Entries progress concurrently
- **WHEN** one entry is waiting for a provider or dependency and another entry has eligible work
- **THEN** the system processes the eligible work without waiting for the first entry to complete

#### Scenario: ITAD history dependency
- **WHEN** an entry's ITAD game identifier has not been resolved
- **THEN** the system does not request ITAD history for that entry

#### Scenario: Steam HTML dependency
- **WHEN** an entry's ITAD history request has not completed
- **THEN** the system does not request Steam HTML for that entry

#### Scenario: Rating is independently eligible
- **WHEN** an entry has a Steam application identifier and target date but its ITAD chain is incomplete
- **THEN** the system may collect that entry's historical Steam rating

### Requirement: Provider-aware request scheduling
The system MUST enforce the request limits applicable to each external provider, MUST bound queued and in-flight work, and SHALL schedule eligible work across entries and providers without violating per-entry dependencies.

#### Scenario: One provider is throttled
- **WHEN** the next request to a provider must wait to remain within its request limit and an independent request to another provider is eligible
- **THEN** the system performs the eligible request instead of idling for the first provider

#### Scenario: No request is eligible
- **WHEN** every pending provider request is rate-limited or depends on unfinished data
- **THEN** the system waits until a request can be made without exceeding a provider limit

#### Scenario: Pipeline reaches its configured bound
- **WHEN** the number of queued or in-flight entries reaches the configured bound
- **THEN** the system applies backpressure and does not admit additional entries until capacity is available

### Requirement: Batched ITAD identifier lookup
The system SHALL combine eligible Steam shop identifiers into bounded ITAD identifier-lookup batches while respecting the account's configured request limit and the endpoint's accepted batch size.

#### Scenario: Multiple identifiers are eligible
- **WHEN** multiple entries require ITAD identifier resolution and batch capacity is available
- **THEN** the system resolves them in a shared lookup request rather than one request per entry

#### Scenario: Partial batch response
- **WHEN** ITAD returns mappings for only some identifiers in a batch
- **THEN** each returned mapping is associated with its entry and unmapped entries continue with no ITAD identifier

### Requirement: Historical rating cutoff
The system SHALL calculate each game's Steam rating using review histogram data only through the requested target date.

#### Scenario: Future reviews exist
- **WHEN** review data includes activity after the requested target date
- **THEN** that later activity does not affect the calculated rating

### Requirement: Price and discount precedence
The system SHALL use Steam price and discount history from ITAD when available. If ITAD has no Steam history values, the system SHALL omit unavailable ITAD values and SHALL attempt to populate price and discount from the Steam store page.

#### Scenario: ITAD history is available
- **WHEN** ITAD returns Steam price and discount history for the game and target date
- **THEN** the extracted record uses the ITAD values

#### Scenario: ITAD history is unavailable
- **WHEN** ITAD returns no Steam price or discount history for the game
- **THEN** no empty ITAD values are added and the system attempts the Steam store fallback

### Requirement: Reviewable helper output
After all requested dates and games are collected, the system SHALL write the combined extraction data to a CSV file for operator validation. All `.csv`, `.json`, and `.md` files generated by scripts SHALL be placed in the `helpers` directory.

#### Scenario: Extraction completes
- **WHEN** all requested weekly datasets have been enriched
- **THEN** a validation-ready CSV is created under `helpers`
