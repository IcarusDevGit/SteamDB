## 1. Historical Rating Domain

- [x] 1.1 Add the shared historical-rating aggregate and centralized label constants/classifier, and verify table-driven unit tests cover every percentage threshold, review-count band, exact boundary, and the fewer-than-10 `no_label` case.
- [x] 1.2 Update Steam histogram parsing and the extraction client contract to return cutoff-consistent counts, ratio, and label from one response, and verify parser tests include reviews before and at the next-Tuesday cutoff.

## 2. Extraction and CSV Flow

- [x] 2.1 Extend extraction records, enrichment assignment, progress-compatible branch behavior, and CSV serialization with nullable `rating_label`, and verify pipeline/model tests distinguish populated labels, `no_label`, and failed/absent collection without changing numeric rating behavior.
- [x] 2.2 Extend the validated CSV contract to require, normalize, and validate `rating_label` against the shared label set including `no_label`, and verify CSV tests accept empty/known values, preserve their distinct meanings, and reject unknown labels before persistence.

## 3. Database Persistence

- [x] 3.1 Add the repository's additive database migration for nullable `weeksheet.rating_label` and update disposable integration schemas, then verify the migration applies without changing existing numeric `rating` values.
- [x] 3.2 Extend validated weekly bulk upserts and weekly-identity reconciliation to insert, update, and preserve `rating_label` by week/game identity, and verify transaction, rank-swap, retained-row, and newly inserted-row integration cases.

## 4. Rating-Label Repair

- [x] 4.1 Add a focused `rating-labels` repair whose single candidate query materializes all selected null-label rows, with optional `--week`, `--appid`, and `--limit` filters and an explicitly reported all-null-rows default apply target; verify one-query discovery, deterministic filtering, connection cleanup, and apply authorization tests.
- [x] 4.2 Group candidates by application ID, request each unique game's complete histogram once, and derive every candidate week's label from the shared rollups; verify recurring games cause one request, distinct week cutoffs produce correct labels, low-volume weeks produce `no_label`, and provider failures leave affected rows out of the update collection.
- [x] 4.3 Accumulate all successful discoveries in a separate update collection and persist it only after discovery completes using one bulk operation and one transaction guarded by `rating_label IS NULL`; verify applied counts, no early writes, numeric-rating preservation, concurrent-change protection, rollback, progress, and idempotency in unit and disposable-database tests.

## 5. Command Surface and Documentation

- [x] 5.1 Register `repair rating-labels` in repair dispatch and authoritative command metadata, regenerate the committed command catalog, and verify parser, registry-completeness, and freshness tests pass.
- [x] 5.2 Document the schema prerequisite, null-versus-`no_label` semantics, unique-game request reuse, dry-run/apply examples, optional filters, full-set default, and backfill procedure in operator documentation, and verify all documented invocations match generated command syntax.

## 6. End-to-End Verification

- [x] 6.1 Run the focused client, pipeline, CSV-update, database-repair, progress, command-catalog, and disposable-database tests and resolve all failures.
- [x] 6.2 Run the full Python test suite and strict OpenSpec validation, and verify extraction remains non-mutating while approved CSV application and bounded repair persist labels independently of numeric ratings.
