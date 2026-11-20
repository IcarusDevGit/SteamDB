## Context

The repair framework already separates candidate selection, asynchronous provider discovery, and transaction-owned persistence. Steam store HTML parsing and catalog tag resolution are also existing production paths, while `games.tags` is represented as a PostgreSQL integer array and existing snapshots normalize null values to empty lists.

This change crosses the repair registry, HTTP/tag-resolution services, database persistence, progress reporting, tests, and generated command documentation. See the proposal and capability deltas for the behavioral contract.

## Goals / Non-Goals

**Goals:**

- Reuse the same Steam HTML interpretation and tag aliases used by weekly extraction.
- Make a full empty-tag catalog scan the explicit, reported default for both dry-run and authorized apply.
- Isolate provider failures per game and preserve the repair framework's final outcome and live-progress conventions.
- Prevent stale discovery results from overwriting tags populated by another operation.

**Non-Goals:**

- Refreshing or merging tags for games that already have at least one stored tag.
- Creating catalog tag records or exception aliases from previously unknown HTML names.
- Persisting prices, discounts, or other data returned by the shared store-page parser.
- Adding a separate scraper, HTTP dependency, or provider-specific retry system.

## Decisions

### Treat null and zero-cardinality arrays as candidates

Candidate SQL will use the semantic equivalent of `COALESCE(cardinality(tags), 0) = 0`, ordered by app ID before applying an optional limit. This covers the current empty-array representation and remains robust to nullable legacy rows. Checking only `tags = '{}'` is narrower and checking a loaded Python snapshot would lose database-side targeting and ordering.

### Follow the game-name repair's default targeting model

`repair game-tags` will accept optional `--appid`, `--limit`, and `--apply`. Unlike repairs where an unbounded mutation is unsafe, the operation's safe default is precisely the finite set of catalog rows missing tags, so `--apply` alone is valid. The command will report `empty-tags` when no narrowing option is present.

### Reuse store HTML and tag resolution services

Each candidate will call the existing asynchronous Steam HTML client, which already sets locale, country, mature-content cookies, request headers, timeout handling, and parses unique `a.app_tag` values. The result will be passed to existing case-insensitive catalog/alias resolution using a catalog snapshot loaded once per run. A new parser would risk behavioral drift; invoking the entire weekly pipeline would fetch unrelated weekly, rating, category, and pricing data.

### Apply the resolvable subset without synthesizing IDs

If a page contains both resolved and unresolved names, resolved IDs remain a valid proposal and unresolved names are diagnostic messages. If no IDs resolve, no update is proposed. This salvages known catalog data while preserving the existing reviewed process for unknown tags; making one unknown name invalidate all known names would unnecessarily retain an empty row.

### Persist with a guarded, atomic update phase

Discovery completes before opening the mutation transaction. Each statement updates by app ID only while the tag collection remains null or empty, and applied counts come from affected row counts. All proposed updates commit together or roll back together. This matches repair transaction ownership and prevents concurrent enrichment from being overwritten.

### Preserve candidate-level observability

Discovery emits bounded Steam lookup progress and isolates request/parsing errors per candidate. Persistence emits monotonic progress for proposed rows. Final results use existing proposed, applied, skipped, and failed fields, with messages identifying unresolved names and provider failures. Unresolved names alone do not make an otherwise applicable candidate fail.

## Risks / Trade-offs

- [Steam HTML markup changes or bot defenses can produce no tags] → Reuse the tested parser and request profile, classify empty results without mutation, and isolate failures per game.
- [A full catalog scan can generate many requests] → Keep `--limit` and `--appid` available, use asynchronous discovery consistent with existing repairs, and expose per-candidate progress.
- [Catalog mappings can change during a long run] → Load one coherent snapshot for deterministic resolution; guarded writes protect game rows, while a later repair can use newer mappings.
- [Partially resolved pages omit unknown classifications] → Report unresolved names explicitly and never synthesize IDs, allowing reviewed catalog/alias maintenance followed by another repair.

## Migration Plan

1. Add and register the repair module, tests, and catalog descriptor.
2. Regenerate the committed command catalog and run focused plus full automated tests.
3. Deploy without a schema migration; the command is opt-in and dry-runs by default.
4. Operators can first review an unbounded dry-run, then invoke `--apply`; rollback of an erroneous applied run requires restoring affected `games.tags` from a database backup because the repair intentionally has no destructive inverse command.
