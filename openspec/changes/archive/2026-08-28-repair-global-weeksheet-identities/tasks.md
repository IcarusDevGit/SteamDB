## 1. Characterize Global Evidence and Comparison

- [x] 1.1 Add focused provider tests for explicitly global historical Top 100 requests, rendered-prefix agreement, exactly 100 unique ranks/app IDs, normalized name and weekly-stat fields, and malformed/provider failures; verify the request remains global even when `STEAM_CHART_COUNTRY` is nonempty.
- [x] 1.2 Add focused comparison tests for matching weeks, missing/unexpected identities, wrong ranks, unchanged counts, malformed stored sets, all-date discovery, and one-week targeting; verify dry-run evidence is deterministic and no database mutation occurs.

## 2. Implement Weekly Identity Repair

- [x] 2.1 Extract or extend the global chart evidence boundary so validation and repair reuse one exact-100/prefix-checked source with chart-provided names and weekly stats; verify existing standalone validation behavior remains unchanged.
- [x] 2.2 Add `database_updates/repairs/weekly_identities.py` with stored-date and week-row SQL, global discovery, comparison planning, standard progress/result reporting, full stored-date default scope, optional `--week`, and explicit `--apply`; verify focused tests cover correct, mismatched, failed, dry-run, and all-weeks cases.
- [x] 2.3 Implement module-owned atomic reconciliation that inserts missing catalog games with global names and empty tags, preserves retained price/discount/rating by week/game, assigns global ranks and weekly stats, leaves new enrichment null, removes unexpected weekly rows, preserves unrelated catalog rows, and rolls back all selected weeks on failure; verify SQL and transaction tests cover swaps, counts, null defaults, commit, rollback, and connection closure.
- [x] 2.4 Register `repair weekly-identities` without a compatibility alias; verify parser and dispatch tests accept optional `--week` and `--apply`, reject meaningless targeting flags, and allow explicitly authorized all-stored-date repair.

## 3. Integration and Documentation

- [x] 3.1 Extend the disposable PostgreSQL scenario with correct and US-divergent weeks, retained/missing/unexpected games, rank swaps, and a forced later-week failure; verify exact global reconciliation, retained enrichment, null new enrichment, catalog preservation/insertion, idempotency, and cross-week rollback.
- [x] 3.2 Update repair guidance and command metadata, regenerate `docs/commands.md`, and verify catalog freshness/completeness documents the global-only source, all-stored-date default, optional week target, dry-run, explicit apply, destructive weekly-row reconciliation, preserved enrichment, and null defaults.

## 4. Final Verification

- [x] 4.1 Run focused provider, validation, comparison, repair, progress, parser, catalog, and disposable-database tests; verify all external charts validate before the mutation transaction and repaired weeks exactly match their global identities.
- [x] 4.2 Run a read-only dry-run against the configured database and verify its per-week mismatch totals agree with independently validated global comparisons before any apply is attempted.
- [x] 4.3 Run the complete active Python test suite and verify all tests pass without changes to `Python_legacy/` or repair-specific additions to `Python/db.py`.
- [x] 4.4 Run strict OpenSpec validation for `repair-global-weeksheet-identities` and verify every planning artifact and both delta specifications are valid.

## 5. Persistence Progress Follow-up

- [x] 5.1 Add focused progress tests proving an applied repair emits bounded catalog-preparation and per-week reconciliation updates, with current-week identity and completed/total counts, while retaining a single commit boundary.
- [x] 5.2 Instrument weekly-identity persistence with the tested progress events and pass the operation reporter through the mutation boundary without changing dry-run behavior or atomicity.
- [x] 5.3 Run focused and complete active Python tests plus strict OpenSpec validation after the progress change.
