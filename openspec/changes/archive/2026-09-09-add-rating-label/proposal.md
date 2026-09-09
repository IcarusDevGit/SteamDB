## Why

Weekly rows currently retain only Steam's historical positive-review ratio, so consumers cannot directly use the rating label Steam presents for the same review population. Existing rows also need a safe way to acquire labels without overwriting their numeric ratings.

## What Changes

- Add a nullable `rating_label` value to weekly extraction records, CSV artifacts, validation, and `weeksheet` persistence while preserving the existing numeric `rating` value.
- Derive historical labels from cumulative positive and negative histogram reviews through the same closed-week cutoff used for numeric ratings.
- Apply the supplied Steam label thresholds by both positive percentage and total review count; store `no_label` when fewer than 10 reviews are available so null remains reserved for data that has not been collected.
- Add a dry-run-first `repair rating-labels` operation that loads null-label rows once, groups them by game, fetches each game's histogram once, derives every required historical-week label, and bulk-persists the collected results at the end.
- Extend command documentation, progress reporting, and automated coverage for extraction, persistence, classification boundaries, and repairs.

## Capabilities

### New Capabilities

- `historical-rating-labels`: Defines historical review aggregation, deterministic label classification, and behavior when a label cannot yet be assigned.

### Modified Capabilities

- `data-extraction-workflow`: Historical rating enrichment will produce both the existing numeric ratio and the new label from one cutoff-consistent review aggregate.
- `validated-database-update`: Approved CSV validation and transactional weekly upserts will accept and persist `rating_label` without replacing numeric `rating`.
- `modular-database-repair`: Adds a guarded, observable repair for null weekly rating labels.
- `python-command-catalog`: Adds the public `repair rating-labels` command to the authoritative operator-command inventory.

## Impact

- Affects the PostgreSQL `weeksheet` schema and any disposable test schema representing it.
- Affects Steam histogram parsing/client contracts, extraction records and orchestration, CSV serialization and validation, bulk weekly upserts, repair registration, command metadata, documentation, and tests.
- Uses the existing Steam histogram endpoint and request scheduling; no new external service or dependency is introduced.
