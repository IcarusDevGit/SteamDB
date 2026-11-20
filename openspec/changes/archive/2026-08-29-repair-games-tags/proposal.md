## Why

Some catalog games have an empty tag array, leaving downstream analysis without genre and feature classifications. Operators need a safe repair command that can rebuild those tags from each game's Steam store HTML without disturbing games whose tags are already populated.

## What Changes

- Add a `repair game-tags` operator command that discovers every game with empty tags by default.
- Fetch each candidate's Steam store HTML by app ID and reuse the existing store-page parser and catalog tag-resolution rules.
- Keep the operation dry-run by default, with explicit `--apply` authorization for database writes.
- Allow optional `--appid` and `--limit` narrowing while permitting an unbounded apply across all empty-tag games.
- Preserve concurrently or previously populated rows through a conditional update and report unavailable, unresolved, failed, proposed, and applied outcomes.
- Register and document the new supported command in the generated Python command catalog.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `modular-database-repair`: Add discovery and repair behavior for catalog games whose tag arrays are empty.
- `python-command-catalog`: Expose the game-tag repair as a supported, documented operator command.

## Impact

- Adds a repair module under `Python/database_updates/repairs/` and registers it with the existing update-command dispatcher.
- Reuses `RealExtractionClients.steam_html`, `parse_store_html`, catalog snapshots, exception aliases, and tag resolution; no new external provider or dependency is introduced.
- Adds focused repair, CLI, command-catalog, and disposable-database test coverage.
- Reads Steam store pages and conditionally updates `games.tags`; it does not modify populated tag arrays or create tag identities for unresolved names.
