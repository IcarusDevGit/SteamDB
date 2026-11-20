# Weekly chart validation

Validation proves that one extraction CSV contains the same ranked application identities as one Steam global weekly Top 100 chart. It intentionally ignores enrichment fields such as name, tags, rating, price, and discount.

## Automatic and manual validation

Extraction invokes validation automatically. To revalidate a corrected file or retry after a provider error:

```powershell
python Python\ValidateEntries.py helpers\CSV_error\steam_top_100_2026-08-04_<timestamp>.csv
```

The CSV must be non-empty and contain exactly one distinct `week_date`. That date must identify the Steam chart being compared.

## Comparison

The validator compares `rank` and `appid` and records:

- expected and actual counts;
- duplicate ranks or application identifiers;
- missing and unexpected entries;
- applications found at the wrong rank;
- fetch or parsing errors.

An exact identity match produces `passed`. Differences produce `failed`. An invalid input, fetch failure, or unreliable chart parse produces `error`.

## Digest-bound sidecar

Every outcome writes an adjacent `<csv-stem>.validation.json` report containing:

- schema version and status;
- SHA-256 of the exact CSV bytes;
- week and source URL;
- counts and structured differences or an error.

Revalidation recomputes the digest and replaces the report. Editing the CSV after validation makes the old sidecar stale; tag resolution and database application reject stale evidence.

## Artifact classification

The CSV and report are preserved together:

| Status | Directory | Database eligible? |
|---|---|---:|
| `passed` | `helpers/CSV/` | Only after review, no unresolved/errors, and `--approved` |
| `failed` | `helpers/CSV_error/` | No |
| `error` | `helpers/CSV_error/` | No |

The standalone command succeeds only for `passed`; both other outcomes return an unsuccessful process result while retaining paths for diagnosis.

Moving or renaming a CSV without its adjacent sidecar prevents the default database application command from finding its evidence. `UpdateDB.py apply csv` accepts `--validation-report PATH` only to identify a non-adjacent report; all digest and week checks still apply.
