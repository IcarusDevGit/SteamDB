## Context

See `proposal.md` for motivation. `Python/main.py` currently collects all requested weeks through one pipeline run, writes one combined reviewable CSV, and returns its path without checking the chart. A failure while fetching a later extraction week can therefore prevent any earlier week from being written. `Python/UpdateDB.py` requires explicit approval and performs structural/semantic CSV validation, but it has no evidence that weekly membership and ordering match Steam's global chart. `comparison/compare_weekly_chart.py` demonstrates HTML bootstrap parsing and complete-chart comparison for one hard-coded week, but it is coupled to legacy comparison, hard-coded dates and timestamps, and does not gate persistence.

Steam's chart page initially embeds a visible chart subset and loads the complete Top 100 through official chart data. Validation must use the requested global chart URL as its anchor, derive all dates dynamically, and avoid treating names or localized price presentation as identity.

## Goals / Non-Goals

**Goals:**

- Make one requested week the unit of extraction, CSV output, validation, and database application.
- Validate exact `(rank, appid)` membership for the one week in each CSV.
- Produce deterministic, actionable differences and a digest-bound sidecar report.
- Preserve failed CSVs for manual diagnosis and correction.
- Make both automatic extraction and standalone validation observable through process status.
- Prevent every database mutation path for a CSV without current passing chart evidence.

**Non-Goals:**

- Validating names, ratings, tags, prices, discounts, or other enrichment fields.
- Correcting, deleting, or silently rewriting CSV entries.
- Using the legacy Python tree at runtime.
- Treating a network or parser failure as a chart mismatch or as a successful validation.
- Updating PostgreSQL from the validator.

## Decisions

### Add one standalone active-tree validator

Add `Python/ValidateEntries.py` with a callable validation function and a CLI accepting a single-week CSV path. `main.py` invokes the same function after each weekly `WriteCSV.write_csv`; tests inject the chart fetcher instead of requiring live Steam access. Reusing one implementation avoids drift between automatic and manual validation.

Extending the legacy comparison script was rejected because it loads both Python trees and contains hard-coded comparison behavior unrelated to the production gate. Embedding all validation in `main.py` was rejected because operators must be able to revalidate a corrected CSV without rerunning extraction.

### Model chart identity only as rank and app id

The validator requires one distinct CSV week, parses its ordered identities, and compares them with the corresponding global chart identities. It first detects malformed, missing, and duplicate identities, then compares by rank and by application id so the report can distinguish wrong rank from missing/unexpected membership. More than one distinct week is an input error. Other columns are read only as necessary to locate the identity fields.

Comparing names was rejected because localization and renaming make them weaker identifiers. Comparing price and other enrichment was rejected because those values come from different historical sources and are not part of the user's validation objective.

### Isolate extraction and validation by requested week

`main.py` iterates requested dates as independent end-to-end units. For each date it runs extraction for that date, writes that date's CSV, validates it, records the outcome, and only then advances to the next date. A later extraction or validation exception contributes an unsuccessful command result but does not revoke, combine with, or remove artifacts already produced for earlier dates.

Keeping one pipeline run and splitting its returned records was rejected because a later weekly fetch can fail before the pipeline returns anything. Writing one combined CSV was rejected because its digest and passing status couple otherwise independent weeks and make one unavailable chart block all database application.

### Anchor complete-chart loading to the public chart page

For each Tuesday, the validator requests `https://store.steampowered.com/charts/topsellers/global/{date}`. It parses the embedded chart bootstrap, derives the complete-chart request dynamically from the target date, and verifies that the rendered bootstrap identities are a prefix of the complete result before trusting all 100 entries. No date, timestamp, or count from the existing comparison fixture is hard-coded in production.

Using only the first rendered entries was rejected because it cannot prove all entries are present. Calling only the same weekly API as extraction was rejected because it would not independently confirm that request parameters represent the public global chart.

### Use a deterministic sidecar bound to exact CSV bytes

The report path defaults to `<csv-stem>.validation.json` beside the CSV. It contains a schema version, the CSV week and source URL, CSV SHA-256, `passed`/`failed`/`error` status, expected and actual counts, duplicate ranks/app ids, missing/unexpected identities, and wrong-rank records. Report writing uses a temporary sibling followed by replacement so a crash does not leave a partially valid JSON file.

The digest is computed from raw bytes, not parsed rows, so any edit invalidates the prior evidence. Embedding status in the CSV was rejected because it would alter the artifact being hashed and complicate manual corrections. A report without a digest was rejected because it could be accidentally reused for a changed file.

### Preserve artifacts and fail closed

Extraction writes each weekly CSV before its validation begins. Validation retains the weekly pair together and classifies it under `helpers/CSV` only for `passed`; `failed` and `error` pairs are retained under `helpers/CSV_error`. The report remains adjacent to the CSV after classification. A mismatch returns a distinct nonzero result and a fetch or parse failure returns another nonzero result. `main.py` prints every produced pair and weekly summary, then returns success only if every requested week completed and passed.

Deleting a failed CSV was rejected because it is needed for diagnosis. Allowing extraction to exit successfully on mismatch was rejected because automation would miss the failure.

### Enforce the gate in approved CSV application

The approved-CSV operation requires exactly one distinct CSV week, resolves the default adjacent report or an explicitly supplied report path, parses it, requires `status == "passed"`, recomputes the CSV digest, and confirms that the report covers exactly that week before opening a database connection. The existing `--approved` flag remains necessary but is no longer sufficient.

Trusting only the report filename was rejected because reports can become stale. Offering a bypass flag was rejected because it would undermine the required gate; recovery consists of fixing and revalidating the CSV.

### Keep parsing and comparison independently testable

HTML/bootstrap parsing, complete-chart response parsing, CSV identity parsing, difference calculation, digest calculation, and report-gate verification are pure or dependency-injected boundaries. Stored fixtures cover page-format parsing without making unit tests depend on Steam availability. A separately authorized live smoke check may detect page drift but is not the deterministic acceptance test.

## Risks / Trade-offs

- [Steam changes its page bootstrap or complete-chart request] -> Treat parsing as an `error`, preserve artifacts, use representative fixtures, and keep parsing isolated for focused updates.
- [The complete list shares infrastructure with extraction] -> Require the public HTML bootstrap to match the complete result prefix so validation confirms global-page semantics before checking all entries.
- [Steam is temporarily unavailable] -> Fail closed with an `error` report and allow standalone retry against the preserved CSV.
- [Manual CSV correction changes formatting but not identities] -> The digest intentionally invalidates the report; rerun validation to bind fresh evidence.
- [A later requested week fails extraction or validation] -> Return an unsuccessful command status while preserving earlier weekly artifacts and their independent eligibility.
- [An operator passes a combined or manually merged CSV] -> Reject it before chart validation or database access and require separate weekly artifacts.
- [Unexpected non-application chart products appear] -> Report a parse error rather than silently dropping an entry, because completeness cannot otherwise be proven.

## Migration Plan

1. Add weekly helper paths and extraction orchestration while retaining existing generated CSVs.
2. Extract reusable chart parsing/comparison behavior from the existing comparison evidence into the active validator with fixtures.
3. Add deterministic single-week sidecar generation, classification, and standalone CLI behavior without changing the application gate yet.
4. Invoke validation after each weekly CSV write and update aggregate CLI status/reporting while preserving mixed outcomes.
5. Add single-week, sidecar status, digest, and week-identity checks to approved CSV application before any database access.
6. Update documentation and tests, then perform an optional historical live chart smoke check.
7. Roll back by removing automatic invocation and report gating while retaining generated CSVs and reports; no database schema migration is involved.
