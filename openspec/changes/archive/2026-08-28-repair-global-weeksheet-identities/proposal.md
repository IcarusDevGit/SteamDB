## Why

Historical `weeksheet` rows were populated by a legacy fetcher that requested the US weekly sellers chart instead of Steam's global Top 100. Seven of the ten stored weeks currently differ from the validated global identities, so operators need a controlled repair that restores authoritative membership and rank without inventing enrichment data.

## What Changes

- Add a public `repair weekly-identities` operation that inspects every distinct stored `weeksheet.week_date` by default, with an optional single-week target.
- Fetch and validate exactly 100 unique global Steam chart identities for every selected stored date, independent of configurable extraction country settings.
- Report missing global games, unexpected stored games, wrong ranks, unchanged identities, and malformed/provider failures before any mutation.
- On explicit application, atomically reconcile selected mismatched weeks to the validated global membership and rank set.
- Emit bounded persistence progress, including the current phase or week and completed/total counts, so operators receive visible feedback throughout a multi-week transaction.
- Preserve existing price, discount, and rating values by week/game identity for games retained in the global chart.
- Populate new weekly rows only with data present in the global Top 100 response; leave price, discount, and rating null and use an empty tag set for newly required catalog games.
- Remove US-only weekly rows without deleting their reusable `games` catalog entries.
- Register and document the command through the existing command-catalog workflow.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `modular-database-repair`: Define validated global-chart comparison, full stored-date discovery, safe weekly identity reconciliation, enrichment preservation, and null defaults for newly inserted identities.
- `python-command-catalog`: Include the new supported weekly-identity repair in the authoritative generated operator inventory.

## Impact

- Adds a focused repair module under `Python/database_updates/repairs/` with module-owned candidate and mutation SQL.
- Reuses the active global Top 100 validation request and exact identity guarantees while adding access to global response fields needed for reconciliation.
- Writes `weeksheet` membership/rank/stat fields and may insert missing `games` catalog rows; no database schema migration is required.
- Updates repair, provider, discovery and persistence progress, parser, command-catalog, disposable PostgreSQL integration, and operator documentation coverage.
- Does not modify `Python_legacy/`, enrich new rows from reviews/ITAD/store HTML/tag providers, create dates absent from `weeksheet`, or delete catalog games.
