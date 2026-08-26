## Why

Applying an approved weekly CSV currently updates the names and tag associations of every existing game and the names of every existing tag. Weekly ingestion should create missing catalog entities and reconcile weekly facts, while changes to existing catalog entities remain deliberate, separately selected `UpdateDB.py` operations.

## What Changes

- Change `apply csv` so a game already present in `games` retains its stored name and tag identifiers.
- Change `apply csv` so a tag already present in `tags` retains its stored name.
- Continue inserting games and resolved tags that are absent from their destination tables.
- Continue reconciling approved `weeksheet` facts, including updates to an existing game/week record and conflict-safe weekly rank assignment.
- Preserve whole-file transaction and validation behavior.
- Leave tag deduplication, bulk persistence, and new catalog-repair commands outside this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `validated-database-update`: Restrict approved CSV application to insert-only handling for `games` and `tags`, while retaining weeksheet reconciliation and atomicity.

## Impact

- Affects the approved CSV persistence statements in `Python/db.py` and their tests.
- Does not change the `UpdateDB.py apply csv` command syntax, approval gate, validation report contract, CSV format, or transaction boundary.
- Existing game or tag catalog values will no longer be silently refreshed by weekly CSV application; such changes require a separately selected update or repair operation.
