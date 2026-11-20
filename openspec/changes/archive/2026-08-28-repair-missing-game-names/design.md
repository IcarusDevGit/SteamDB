## Context

The repair framework already provides named commands, explicit dry-run/apply behavior, targeting, outcome reporting, injectable dependencies, and module-owned persistence. The `games` table is keyed by Steam application ID, while `games.name` may contain an empty or whitespace-only string. Existing Steam client code already calls the application-details endpoint for category metadata, but does not expose a focused game-name lookup. See `proposal.md` for motivation and the delta specs for behavioral requirements.

## Goals / Non-Goals

**Goals:**

- Fit game-name repair into the established registry, result, progress, and safety conventions.
- Keep candidate SQL, guarded mutation SQL, and transaction handling in the game-name repair module.
- Reuse the shared connection factory and Steam HTTP client infrastructure through narrow injectable interfaces.
- Repair empty and whitespace-only names without changing populated or null names.

**Non-Goals:**

- Refreshing populated names or treating `NULL` names as default candidates.
- Repairing weekly-sheet values, tags, prices, ratings, or other catalog metadata.
- Adding repair-specific persistence methods to `db.py`, changing the database schema, or changing `Python_legacy/`.
- Falling back to third-party naming providers when Steam cannot resolve an ID.

## Decisions

### Add a focused `game_names` repair module

The module will register `repair game-names`, select candidates from `games`, orchestrate provider lookup, validate results, own guarded updates, and render standard repair outcomes. This follows the operation-owned persistence boundary and keeps command registration consistent with the existing repair tuple. Adding name logic to `db.py` or a generic repair service was rejected because it would reverse the recently established module ownership boundary.

### Select whitespace-only names by default and allow optional bounds

The command will select rows satisfying `BTRIM(name) = ''` when no target option is supplied and will accept a positive Steam application ID or positive maximum candidate count to narrow that candidate set. PostgreSQL's null semantics naturally exclude `NULL`; populated names also fail the predicate. `--apply` remains the sole mutation authorization and may be used for the complete whitespace-name set without an additional bound. A week bound was rejected because names live in the catalog rather than a weekly record.

### Resolve names through a narrow Steam client method

Expose an asynchronous client operation that requests English Steam application details for one application ID and returns a normalized optional name. The repair will receive the existing client dependency and call only that narrow method. Reusing store-page price parsing was rejected because its return model contains no name and HTML is less structured than the application-details response.

### Guard updates by application ID and whitespace predicate

Candidate selection will read IDs and current names only for rows satisfying the whitespace predicate unless narrowed further. Mutation will use the application ID plus `BTRIM(name) = ''`, count only rows actually updated, and therefore avoid overwriting a value populated or changed to `NULL` after discovery. All authorized updates will run in one transaction with rollback on failure and guaranteed connection closure. An unguarded application-ID update was rejected because the repair is intentionally limited to whitespace names.

### Validate provider output before building updates

Provider names will be converted to text, trimmed, and rejected when absent or blank. Unavailable apps and invalid payloads will become skipped/failed outcomes according to existing result conventions without entering the mutation batch. Persisting raw provider values was rejected because it could replace one missing representation with another.

## Risks / Trade-offs

- [Steam application details may rate-limit or report an app unavailable] → Reuse the existing HTTP error handling and progress reporting, keep dry-run as the default, and preserve each unresolved row.
- [A database can contain many whitespace-name rows] → Keep dry-run non-mutating, support `--limit` and `--appid` for smaller runs, and report the whitespace-only target before lookup.
- [A candidate can change between discovery and persistence] → Repeat the whitespace predicate in the update and count only affected rows.
- [A large repair transaction may hold locks] → Complete all provider calls before opening the transaction and retain optional bounds for operational batching.

## Migration Plan

1. Add characterization and provider parsing tests before command registration.
2. Add the client lookup and focused repair module with unit and disposable-database coverage.
3. Register the command and regenerate the committed command catalog.
4. Deploy without a schema migration; operators first run a dry-run, optionally bounded, then repeat with `--apply` after reviewing outcomes.
5. Roll back by removing command registration and the repair/client additions; the operation does not replace populated or null names.
