## Context

The legacy weekly fetcher requested `country="US"` for both chart selection and storefront context. The active validator already builds an explicitly global request, verifies exactly 100 unique rank/application identities, and cross-checks the rendered chart prefix. `weeksheet` enforces uniqueness for week/rank and week/game, while enrichment belongs to a week/game identity rather than to a rank. Repair modules own operation-specific SQL and obtain connections through `db.get_connection`. See `proposal.md` for motivation and the delta specs for behavioral requirements.

## Goals / Non-Goals

**Goals:**

- Reuse one authoritative global-chart validation path for comparison and repair evidence.
- Reconcile complete stored weekly identity sets without transient uniqueness conflicts.
- Preserve retained games' enrichment by week/game identity.
- Keep all provider work outside one all-or-nothing repair transaction.

**Non-Goals:**

- Creating weeks for Tuesday dates that do not already exist in `weeksheet`.
- Fetching or deriving rating, price, discount, tags, or other enrichment from non-chart providers.
- Deleting catalog games made unused by weekly reconciliation.
- Modifying the legacy source tree or changing database constraints.

## Decisions

### Add a focused `weekly_identities` repair module

The module will register `repair weekly-identities`, own stored-date/candidate SQL and reconciliation SQL, orchestrate global discovery, and return standard repair results. This keeps identity correction separate from `weekly-stats`, which assumes membership and rank are already correct and only changes two metadata fields. Expanding CSV application was rejected because this repair operates directly from validated provider evidence across existing database dates.

### Use an explicitly global fetch contract independent of extraction configuration

The repair will reuse or extract the validator's complete global request, exact-100 validation, and rendered-prefix cross-check. Its chart `country_code` is always empty; storefront context may remain the configured storefront country. Calling the normal extraction client without an override was rejected because `STEAM_CHART_COUNTRY` is configurable and could reproduce the source error.

The normalized repair evidence for each rank will contain only fields available in the Top 100 response: rank, application ID, usable basic name, last-week rank, and consecutive weeks. No ITAD, review histogram, store HTML, tag-list, or category request participates.

### Discover and validate every selected week before mutation

The module will read distinct stored dates (or validate one requested stored date), fetch each global chart, compare identities, and build a complete repair plan before opening a mutation connection. Any provider, completeness, prefix, duplicate, or required-name failure stops application before writes. Per-week commits were rejected because a later failure could leave the historical series partly converted from US to global.

### Reconcile by week/game identity in one transaction

For retained global games, the plan carries existing price, discount, and rating forward by `(week_date, game_id)` while replacing rank and chart-provided weekly stats. For missing global games, those enrichment values are explicitly null. Unexpected weekly rows are removed, but their `games` rows remain.

The transaction first inserts missing catalog games with the validated global name and empty tags. For each selected mismatched week, it frees occupied ranks using the existing temporary-rank-offset pattern, removes identities absent from global, and upserts the complete 100-row global set. Rebuilding only mismatched weeks avoids rewriting already-correct weeks. Row-by-row rank swaps were rejected because they can violate the week/rank constraint mid-transaction.

### Report comparison categories before authorization

Dry-run results will summarize each week as missing, unexpected, moved, and unchanged, with details sufficient to identify the affected application IDs and ranks. Already-correct weeks are skipped rather than proposed. `--apply` may cover all stored dates because the default target is explicitly defined and every chart must validate before the atomic transaction; `--week` narrows operational scope.

### Report bounded progress inside the persistence transaction

Persistence will emit progress while preparing missing catalog identities and after reconciling each mismatched week. Weekly events will identify the week and expose completed/total counts, ensuring a multi-week apply continues to produce visible terminal feedback after the persistence stage begins. These events are observational only: all selected weeks remain inside the same transaction, and no progress boundary commits partial work.

## Risks / Trade-offs

- [A multi-week transaction appears stalled to the operator] → Emit bounded catalog and per-week persistence progress without adding intermediate commits.

- [Historical Steam chart fetches may become unavailable] → Treat fetch or validation failure as non-mutating and report the affected week for retry.
- [One transaction covers several hundred rows] → Finish network work first, update only mismatched weeks, use set-oriented persistence, and retain a single rollback boundary.
- [A new global game lacks a usable basic name] → Reject the plan before mutation rather than insert an invalid catalog row or call another provider.
- [Chart data changes between dry-run and apply] → Apply performs fresh discovery and validation; it does not reuse stale local repair evidence.
- [New rows have incomplete enrichment] → Store null rating/price/discount intentionally and let existing focused repairs fill them later.

## Migration Plan

1. Add provider and comparison characterization tests around explicitly global exact-100 responses.
2. Add module-owned database planning and transactional reconciliation with disposable-schema coverage.
3. Register and document the command, then run a dry-run across all stored dates and review per-week differences.
4. Apply against an isolated Neon branch or disposable clone first, verify every repaired week exactly matches global, then run against the intended branch.
5. Roll back code by removing the command registration and module; roll back repaired data through Neon restore/branch recovery or a pre-repair database backup because the operation intentionally deletes and replaces historical weekly identities.
