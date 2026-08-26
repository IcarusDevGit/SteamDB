## Why

The extraction workflow can produce a structurally valid CSV whose games are missing, duplicated, or assigned to the wrong global weekly ranks. A combined multi-week artifact also makes one later extraction or validation error block earlier successful weeks. Operators need independently validated weekly CSVs before database application, while retaining every non-passing artifact for diagnosis and correction.

## What Changes

- Add a standalone weekly Top 100 validator that compares only `(rank, appid)` for one extraction week against `https://store.steampowered.com/charts/topsellers/global/{date}`.
- Detect missing, unexpected, duplicate, incorrectly ranked, and incorrectly counted entries for the weekly artifact.
- Process each requested week independently through extraction, CSV writing, and automatic validation so a later failure cannot discard or invalidate an earlier outcome.
- Place passing CSVs and their digest-bound reports under `helpers/CSV/`, and place mismatched or unverifiable CSVs and reports under `helpers/CSV_error/`.
- Return an unsuccessful command status when any requested week fails extraction, mismatches, or cannot be validated while still reporting every artifact produced for other weeks.
- **BREAKING** Require `UpdateDB.py` to verify a matching successful sidecar report in addition to explicit `--approved` confirmation before applying a CSV.
- **BREAKING** Require each CSV presented for validation or database application to contain exactly one week.
- Keep names, ratings, tags, prices, discounts, and other enrichment fields outside the chart-comparison contract.

## Capabilities

### New Capabilities

- `top100-chart-validation`: Defines exact single-week rank/application membership validation, outcome-based artifact routing, difference reporting, preservation, and digest binding.

### Modified Capabilities

- `data-extraction-workflow`: Requires one independently written and validated CSV per requested week, with earlier outcomes preserved after later failures.
- `validated-database-update`: Requires a passing single-week validation report bound to the exact single-week CSV before database mutation is permitted.

## Impact

- Adds `Python/ValidateEntries.py` and chart-validation fixtures/tests.
- Affects `Python/main.py`, the extraction orchestration boundary, `Python/UpdateDB.py`, the validated CSV application module, helper-path handling, operator documentation, and generated report artifacts.
- Uses Steam's global weekly chart page and its complete chart data, with request failure and page-format drift treated as blocking validation errors.
- Does not validate enrichment accuracy and does not mutate PostgreSQL during chart validation.
