# Data Extraction Workflow Specification

## Purpose

Defines a predictable, rate-limit-aware workflow for collecting and enriching weekly Steam seller data for operator-selected Tuesdays.

## Requirements

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

### Requirement: Live operator progress
The command-line extraction workflow SHALL emit flushed operational progress throughout each requested week's processing so an operator can observe forward movement without waiting for the final outcome. Progress SHALL identify stage transitions for weekly collection, identifier lookup, record enrichment, CSV writing, and validation. When a provider request is retried after a retryable failure, progress SHALL identify the provider, retry attempt, and expected wait duration.

#### Scenario: Weekly workflow advances through stages
- **WHEN** an operator starts a weekly extraction from the command line
- **THEN** the terminal reports the start and completion of each applicable workflow stage as it occurs

#### Scenario: Provider request enters retry backoff
- **WHEN** a retryable provider failure causes the workflow to wait before another attempt
- **THEN** the terminal reports the provider, upcoming retry attempt, and backoff duration before the wait begins

### Requirement: Concurrent record completion counter
After the weekly records are known, the command-line workflow SHALL emit exactly one consolidated completion message whenever an individual record reaches its terminal enrichment state. Each message MUST include the completed-record count, total-record count, week, rank, application identifier, name, terminal outcome of each enrichment branch, tag source, unresolved-tag count, and error count. The completed count SHALL be monotonic and SHALL reflect completion order rather than chart rank order.

#### Scenario: Records complete out of rank order
- **WHEN** concurrent enrichment causes a lower-ranked record to finish before a higher-ranked record
- **THEN** the next completion message increments the completed count and identifies the record that actually completed without waiting for rank order

#### Scenario: Record completes with absent or failed enrichment
- **WHEN** all enrichment branches for a record are terminal but one or more values are absent or failed
- **THEN** the workflow counts the record as completed and reports its branch outcomes and error count

#### Scenario: All records reach terminal state
- **WHEN** enrichment completes for every record in a week
- **THEN** the final record message reports a completed count equal to the total record count

### Requirement: Progress stream compatibility
Operational progress SHALL be written to standard error and SHALL be emitted immediately. The existing final per-week outcome SHALL remain on standard output with its current fields, and progress reporting SHALL NOT change established exit-code behavior. Non-command-line callers SHALL be able to run extraction without receiving terminal progress output.

#### Scenario: Command output is redirected
- **WHEN** standard output and standard error are captured separately
- **THEN** stage, retry, and record progress appears only on standard error and the final per-week outcome appears on standard output

#### Scenario: Extraction is used without a terminal reporter
- **WHEN** a caller invokes the extraction workflow without supplying progress reporting
- **THEN** extraction behavior and returned records remain unchanged and no progress output is emitted

#### Scenario: Weekly extraction fails
- **WHEN** a requested week fails during extraction, CSV writing, or validation
- **THEN** progress identifies the failed stage and the command preserves its established unsuccessful exit status and per-week error reporting

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
