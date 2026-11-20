## 1. Characterize Name Lookup and Persistence

- [x] 1.1 Add focused Steam client tests for a successful English application-details name, unavailable applications, missing/blank names, malformed payloads, and provider failures; verify the new tests define normalized optional-name behavior without live network access.
- [x] 1.2 Add focused repair persistence tests for default empty/whitespace discovery, exclusion of populated and null names, `--appid` and `--limit` filtering, guarded application-ID updates, affected-row counts, commit, rollback, and connection closure; verify SQL tests enforce module-owned persistence and concurrent-name protection.

## 2. Implement Missing-Name Repair

- [x] 2.1 Add the narrow asynchronous Steam game-name lookup to the existing client boundary and implementation; verify client tests pass and existing category/details behavior remains unchanged.
- [x] 2.2 Add `database_updates/repairs/game_names.py` with catalog-appropriate argument registration, local candidate and mutation functions using an injectable connection factory, whitespace-only default discovery, provider lookup, name validation, progress events, dry-run behavior, and standard result counts; verify focused repair and progress tests cover successful, skipped, failed, default, narrowed, and concurrently changed outcomes.
- [x] 2.3 Register `repair game-names` in the repair command inventory without adding a compatibility alias; verify parser and dispatch tests accept `--appid`, `--limit`, and `--apply`, reject unsupported bounds, and allow explicitly authorized application without a bound.

## 3. Integration and Operator Documentation

- [x] 3.1 Extend the disposable PostgreSQL scenario with null, empty, whitespace, and populated game names; verify default discovery includes only empty/whitespace names, optional bounds narrow correctly, authorized guarded updates repair valid candidates, and failures roll back atomically.
- [x] 3.2 Update database-repair guidance and command metadata for the new operation, regenerate the committed command catalog, and verify freshness/completeness tests include `repair game-names`, its external read, whitespace-only default, optional bounds, explicit apply safeguard, and representative examples.

## 4. Final Verification

- [x] 4.1 Run focused client, repair, progress, parser, command-catalog, and disposable-database tests; verify the default run covers only whitespace-name games, provider calls finish before the mutation transaction, and output counts match proposed, applied, skipped, and failed records.
- [x] 4.2 Run the complete active Python test suite and verify all tests pass without changes to `Python_legacy/` or repair-specific additions to `Python/db.py`.
- [x] 4.3 Run strict OpenSpec validation for `repair-missing-game-names` and verify every planning artifact and both delta specifications are valid.
