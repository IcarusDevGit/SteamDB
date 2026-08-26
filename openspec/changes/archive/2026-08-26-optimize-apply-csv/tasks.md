## 1. Catalog Insert Semantics

- [x] 1.1 Change approved CSV tag persistence so identifier conflicts leave existing tag rows unchanged, and verify a database-boundary test preserves an existing tag name while inserting a missing tag.
- [x] 1.2 Change approved CSV game persistence so identifier conflicts leave existing game rows unchanged, and verify a database-boundary test preserves an existing game's name and tag identifiers while inserting a missing game.

## 2. Weekly Reconciliation Safety

- [x] 2.1 Verify approved CSV application still updates an existing weeksheet record's reviewed weekly facts while preserving its existing game and tag catalog rows.
- [x] 2.2 Verify games exchanging ranks in one approved week remain conflict-safe and that a persistence failure rolls back missing catalog inserts and weeksheet mutations together.

## 3. Regression Verification

- [x] 3.1 Run the CSV update unit tests and disposable PostgreSQL integration tests, verifying approval, validation evidence, applied counts, transaction behavior, and CLI compatibility remain unchanged.
