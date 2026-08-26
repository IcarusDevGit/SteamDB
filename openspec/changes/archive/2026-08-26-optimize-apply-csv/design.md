## Context

See `proposal.md` for motivation and `specs/validated-database-update/spec.md` for required behavior. The approved CSV database boundary currently loops over every record, upserts every referenced tag with `ON CONFLICT ... DO UPDATE`, and upserts every game with the same conflict behavior before reconciling weeksheet rows. Consequently, weekly application can overwrite existing catalog names and game tag arrays even though extraction deliberately avoids recollecting tags for existing games.

The CSV is validated before persistence, and all catalog and weeksheet statements run in one transaction. Rank displacement for incoming games prevents transient weekly rank conflicts. Those safety properties must remain intact.

## Goals / Non-Goals

**Goals:**

- Make catalog persistence insert-only for existing game and tag identifiers during approved CSV application.
- Preserve current missing-entity insertion, weeksheet reconciliation, rank-conflict handling, rollback, and result-count behavior.
- Verify the database boundary, rather than relying on a potentially stale extraction snapshot, enforces the insert-only rule atomically.

**Non-Goals:**

- Deduplicating repeated tag references before issuing persistence statements.
- Converting row-wise persistence to bulk or set-based SQL.
- Adding or changing explicit game or tag repair commands.
- Changing CSV validation, approval evidence, CLI syntax, or schema.

## Decisions

### Ignore catalog conflicts inside the existing transaction

Use insert statements whose conflict action leaves an existing `tags` or `games` row unchanged. PostgreSQL remains the authority for deciding whether an identifier is missing at statement execution time, so the behavior is safe if database state changes after extraction.

Pre-querying all existing identifiers and conditionally inserting in Python was considered but rejected because it adds reads and creates a race between the check and insertion. Updating only when values appear different was rejected because weekly application must not own catalog repairs.

### Keep weeksheet reconciliation unchanged

Continue displacing ranks for the authorized incoming game set and upserting each validated game/week fact. The insert-only policy applies only to catalog tables; an approved weekly CSV must still be able to update the reviewed price, discount, rating, rank, last-week rank, and consecutive-week values.

Treating weeksheet conflicts as insert-only was rejected because it would prevent corrected or rerun weekly facts from being reconciled and would contradict the purpose of approved CSV application.

### Preserve existing statement shape for this change

Keep the current row-wise loop and repeated tag statements, changing only catalog conflict semantics. This isolates authorization behavior from later performance work and directly honors the decision not to introduce deduplication now.

Combining this change with tag deduplication or bulk upserts was considered but rejected because it would broaden testing and make behavioral regressions harder to attribute.

## Risks / Trade-offs

- [A CSV may contain more current catalog metadata than the database] → Preserve it in the reviewed artifact but require an explicit catalog update operation to mutate existing rows.
- [Repeated tag references still generate redundant conflict checks] → Accept the current cost; address deduplication or bulk persistence in a separate performance change.
- [Changing conflict actions could accidentally affect weeksheet behavior] → Add focused database tests that distinguish catalog preservation from weekly fact reconciliation and rank exchange.
- [Concurrent insertion of the same missing identifier may occur] → Let the database uniqueness constraint and conflict handling select one committed insert without overwriting an existing row.

## Migration Plan

1. Change catalog conflict handling in the approved CSV database boundary while retaining the transaction and weeksheet statements.
2. Extend unit or disposable-database integration coverage for missing catalog inserts, existing catalog preservation, weeksheet updates, rank exchange, and rollback.
3. Run the CSV update and database integration suites. No data migration is required because the change only prevents future implicit catalog updates.
4. Roll back by restoring the former catalog conflict actions; no schema rollback is needed.
