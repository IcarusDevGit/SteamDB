## Context

See `proposal.md` for motivation. The active pipeline already requests Steam review histograms and reduces eligible rollups to one numeric positive ratio per application and week. That scalar discards the total review count required to distinguish Steam's labels. The value crosses typed extraction records, CSV review/validation, and a transactional `weeksheet` upsert. Existing numeric-rating repair selects only `rating IS NULL`, so it cannot repair rows whose numeric rating exists but label is absent.

## Goals / Non-Goals

**Goals:**

- Compute the ratio and label once from a cutoff-consistent review aggregate.
- Preserve numeric `rating` as a backward-compatible field and store labels separately.
- Use one classifier across extraction and repair paths.
- Backfill labels through the established dry-run, targeting, progress, and transaction conventions.

**Non-Goals:**

- Reproduce undocumented Steam review weighting or purchase-language filters beyond the supplied thresholds.
- Rewrite existing numeric ratings during a label repair.
- Automatically mutate the database during extraction.
- Conflate insufficient review volume with missing or failed label collection.

## Decisions

### Store labels in a separate nullable column

Add `weeksheet.rating_label` using a text-capable type while retaining `weeksheet.rating` as the numeric positive ratio. A constrained string set at validation and classification boundaries keeps CSVs readable and avoids coupling database deployment to a PostgreSQL enum migration. Overwriting `rating` was rejected because it would be a breaking type and meaning change.

### Preserve histogram counts until classification

Change the histogram parsing boundary to produce a small historical rating value containing positive count, total count, computed ratio, and label. Extraction consumes both public values from that result. This avoids a second Steam request and prevents reverse-engineering total counts from a ratio. Returning only a tuple was considered but rejected because named fields make the count and cutoff contract harder to misuse.

### Classify exact ratios with ordered count bands

Use integer positive and total counts and compare cross-products or the unrounded ratio against inclusive lower bounds. Select the total-count band first (`500+`, `50–499`, `10–49`, below 10), then its percentage threshold from highest to lowest. This makes all boundaries deterministic. Classification based on a rounded display percentage was rejected because rounding can move an observation across a supplied threshold.

### Extend the reviewed CSV contract

Add `rating_label` to extraction serialization and required CSV headers. A successfully collected population below 10 reviews serializes as `no_label`; an empty cell normalizes to null and indicates that collection did not complete. Other non-empty cells must exactly match a known Steam label. The database bulk candidate and conflict update include the new field. Chart identity validation remains indifferent to enrichment values, as it already is for numeric rating.

### Add a focused rating-label repair

Create a `rating-labels` repair module rather than expanding `repair ratings`. Candidate discovery issues one query for all matching `rating_label IS NULL` rows and materializes the result before any provider work. Optional `--week`, `--appid`, and `--limit` filters constrain that query; without filters, the reported null-row result set is the explicit safe default target for `--apply`.

Group the candidate collection by application ID. Request the complete histogram once for each unique game, then reuse its rollups to derive a label independently at every candidate week's cutoff. Append valid Steam labels and `no_label` outcomes to a separate update collection. A failed or invalid histogram excludes all of that game's candidates from the update collection so their null values remain retryable.

Only after every unique-game request reaches a terminal outcome does persistence begin. Persist the complete update collection through one values-based bulk statement in one transaction, with conflict/concurrency protection requiring each target's `rating_label` to remain null. Keeping the existing numeric-rating repair separate preserves its command semantics and avoids unexpectedly refetching populated ratings.

### Persist insufficient populations explicitly

An aggregate below 10 total reviews produces `no_label`. Extraction writes that sentinel to CSV and approved persistence stores it; repair includes it in the update collection. Null is reserved for rows that have not been processed successfully, including provider and malformed-payload failures. This makes repairs idempotent because successfully inspected low-volume rows are no longer selected.

## Risks / Trade-offs

- [Steam changes its public label thresholds] → Keep thresholds centralized and cover every count and percentage boundary with table-driven tests.
- [A schema migration and application release are deployed out of order] → Apply the additive nullable column before running updated CSV application or repair code; old code remains compatible with the added column.
- [Large backfills generate many Steam requests] → Retain provider scheduling, bounded targeting, progress events, and candidate limits; operators can apply in reviewed batches.
- [Loading all null rows and all successful updates increases memory use] → Store compact row dictionaries/records, report candidate and unique-game counts before provider work, and retain optional filters for operational batching.
- [One final transaction can be large or fail after lengthy discovery] → Use a bulk values operation, open the transaction only after discovery, and preserve all-or-nothing behavior so null rows remain safely retryable.
- [Historical endpoint data changes between extraction and repair] → Derive both values from one response per operation and document that repair reflects provider data available at repair time.

## Migration Plan

1. Add nullable `weeksheet.rating_label` without changing existing rows or `rating`.
2. Deploy shared aggregate/classifier and updated extraction/CSV persistence paths.
3. Deploy and document the `repair rating-labels` command.
4. Dry-run the complete null-row set or narrower weeks/application IDs, then apply the reviewed update collection; successful low-volume rows become `no_label` and failures remain null for retry.

Rollback application code to the prior version if necessary; the additive nullable column can remain safely unused. Dropping it would discard repaired labels and should only occur as a separately reviewed destructive migration.
