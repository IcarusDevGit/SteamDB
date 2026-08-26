# Active SteamDB workflow

This directory contains the active extraction and database-update workflow. It
does not import or execute code from `Python_legacy/`; comparison utilities that
intentionally load both implementations live under repository `comparison/`.

## Extraction

Extraction is read-only and processes every requested Tuesday independently:

```powershell
python Python\main.py 2026-08-04 2026-08-11
```

Each week produces its own CSV and adjacent `<csv-stem>.validation.json`
report. Exact Steam Top 100 matches are stored together under `helpers/CSV/`.
Chart mismatches and fetch/parser errors are stored under
`helpers/CSV_error/`. If one requested week fails, the command exits
unsuccessfully but earlier passing weeks remain independently eligible for
application.

To retry validation after a provider error or after correcting a CSV:

```powershell
python Python\ValidateEntries.py helpers\CSV_error\steam_top_100_2026-08-04_<timestamp>.csv
```

Revalidation recomputes the raw-byte digest, replaces the sidecar, and moves
the CSV/report pair to the directory matching the new `passed`, `failed`, or
`error` outcome. Validation compares only week, rank, and appid; enrichment
columns do not affect chart validation.

## Reviewed CSV application

Database application is separate and requires explicit approval:

```powershell
python Python\UpdateDB.py apply csv helpers\CSV\steam_top_100_2026-08-04_<timestamp>.csv --approved
```

The former focused invocation remains an alias:

```powershell
python Python\UpdateDB.py helpers\CSV\steam_top_100_2026-08-04_<timestamp>.csv --approved
```

The adjacent passing validation report is mandatory in addition to
`--approved`. The updater verifies that the CSV contains exactly one week, the
report covers that same week, and its SHA-256 matches the exact CSV bytes before
database mutation. An explicit report location can be supplied when needed:

```powershell
python Python\UpdateDB.py apply csv helpers\CSV\weekly.csv --approved --validation-report helpers\CSV\weekly.validation.json
```

Structural and semantic CSV validation still runs before the single-week CSV
is applied as one transaction. There is no bypass for missing, failed, error,
wrong-week, or stale-digest validation evidence.

## Resolving CSV tags

Completed extraction output lists unresolved tags and an artifact-specific command. Resolution is
a dry run unless `--apply` is supplied:

```powershell
python Python\UpdateDB.py resolve tags helpers\CSV\steam_top_100_2026-08-04.csv
python Python\UpdateDB.py resolve tags helpers\CSV\steam_top_100_2026-08-04.csv --map "Dystopian=1001"
python Python\UpdateDB.py resolve tags helpers\CSV\steam_top_100_2026-08-04.csv --map "Dystopian=1001" --apply
```

The resolver checks database tags, configured exceptions, and one Steam tag-list response before
using explicit mappings. Apply mode requires matching passing validation evidence, atomically
rewrites the CSV, saves used explicit mappings, and creates fresh validation evidence. Partial
resolution is retained but exits unsuccessfully. This operation never writes to the database;
database insertion remains behind the separate `apply csv ... --approved` command.

## Repairs

Repairs inspect and report candidates by default. They write only when `--apply`
is present, and apply mode requires an operation-appropriate bound.

```powershell
python Python\UpdateDB.py repair ratings --week 2026-08-04
python Python\UpdateDB.py repair ratings --appid 730 --apply
python Python\UpdateDB.py repair prices --week 2026-08-04 --limit 20 --apply
python Python\UpdateDB.py repair weekly-stats --week 2026-08-04 --apply
```

Every result reports its effective target plus proposed, applied, skipped, and
failed counts. Provider requests finish before a single transactional apply.

## Adding a repair

1. Add a focused module under `database_updates/repairs/`.
2. Expose `register_parser(subparsers)` and `run(args, dependencies=None)` functions.
3. Add the module to the explicit registry in `database_updates/__init__.py`.
4. Query candidates and persist validated updates only through `db.py`.
5. Default to dry-run, require a bounded target for `--apply`, and return an
   `UpdateResult`.

Classes are unnecessary unless a repair owns meaningful batching or lifecycle
state; the public operation boundary remains function-based.

## Legacy command migration

| Legacy command | Classification | Active replacement |
|---|---|---|
| `upsert-csv` | Compatibility alias | `apply csv <path> --approved` |
| `update-null-ratings` | Compatibility alias | `repair ratings [target] [--apply]` |
| `update-null-prices` | Compatibility alias | `repair prices [target] [--apply]` |
| `update-last-week-rank`, `update_last_week_rank` | Compatibility alias | `repair weekly-stats --field last-week-rank --week ...` |
| `update-consecutive-weeks`, `update_consecutive_weeks` | Compatibility alias | `repair weekly-stats --field consecutive-weeks --week ...` |
| `update-games` | Superseded | Review and apply a new extraction CSV |
| `update-missing-tags` | Superseded | Extraction emits unresolved tags for review |
| `resolve-missing-tags` | Superseded | `resolve tags <csv> [--map NAME=ID] [--apply]` |
| `apply-missing-tags` | Superseded | Apply the complete reviewed extraction CSV |

Compatibility aliases use the same handlers and safety rules. In particular,
repair aliases are dry-run unless `--apply` is explicitly provided.

## Verification

```powershell
python -m unittest discover -s Python\Tests -t Python -p "test_*.py" -v
```

The real PostgreSQL check uses a temporary schema and refuses to run without
`ALLOW_DISPOSABLE_DB_TEST=1` and PostgreSQL connection variables:

```powershell
python Python\Tests\integration_disposable_db.py
```

Provider intervals, concurrency, queue sizes, retry counts, maximum pipeline
entries, and ITAD batch settings remain configurable through the environment
variables used by `main.py`.
