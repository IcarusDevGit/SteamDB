## Why

Some rows in the PostgreSQL `games` catalog have an empty or whitespace-only name even though each game's Steam application ID is known. Operators need a safe way to repair those blank names from Steam without replacing populated names or treating `NULL` as a default candidate.

## What Changes

- Add a public `repair game-names` operation that selects catalog games whose names are empty or whitespace-only by default.
- Resolve each candidate's English display name from Steam using its application ID, validating and normalizing the provider result before proposing an update.
- Keep the operation non-mutating unless `--apply` is supplied, allow optional application-ID and record-limit bounds, and report proposed, applied, skipped, and failed outcomes consistently with existing repairs.
- Guard authorized updates with the same whitespace-only predicate so populated and `NULL` names are not overwritten.
- Let the repair module own its candidate SQL, guarded mutation SQL, and transaction lifecycle while reusing the shared PostgreSQL connection facility.
- Register and document the command through the existing command-catalog workflow.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `modular-database-repair`: Define whitespace-name discovery, provider lookup by game ID, validation, optional targeting, and guarded transactional persistence behavior for game-name repairs.
- `python-command-catalog`: Include the new supported repair command in the authoritative generated operator inventory.

## Impact

- Adds a focused repair module and command registration under `Python/database_updates/repairs/`.
- Extends the existing Steam client boundary with name lookup by application ID.
- Adds repair SQL against `games.id` and `games.name` within the repair module; `Python/db.py` remains responsible for shared connection setup and main-workflow persistence.
- Updates unit, progress, command-catalog, disposable PostgreSQL integration, and operator documentation coverage.
- Introduces no schema migration and no new third-party service.
