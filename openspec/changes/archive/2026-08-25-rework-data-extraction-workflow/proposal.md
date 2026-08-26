## Why

The weekly data-extraction workflow is fragmented across scripts and performs remote requests in an unnecessarily slow order. It needs a single, rate-limit-aware orchestration model that produces complete, reviewable data for one or more Tuesdays before any database mutation occurs.

## What Changes

- Reorganize the Python project around a clear extraction pipeline coordinated by `main.py`, with database access isolated in `DB.py` and persisted updates isolated in `UpdateDB.py`.
- Support collecting weekly top-seller data for multiple Tuesdays in one run.
- Process entries through a bounded asynchronous pipeline that permits work on multiple games concurrently while preserving each entry's data dependencies.
- Batch eligible ITAD identifier lookups, alternate work across providers, and enforce per-provider request limits so provider wait times do not unnecessarily stall the pipeline.
- Require ITAD history to wait for the entry's ITAD game id and require conditional Steam HTML access to wait for the ITAD history outcome; allow historical Steam rating collection to proceed independently.
- Fetch Steam tags only for games absent from the database, normalize exception-mapped tags, and resolve unknown weekly category names through Steam app details only when required.
- Prefer ITAD price and discount history; omit unavailable ITAD values and use the Steam store page as the price/discount fallback.
- Write collected data to CSV for user validation, then keep database application as a separate explicit step.
- Place script-generated `.csv`, `.json`, and `.md` helper artifacts under a `helpers` directory.

## Capabilities

### New Capabilities

- `data-extraction-workflow`: Defines orchestration, multi-date collection, dependency-aware asynchronous enrichment, provider-aware throttling, fallback behavior, and reviewable output.
- `catalog-tag-synchronization`: Defines conditional tag/category collection, exception mapping, and insertion of missing games and tags.
- `validated-database-update`: Defines the separation between CSV validation and database updates, including database access ownership.

### Modified Capabilities

None. The project has no existing OpenSpec capability specifications.

## Impact

- Affects the Python entry point and extraction modules corresponding to weekly sellers, ITAD, Steam reviews, Steam HTML/app-details data, CSV writing, database queries, and database updates.
- Changes runtime request scheduling against Steam Web API, Steam Store endpoints, and IsThereAnyDeal by introducing bounded cross-entry concurrency and lookup batching while preserving their rate limits.
- Changes generated-file locations and the operator workflow for multi-Tuesday extraction, validation, and database update.
- May require renaming or consolidating current scripts to match the target module responsibilities described by the workflow brief.
