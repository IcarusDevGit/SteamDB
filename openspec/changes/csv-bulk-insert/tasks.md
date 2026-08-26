## 1. Candidate Preparation

- [x] 1.1 Add deterministic tag-candidate preparation keyed by tag ID and verify repeated identical mappings produce one candidate without changing per-game tag arrays.
- [x] 1.2 Reject one tag ID mapped to different names before opening a write connection and verify the error identifies the contradictory mapping with zero database mutations.

## 2. Bulk Catalog Persistence

- [x] 2.1 Replace row-wise tag persistence with one parameterized bulk insert using insert-only conflict behavior, and verify statement/helper counts remain constant as repeated tag references increase.
- [x] 2.2 Replace row-wise game persistence with one parameterized bulk insert using insert-only conflict behavior, and verify existing catalog rows remain unchanged while missing games are inserted.

## 3. Bulk Weekly Reconciliation

- [x] 3.1 Replace row-wise weeksheet persistence with one parameterized bulk upsert after rank displacement and verify reviewed weekly facts update while an existing rank swap remains conflict-safe.
- [x] 3.2 Preserve whole-file transaction handling and verify a bulk-stage failure rolls back tag, game, rank-displacement, and weeksheet mutations together.

## 4. Reporting and Regression Verification

- [x] 4.1 Report prepared record and unique-tag counts at the persistence boundary and verify progress tests expose the reduced candidate set and persistence completion or failure.
- [x] 4.2 Run the complete Python unit suite and disposable PostgreSQL integration test, verifying bounded command execution, deduplication, catalog preservation, weekly reconciliation, applied counts, CLI compatibility, and atomic rollback.
