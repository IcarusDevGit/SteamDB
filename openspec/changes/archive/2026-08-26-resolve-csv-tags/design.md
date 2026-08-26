## Context

See `proposal.md` for motivation and the delta specs for required behavior. The active pipeline retains unresolved names in each record and writes them to `unresolved_tags`; chart validation intentionally ignores enrichment fields, so a CSV may have a passing chart report while remaining ineligible for `apply csv`. `UpdateDB.py` currently registers only apply and repair groups. Tag resolution reads database and exception snapshots during extraction, while the legacy resolver fetched the full Steam tag list once per unresolved name and directly inserted tags into the database.

The active workflow requires an exact-byte validation digest, insert-only catalog handling during CSV application, explicit authorization for mutation, import isolation from `Python_legacy`, and atomic artifact replacement.

## Goals / Non-Goals

**Goals:**

- Give operators an actionable unresolved summary at the point each artifact finishes.
- Resolve names through deterministic, testable precedence with at most one Steam tag-list request.
- Make dry-run the default and require `--apply` before changing review artifacts.
- Preserve CSV column alignment and all unrelated values.
- Re-establish trustworthy validation evidence after correction.
- Keep resolver execution free of database writes.

**Non-Goals:**

- Updating tag arrays for games already present in the database.
- Applying the corrected CSV or bypassing its separate `--approved` gate.
- Repairing malformed catalog names such as trailing database whitespace.
- Reusing or importing the legacy resolver implementation.
- Supporting arbitrary CSV schemas or multi-week review artifacts.

## Decisions

### Add an explicit resolve command group

Extend the dispatcher with an explicit `resolve` group and a registered `tags` module, yielding `UpdateDB.py resolve tags <csv> [--map NAME=ID] [--apply]`. Keep resolver orchestration in a focused module with the same parser/handler/result conventions as other update operations, while distinguishing artifact correction from database repair.

Adding the command under `repair` was rejected because repair application mutates bounded database records. Hiding resolution inside `apply csv` was rejected because operators must review corrections before database authorization.

### Normalize matching but preserve canonical display names

Compare names using trimmed `casefold()` keys across CSV values, database tags, exceptions, Steam results, and explicit mappings. Prefer canonical display names in this order: existing database name after trimming, exception target's database name, Steam's canonical name, then the explicitly supplied CSV name. Deduplicate row associations by identifier while preserving their original order.

Using raw lowercase comparisons was rejected because existing catalog whitespace caused the motivating failure. Silently matching approximate or fuzzy names was rejected because it can assign the wrong taxonomy identifier.

### Fetch the Steam tag list once and only when needed

Add a client operation for Steam's tag-list endpoint and construct one normalized in-memory lookup per resolver invocation. Invoke it only when database, exception, and explicit sources leave candidates unresolved. Route retryable HTTP responses through the existing provider scheduling conventions.

Calling the endpoint once per name was rejected as unnecessary latency and rate-limit exposure. Scraping individual game pages was rejected because the unresolved name is already known and the authoritative tag list is the direct lookup source.

### Keep mapping discovery separate from artifact application

Discovery returns immutable proposed mappings and per-name outcomes. Dry-run renders them and stops. Authorized application first verifies the existing sidecar against the original bytes, stages corrected rows and any explicit exception additions, then atomically replaces individual files. Cross-file replacement cannot be one filesystem transaction, so writes are idempotent and ordered: stage all outputs, replace the CSV and exception file, then synchronously regenerate/classify validation evidence. A retry recomputes from current artifacts safely.

Direct database insertion, as performed by the legacy resolver, was rejected because it bypasses reviewed CSV application. Editing before verifying the original sidecar was rejected because it would accept an untrusted starting artifact.

### Permit partial correction while retaining the gate

An authorized run applies every unambiguous mapping and leaves names without mappings in `unresolved_tags`. It returns an unsuccessful result until the artifact is fully resolved. This supports iterative operator work while the unchanged `apply csv` validator continues to block incomplete artifacts.

All-or-nothing resolution was considered but rejected because one unknown name should not discard trustworthy automatic corrections. Silently dropping failures was rejected because it would make the artifact appear eligible.

### Reuse chart validation after every applied rewrite

Call the existing validation workflow after atomically replacing the CSV. This creates a new digest and confirms that chart identities remain intact, then reports the final classified paths. Do not merely patch the old digest: independent revalidation retains the current evidence contract.

Reusing the prior chart result with a new digest was considered but rejected because it would create a second, less trustworthy evidence path.

### Print per-week summaries from completed records

After validation returns the final classified path, aggregate unresolved names from the in-memory records using normalized keys, sort by display name, and print affected game name, appid, and rank followed by the artifact-specific resolve command. Print a zero count explicitly. Do not emit a summary when no CSV exists.

Scanning the CSV again was considered but rejected because the completed records already contain the same information and avoid another parsing path.

## Risks / Trade-offs

- [Steam tag-list availability can block automatic resolution] → Preserve dry-run outcomes, accept explicit mappings, and leave unresolved values intact.
- [Partial multi-file replacement can occur after a process crash] → Stage every file first, use atomic replacement per file, keep operations idempotent, and require sidecar verification on each retry.
- [Explicit mappings can pollute future exception behavior] → Validate catalog consistency, show them in dry-run, and persist only explicitly authorized mappings.
- [Revalidation adds two Steam requests] → Preserve evidence integrity and expose progress; resolver use is exceptional rather than per-record.
- [Resolved tags for existing games are not propagated to catalog arrays] → State this in output and reserve catalog updates for a separately proposed bounded repair.
- [Human-readable summaries add stdout lines] → Keep the existing first summary line stable and cover the additional deterministic lines in CLI tests.

## Migration Plan

1. Add normalized tag lookup and Steam tag-list client support with pure resolution tests.
2. Add database read and atomic exception/CSV artifact helpers without database mutation methods.
3. Register `resolve tags`, implement dry-run and authorized partial correction, then integrate revalidation and result paths.
4. Add per-week unresolved summaries to extraction output using the final classified CSV path.
5. Update active workflow documentation and replace the legacy migration entry with the supported resolver command.
6. Run unit tests covering precedence, conflicts, stale evidence, partial resolution, atomic writes, summaries, and zero database writes; run an end-to-end temporary-artifact test with injected providers.
7. Roll back by removing the resolve registry/module and summary output; corrected CSVs and exception mappings remain valid data and require no migration.
