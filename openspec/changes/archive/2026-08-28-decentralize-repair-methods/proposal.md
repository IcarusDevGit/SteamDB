## Why

Repair-specific database queries currently accumulate in `db.py`, coupling the main extraction/application boundary to every maintenance operation. Moving those queries into their owning repair modules makes the existing repair framework independently maintainable and prevents future repairs from expanding the main workflow database module.

## What Changes

- Keep PostgreSQL connection configuration and `get_connection()` in `db.py`, together with database behavior used by the main extraction and validated weekly-application workflows.
- Move candidate-selection and persistence methods for ratings, prices, and weekly statistics from `db.py` into their respective repair modules.
- Make every repair module own its operation-specific SQL, transaction handling, discovery orchestration, and outcome reporting while obtaining connections through `db.get_connection()`.
- Preserve the existing repair command surface, dry-run safeguards, targeting behavior, outcome reporting, and external-discovery separation throughout the migration.
- Update contributor documentation and automated tests for the revised ownership model.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `modular-database-repair`: Define repair-module ownership of operation-specific reads and writes while preserving the existing repair behavior.

## Impact

The change affects `Python/db.py`, the existing modules under `Python/database_updates/repairs/`, repair and integration tests, and database repair contributor documentation. It does not move connection configuration out of `db.py`, add or remove public commands, change the validated CSV application contract, or alter the database schema.
