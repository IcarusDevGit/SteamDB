# Database updates and repairs

[`Python/UpdateDB.py`](../Python/UpdateDB.py) is the canonical entry point for controlled PostgreSQL changes. It has three operation groups: `apply`, `resolve`, and `repair`. Tag resolution is covered separately because it changes artifacts rather than the database.

## Apply reviewed weekly CSVs

With no CSV path, apply every `.csv` directly under `helpers/CSV` in filename order:

```powershell
python Python\UpdateDB.py apply csv --approved
```

To apply only one reviewed weekly CSV, supply its path:

```powershell
python Python\UpdateDB.py apply csv helpers\CSV\steam_top_100_2026-08-04_<timestamp>.csv --approved
```

An explicit report path is optional:

```powershell
python Python\UpdateDB.py apply csv helpers\CSV\weekly.csv --approved --validation-report review\weekly.validation.json
```

`--validation-report` is available only with an explicit CSV. Each default-batch file uses its adjacent digest-bound report.

After a file commits, its CSV and verified report move to `helpers/CSV upserted`. A failed default-batch file and any existing validation report move to `helpers/CSV_error` under collision-safe names, with a best-effort `.upsert-error.json` describing the failed stage. The command continues with later files and returns an unsuccessful overall status if any file failed. Explicit single-file failures remain at their supplied locations.

Before connecting for mutation, application requires:

- explicit `--approved` authorization;
- a non-empty CSV with all required fields;
- exactly one Tuesday week;
- unique week/rank and week/game identities;
- valid ranges and aligned unique tag names/identifiers;
- no unresolved tags or unacknowledged extraction errors;
- a `passed` validation sidecar for the same week;
- a sidecar SHA-256 matching the exact CSV bytes.

The database layer inserts missing tags and games without overwriting existing catalog attributes, then reconciles weekly records. The complete file is applied in one transaction; any persistence failure rolls back the mutation.

## Repairs

Repairs discover candidates and report `proposed`, `applied`, `skipped`, and `failed` counts. They are non-mutating by default:

```powershell
python Python\UpdateDB.py repair ratings --week 2026-08-04
python Python\UpdateDB.py repair rating-labels
python Python\UpdateDB.py repair prices --appid 730
python Python\UpdateDB.py repair weekly-stats --week 2026-08-04
python Python\UpdateDB.py repair game-names
python Python\UpdateDB.py repair weekly-identities
```

`ratings` and `prices` accept `--week`, `--appid`, and `--limit`. Applied operations require at least one of those bounds:

```powershell
python Python\UpdateDB.py repair ratings --appid 730 --apply
python Python\UpdateDB.py repair rating-labels --apply
python Python\UpdateDB.py repair prices --week 2026-08-04 --limit 20 --apply
```

`weekly-stats` requires `--week`, accepts `--limit`, and can select `--field all`, `last-week-rank`, or `consecutive-weeks`:

```powershell
python Python\UpdateDB.py repair weekly-stats --week 2026-08-04 --field last-week-rank --apply
```

`game-names` selects games whose stored name is empty or whitespace-only by default and looks up the authoritative English Steam name by application ID. Populated and `NULL` names are excluded. `--appid` and `--limit` optionally narrow the candidate set:

```powershell
python Python\UpdateDB.py repair game-names
python Python\UpdateDB.py repair game-names --appid 730 --apply
python Python\UpdateDB.py repair game-names --limit 100 --apply
python Python\UpdateDB.py repair game-names --apply
```

The first form is a dry run across all whitespace-name candidates. Supplying `--apply` explicitly authorizes guarded updates only for candidates that remain whitespace-only at mutation time.

Provider discovery and value validation finish before transactional persistence begins. Missing provider values are skipped rather than overwriting stored values.

### Repair progress

Every repair writes immediately flushed operational progress to standard error while keeping its final `proposed`, `applied`, `skipped`, and `failed` summary on standard output. Progress identifies the repair and current stage. Bounded provider and persistence work also identifies its phase, candidate or week, and completed/total counts so a slow request or database operation has a visible location.

`rating-labels` selects all `weeksheet.rating_label IS NULL` rows by default. Null means collection has not completed; `no_label` means the histogram was collected successfully but the game had fewer than 10 reviews at that week's cutoff. Candidate rows are loaded once and grouped by application ID, so recurring games use one complete histogram request to derive all of their weekly labels. Discovery finishes before the accumulated updates are written in one bulk transaction. `--week`, `--appid`, and `--limit` can narrow the set, while `--apply` without a filter explicitly applies the reported complete null-label set.

Provider phases reflect the actual source. Price repair distinguishes the shared `itad_lookup`, per-candidate `itad_history`, and `steam_fallback` steps. Weekly identity repair distinguishes rendered-chart and complete-chart requests. Provider failures are reported with the affected identity when they occur; retries report the provider, next attempt, and backoff duration when retry scheduling applies.

`persistence_progress` means that a candidate's SQL completed inside the still-pending transaction. It does not mean that row committed independently. The repair emits its persistence-stage completion only after the single transaction commits, and any later failure still rolls back all progress reported within that transaction.

Embedded callers may omit the reporter and receive no terminal progress without changing repair behavior.

`weekly-identities` compares every date already present in `weeksheet` with Steam's validated global Top 100 by default. It never uses the configurable extraction chart country and does not create absent dates. `--week` optionally narrows comparison:

```powershell
python Python\UpdateDB.py repair weekly-identities
python Python\UpdateDB.py repair weekly-identities --week 2026-08-04
python Python\UpdateDB.py repair weekly-identities --apply
```

Dry-run reports missing, unexpected, moved, and unchanged identities per week. `--apply` destructively reconciles mismatched weekly membership and rank in one transaction after every selected global chart validates. Retained games keep their week-specific price, discount, and rating; new global weekly identities leave those fields `NULL`. Missing catalog games use only the global chart's basic name and an empty tag set. US-only weekly rows are removed without deleting their catalog games.

## Adding a repair

1. Add a focused module under `Python/database_updates/repairs/`.
2. Keep that repair's candidate-selection SQL, mutation SQL, and transaction lifecycle in its repair module.
3. Obtain connections from `Python/db.py` through `db.get_connection()`; `db.py` retains connection configuration and main-workflow persistence, but does not collect repair-specific methods.
4. Accept an injectable connection factory in repair persistence functions so unit tests can use fake connections without a live database.
5. Expose `register_parser(subparsers)` and `run(args, dependencies=None)`.
6. Add the operation to the explicit registry in `Python/database_updates/__init__.py`.
7. Default to dry-run, define and report the operation's safe target semantics, and return `UpdateResult`.
8. Pass the optional reporter through every slow provider and persistence boundary, using bounded unit start/terminal events and monotonic persistence counts without adding intermediate commits.

Do not bypass the update CLI by calling database write helpers from extraction.
