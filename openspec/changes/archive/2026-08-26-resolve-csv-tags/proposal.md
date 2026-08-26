## Why

Completed extraction CSVs can contain unresolved tag names, but the active workflow only exposes per-record counts and then rejects application without providing a supported correction command. Operators need a consolidated final list and a guarded way to resolve the reviewed artifact without reviving the legacy routine's implicit database mutations.

## What Changes

- List unique unresolved tags and their affected games after each weekly CSV and validation report are completed, including the artifact-specific resolver command.
- Add `UpdateDB.py resolve tags <csv>` as a dry-run-by-default operation that resolves unresolved names from normalized database tags, `helpers/Exceptions.json`, one Steam tag-list lookup, and repeatable explicit `--map NAME=ID` inputs.
- Add explicit `--apply` authorization to atomically update aligned `tags`, `tag_ids`, and `unresolved_tags` CSV fields and, when applicable, persist operator mappings to the exception file.
- Reject ambiguous or contradictory mappings and leave unresolvable names in place with an unsuccessful outcome.
- Verify the original passing sidecar before editing and automatically revalidate the changed CSV so its validation report is bound to the new bytes.
- Keep tag resolution free of database mutations; applying the corrected CSV remains a separate approved operation, and updating tags of existing games remains outside this change.

## Capabilities

### New Capabilities

- `csv-tag-resolution`: Resolve and safely apply tag mappings to a reviewed CSV artifact without mutating the database.

### Modified Capabilities

- `data-extraction-workflow`: Report a consolidated unresolved-tag summary and resolver command after each completed weekly CSV.

## Impact

- Affects `Python/UpdateDB.py`, the explicit operation registry, tag resolution/client helpers, database read APIs, atomic JSON/CSV writing, validation integration, progress/result reporting, documentation, and tests.
- Does not change the CSV schema, chart identity rules, approval gate, database transaction semantics, or insert-only behavior for existing games and tags.
- Uses the existing Steam API key, HTTP client dependency, exception file, and validator; no new external dependency or schema migration is required.
