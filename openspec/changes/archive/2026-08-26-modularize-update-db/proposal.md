## Why

`UpdateDB.py` is the operator-facing entry point for database mutations, but adding each new repair directly to that script would recreate the existing monolith and mix CLI parsing, remote-data coordination, validation, and persistence. The update workflow needs a stable modular boundary now so future repairs can be added without making the command surface or transaction behavior confusing.

## What Changes

- Keep `UpdateDB.py` as a thin, stable CLI entry point that dispatches explicit apply and repair commands.
- Introduce a `database_updates` package under the isolated Python workflow, with one function-based module per update or repair operation.
- Separate reviewed CSV application from repairs that discover replacement data through external providers.
- Establish a common function contract for command registration and execution without requiring one class per repair or automatic module discovery.
- Keep SQL, connections, and transaction ownership in `db.py`; update modules coordinate validation, provider clients, and database operations without embedding SQL.
- Make repairs dry-run by default, require explicit authorization to mutate data, support bounded targeting, and return consistent structured outcomes.
- Preserve the current approved-CSV safety gate while strengthening validation and defining deliberate transaction and weekly rank-reconciliation behavior.
- Move still-needed legacy repair commands into focused modules and retire commands that are superseded by the extraction workflow rather than silently carrying them forward.

## Capabilities

### New Capabilities

- `modular-database-repair`: Defines the extensible function-based repair command structure, dry-run/apply safety behavior, targeting, reporting, and module boundaries.

### Modified Capabilities

- `validated-database-update`: Strengthens approved CSV validation, transaction semantics, and conflict-safe reconciliation while routing application through the modular update package.

## Impact

- Promotes the isolated workflow from `Python_temp/` to `Python/`, moves the former implementation to `Python_legacy/`, and updates repository references while keeping both trees import-isolated.
- Affects `Python/UpdateDB.py`, `Python/db.py`, tests, documentation, and a new `Python/database_updates/` package.
- Changes the internal organization and may intentionally remove or rename legacy repair commands after their operational need is assessed; the stable entry point remains `UpdateDB.py`.
- Requires tests for command dispatch, dry-run safety, explicit mutation, malformed or incomplete CSVs, multi-week rollback, and multi-row weekly rank changes.
- Does not change extraction into an implicit database-writing workflow and does not introduce automatic repair-module discovery.
