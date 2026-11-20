# Extraction

[`Python/main.py`](../Python/main.py) extracts one or more completed Steam weekly charts. It reads the PostgreSQL catalog, calls Steam and IsThereAnyDeal, writes one CSV per week, and immediately validates each CSV. It does not update PostgreSQL.

## Run extraction

The optional start and end dates must be Tuesdays in `YYYY-MM-DD` format:

```powershell
python Python\main.py 2026-08-04
python Python\main.py 2026-08-04 2026-08-25
```

With no dates, the command selects the last closed Tuesday. If today is Tuesday, it selects the previous Tuesday so an incomplete chart is not requested. A start date without an end date extracts one week. When both are supplied, the command extracts every Tuesday in the inclusive range; the end must not precede the start.

Useful options:

```text
--output PATH             CSV path for one week; directory for multiple weeks
--max-entries N           maximum admitted enrichment records
--itad-batch-size N       identifiers per ITAD lookup batch
--itad-batch-wait SECONDS maximum time spent collecting a lookup batch
```

For multiple weeks, `--output` must be a directory:

```powershell
python Python\main.py 2026-08-04 2026-08-25 --output review
```

Older invocations that enumerate three or more individual Tuesdays must be migrated to the first and last Tuesday of the desired contiguous range.

## Processing stages

Each week is independent:

1. Load the current games/tags catalog from PostgreSQL.
2. Fetch that week's global Steam Top 100.
3. Fetch historical ratings in parallel.
4. Batch Steam application identifiers for ITAD lookup and fetch historical price/discount.
5. Fall back to Steam store HTML when price data is missing; collect store tags only for games absent from the catalog.
6. Resolve unknown category identifiers and normalize tags.
7. Write the staging CSV and validate its chart identities.

The CSV columns are:

```text
week_date,rank,appid,name,tags,tag_ids,unresolved_tags,rating,price,discount,last_week_rank,consecutive_weeks,errors
```

## Outputs and exit status

Default staging files are timestamped under `helpers/CSV_error/` because no artifact is eligible before validation. Validation then moves the CSV and adjacent `<stem>.validation.json` sidecar to:

- `helpers/CSV/` when the chart matches exactly;
- `helpers/CSV_error/` for mismatches or validation errors.

The terminal reports the week, status, record count, final CSV path, and report path. It also lists unresolved tags and prints the relevant resolution command.

If one requested week fails, the process exits unsuccessfully but continues with other weeks. A previously passing week remains independently eligible for review and application.

## Safe next steps

- Passing artifact: inspect the CSV and sidecar, resolve any tags, then use the approved [database application](database-updates.md).
- `failed`: inspect chart differences and correct or regenerate the CSV before [revalidation](validation.md).
- `error`: diagnose the provider or parser failure and retry validation later.
