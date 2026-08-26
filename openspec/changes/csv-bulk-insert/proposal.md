## Why

Applying a 100-row approved CSV currently sends thousands of sequential SQL statements to remote PostgreSQL; one observed file issued 3,030 statements and spent approximately eight minutes in persistence. The same atomic, insert-only catalog behavior can be retained while deduplicating tag candidates and persisting each entity set in bulk.

## What Changes

- Deduplicate CSV tag candidates by tag identifier before database persistence and reject contradictory names for the same identifier rather than choosing one silently.
- Persist missing tag candidates in a bounded bulk operation while preserving existing tag rows.
- Persist missing game candidates in a bounded bulk operation while preserving existing game rows.
- Preserve conflict-safe rank displacement and bulk-upsert the approved weeksheet records.
- Keep validation outside the transaction and keep all catalog and weeksheet mutations for one approved CSV atomic.
- Add progress/timing evidence and tests that prevent a return to statement counts proportional to tag references or game rows.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `validated-database-update`: Add bounded bulk persistence and deterministic tag-candidate deduplication requirements to approved CSV application.

## Impact

- Affects `Python/db.py`, the approved CSV preparation/persistence boundary, progress reporting, and related unit and disposable PostgreSQL integration tests.
- Does not change `UpdateDB.py apply csv` syntax, CSV structure, validation evidence, approval requirements, catalog insert-only semantics, weeksheet reconciliation results, or transaction atomicity.
- Introduces no new database schema or external service dependency.
