## Context

See `proposal.md` for motivation and `specs/validated-database-update/spec.md` for the new performance contract. `apply_validated_records` currently performs one tag insert per tag reference, one game insert per record, one rank-displacement update per week, and one weeksheet upsert per record. With a remote database, network round trips dominate execution even when catalog conflicts immediately do nothing.

Approved input contains exactly one week and no duplicate game/week or rank identities. Catalog rows are insert-only, weeksheet facts are reconcilable, and every mutation must remain in one transaction. The existing Python PostgreSQL dependency already provides helpers for composing multi-value statements, so no new dependency is needed.

## Goals / Non-Goals

**Goals:**

- Reduce persistence to one bulk command per non-empty entity set plus bounded rank displacement and commit.
- Deduplicate tags deterministically before opening the write transaction.
- Detect contradictory names for one tag identifier before mutation.
- Preserve catalog insert-only semantics, weekly updates, rank-swap safety, applied counts, and rollback.
- Make statement-count regression testable independently of network timing.

**Non-Goals:**

- Updating existing game names, game tag arrays, or tag names.
- Changing CSV validation evidence, approval, CLI syntax, database schema, or provider workflows.
- Establishing a general bulk-write abstraction for unrelated repair operations.
- Guaranteeing a fixed wall-clock duration across database providers or network conditions.

## Decisions

### Deduplicate tag candidates by identifier before connecting

Build an insertion-ordered mapping from tag ID to canonical name across all validated records. Repeated identical pairs collapse into one candidate. If an ID is paired with a different name, fail before obtaining a write connection. Each game's original validated tag-ID array remains unchanged, so deduplication affects only candidate insertion and not associations.

Silently using the first or last name was rejected because input order should not decide catalog meaning. Relying on `ON CONFLICT DO NOTHING` alone was rejected because it neither detects contradictions within the reviewed artifact nor reduces the transmitted value set.

### Use multi-value PostgreSQL statements with one page per entity set

Use the existing PostgreSQL driver's multi-value execution helper for tags, games, and weeksheet rows. Set the page size to the prepared set size so a normal approved weekly file produces one command for each set rather than hidden fixed-size pages. Empty sets skip their command.

Manual string interpolation was rejected because values must remain driver-parameterized. `executemany` was rejected because it still executes one statement per parameter tuple and retains the network/command overhead being removed.

### Preserve conflict behavior per entity

Bulk tag and game inserts use identifier conflict handling that leaves existing catalog rows unchanged. Bulk weeksheet insertion retains conflict updates for the reviewed weekly fields. Existing result semantics continue to report the number of approved records, not the number of newly inserted catalog entities.

Pre-querying existing catalog IDs was rejected because `ON CONFLICT` is race-safe and a pre-read would add round trips without removing the need for conflict handling.

### Keep rank displacement ahead of the bulk weeksheet upsert

Continue moving ranks held by incoming games out of the constrained range before assigning the reviewed ranks. For the single validated week, this remains one parameterized update followed by one bulk weeksheet upsert. Rows outside the authorized game set remain untouched, so an out-of-scope rank collision still fails and rolls back.

Deleting and replacing the complete week was rejected because approved application must preserve rows outside its authorized identities. Deferring uniqueness constraints was rejected because it would require schema or transaction-constraint changes.

### Verify bounded commands instead of asserting elapsed time

Unit tests will instrument cursor and bulk-helper calls and assert command count remains constant as row and repeated-tag counts grow. The disposable PostgreSQL integration test will verify final state and rollback. Progress will report prepared record and unique-tag counts around persistence; elapsed time may be reported for operator diagnosis but will not be a correctness threshold.

An elapsed-time test was rejected because remote latency, Neon wake-up, and CI load make it nondeterministic.

## Risks / Trade-offs

- [One larger statement uses more client and server memory] → Bound approved input to the existing single 100-record week and test representative tag volume.
- [Driver helpers may split statements by default] → Explicitly configure one page for each prepared entity set and assert helper call/page behavior.
- [Contradictory tag names were previously ignored by catalog conflicts] → Reject them before mutation with an actionable validation error.
- [Bulk weeksheet SQL could regress rank-swap behavior] → Retain displacement ordering and cover swaps plus out-of-scope collisions in disposable PostgreSQL tests.
- [A bulk failure provides less row-level database error locality] → Preserve atomic rollback and include the entity stage in failure reporting; input validation handles record-level errors before persistence.

## Migration Plan

1. Add tag-candidate preparation and contradiction validation before the transaction.
2. Replace tag and game loops with one bulk insert per prepared set while retaining insert-only conflicts.
3. Replace the weeksheet loop with one bulk upsert after the existing rank displacement.
4. Extend progress fields and unit tests for unique-tag counts and bounded command execution.
5. Run the complete unit suite and disposable PostgreSQL integration test with representative duplicates, rank exchange, existing catalog rows, and forced rollback.
6. Roll back by restoring row-wise execution; no schema or data migration is required.
