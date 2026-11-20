## Context

The repair command surface is modular, but its database behavior is not: ratings and prices ask `db.py` to select candidates and persist changes, while weekly statistics also delegate persistence there. This makes the main workflow database module grow whenever a maintenance operation is added. At the same time, `db.py` is the established source of connection configuration and is used by extraction and validated CSV application, so moving connection functionality would create unnecessary churn.

## Goals / Non-Goals

**Goals:**

- Make repair modules cohesive owners of their operation-specific candidate reads, mutations, and transaction behavior.
- Preserve `db.py` as the connection facility and database boundary for the main extraction/application workflow.
- Preserve the observable behavior of rating, price, and weekly-stat repairs while relocating their persistence methods.
- Keep database access replaceable in unit tests without requiring a live PostgreSQL service.

**Non-Goals:**

- Moving `get_connection()`, environment loading, or PostgreSQL driver setup out of `db.py`.
- Creating a generic repository, ORM, or new database abstraction layer.
- Adding, removing, or changing any public repair operation.
- Changing validated CSV application so it overwrites existing game attributes.

## Decisions

### Repair modules own SQL and transaction lifecycle

Each repair module will expose focused candidate-selection and application functions alongside its existing discovery, parser registration, and `run` orchestration. Those functions call `db.get_connection()`, close read connections after candidate selection, and commit or roll back and close mutation connections within the owning module.

Keeping repair SQL in `db.py` was rejected because it recreates the coupling this change addresses. Introducing `postgres.py` or a repository hierarchy was rejected because connection functionality must remain in `db.py` and the project does not need another abstraction layer.

### Inject the connection factory, not a repair-shaped database object

Repair functions will accept an optional connection factory, defaulting to `db.get_connection`. `run` will resolve it from injected dependencies for tests. Unit tests can therefore use fake connections and cursors, while integration tests exercise real transactional statements against the disposable schema.

Continuing to inject a broad mock `database` object was rejected because its required methods grow with every repair and disguise which module owns the SQL. Opening hard-coded global connections without an injectable seam was rejected because it would make repair behavior difficult to test in isolation.

### Migrate all existing repairs as one ownership change

Rating, price, and weekly-stat candidate/application SQL will move with behavior-preservation tests. The repair-specific helpers will then be removed from `db.py` after all callers use their owning modules.

Partial migration was considered but rejected because it would leave two competing repair persistence patterns and ambiguous contributor guidance.

## Risks / Trade-offs

- [Transaction code is repeated across repair modules] → Keep the small commit/rollback/close pattern explicit so ownership remains local; extract only truly operation-neutral helpers if repetition becomes error-prone.
- [Refactoring existing repairs changes behavior accidentally] → Characterize their SQL, bounds, counts, rollback, and progress behavior before removing `db.py` methods, then run focused and disposable-database tests.
- [A future repair copies an older pattern] → Update contributor documentation and enforce ownership with tests or repository searches that reject new repair-specific methods in `db.py`.

## Migration Plan

1. Add characterization tests and relocate existing repair reads/writes one module at a time while keeping public commands stable.
2. Remove repair-specific helpers from `db.py` after all callers have migrated.
3. Update contributor documentation and run the complete unit suite and disposable PostgreSQL integration checks. Rollback restores the former `db.py` repair helpers and module delegation; no data or schema rollback is required.
