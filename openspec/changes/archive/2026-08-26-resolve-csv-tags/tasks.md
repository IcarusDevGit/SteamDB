## 1. Resolution Sources

- [x] 1.1 Add trimmed case-insensitive catalog and exception lookup helpers, and verify database names with surrounding whitespace resolve to the existing ID and trimmed canonical name.
- [x] 1.2 Add one-call Steam tag-list client support with existing retry conventions, and verify multiple unresolved names use at most one provider request and exact normalized matches only.
- [x] 1.3 Parse repeatable `NAME=ID` mappings and verify malformed, non-positive, duplicate, ambiguous, and catalog-conflicting mappings fail before artifact writes.
- [x] 1.4 Implement deterministic source precedence and per-name resolution outcomes, and verify database, exception, Steam, explicit, and unresolved cases without database mutation.

## 2. Resolver Command and Artifact Safety

- [x] 2.1 Register `UpdateDB.py resolve tags <csv> [--map NAME=ID] [--apply]` through an explicit resolve command registry and verify help, dispatch, unknown-command rejection, and dry-run behavior.
- [x] 2.2 Verify the original CSV's passing matching sidecar before authorized edits, and verify missing, failed, stale-digest, wrong-week, and multi-week evidence causes zero CSV or exception changes.
- [x] 2.3 Rewrite affected rows with aligned, order-preserving, ID-deduplicated `tags` and `tag_ids` plus remaining `unresolved_tags`, and verify unrelated fields and unresolved failures are preserved.
- [x] 2.4 Stage and atomically replace authorized CSV and explicit exception-file changes, and verify dry-run changes nothing while repeated authorized execution is idempotent.
- [x] 2.5 Revalidate every changed CSV and report its final classified CSV/sidecar paths, and verify passing, failed, and error validation outcomes remain bound to the corrected bytes.
- [x] 2.6 Return consistent proposed, applied, unresolved, and failed outcomes with progress events, and verify partial resolution exits unsuccessfully and still blocks `apply csv`.

## 3. Extraction Summary

- [x] 3.1 Aggregate unresolved names case-insensitively from completed records and verify deterministic alphabetical output with affected game name, appid, and rank.
- [x] 3.2 Print each completed week's unresolved count and artifact-specific resolver command after its final CSV path, and verify zero-count, multi-week, and pre-CSV failure behavior.

## 4. Documentation and Regression Verification

- [x] 4.1 Document the active resolve command, dry-run/apply sequence, explicit mappings, partial outcomes, revalidation, and zero-database-write boundary, and update the legacy migration table to name the replacement.
- [x] 4.2 Run the complete Python unit suite and an injected end-to-end temporary-artifact test, verifying source precedence, one Steam request, atomic correction, fresh evidence, summaries, CLI compatibility, and zero database writes.
