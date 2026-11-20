# Troubleshooting

## Extraction cannot connect to PostgreSQL

Extraction loads a catalog snapshot before provider work, even though it performs no database writes. Check `DATABASE_URL` or the individual `PG*` settings described in [Configuration](configuration.md). Confirm the account can read `games` and `tags`.

Do not work around the failure by applying a CSV or changing write safeguards.

## Steam or ITAD requests fail

Check the relevant API key, network access, and provider country settings. Retryable HTTP failures use bounded retries and backoff; persistent failures appear in terminal progress or record errors.

For overloaded or rate-limited providers, reduce the matching concurrency or increase its interval. For example:

```dotenv
STEAM_STORE_CONCURRENCY=1
STEAM_STORE_INTERVAL=2
```

If extraction produced a CSV, preserve it and its sidecar. A failed week does not invalidate another week that passed independently.

## Chart validation reports `failed`

Open the adjacent `.validation.json` and inspect duplicate ranks/appids, missing or unexpected identities, and wrong ranks. Correct or regenerate the CSV, then run:

```powershell
python Python\ValidateEntries.py helpers\CSV_error\<file>.csv
```

Do not manually change the sidecar status or digest.

## Chart validation reports `error`

An error indicates invalid input or an unreliable chart fetch/parse, not a confirmed mismatch. Fix the reported input issue or retry validation after the provider recovers. The CSV/report pair remains in `helpers/CSV_error/`.

## Validation evidence is missing or stale

Keep `<stem>.csv` beside `<stem>.validation.json`, or pass the report explicitly with `--validation-report`. If the digest differs, revalidate the exact CSV bytes. There is no supported bypass for missing, non-passing, wrong-week, or stale evidence.

## Unresolved tags block application

Run a dry resolution first:

```powershell
python Python\UpdateDB.py resolve tags helpers\CSV\<file>.csv
```

Add explicit `--map "NAME=ID"` values only after verifying the identifier. Apply resolution with `--apply`; the command regenerates validation evidence. If names remain unresolved, the unsuccessful result is intentional.

## A repair refuses `--apply`

Ratings and prices require an operation bound such as `--week`, `--appid`, or `--limit`. Weekly statistics always require `--week`. Run the dry form first and confirm the reported effective target before adding `--apply`.

## Approved CSV application is rejected

Read the first validation error. Common causes are missing columns, multiple weeks, duplicate identities, invalid values, unresolved tags, extraction errors, or invalid sidecar evidence. Fix the artifact and revalidate it; do not bypass `--approved` or the evidence checks.

During the default batch, one rejection does not stop later files. The failed CSV and any existing validation report move to `helpers/CSV_error/` under collision-safe names. When possible, the adjacent `.upsert-error.json` identifies the source, failed stage, exception, timestamp, and whether the database transaction had already committed. The overall command still exits unsuccessfully when the batch has any failure.

## Where did the artifacts move?

- Passing validation: `helpers/CSV/`
- Failed/error validation and initial staging: `helpers/CSV_error/`
- Successfully upserted CSV/report pairs: `helpers/CSV upserted/`
- Failed default-batch upserts and diagnostics: `helpers/CSV_error/`

The validator reports the final CSV and sidecar paths after classification.
