## ADDED Requirements

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
