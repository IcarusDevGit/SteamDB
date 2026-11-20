# Architecture

## Workflow

```text
PostgreSQL catalog snapshot          Steam weekly chart
             │                              │
             └──────────┐     ┌─────────────┘
                        ▼     ▼
                    extraction
                 Steam + ITAD enrichment
                        │
                        ▼
              staging CSV in CSV_error
                        │
                        ▼
                 chart validation
                  │             │
             passed          failed/error
                  │             │
          helpers/CSV     helpers/CSV_error
                  │
          operator review / optional tag resolution
                  │
                  ▼
          approved transactional apply
                  │
                  ▼
              PostgreSQL
```

Extraction is read-only with respect to PostgreSQL, but it needs a connection to load existing games and tags. Existing catalog entries determine whether Steam store tags and category names need to be fetched.

## Active modules

| Responsibility | Module |
|---|---|
| Extraction CLI, Tuesday selection, per-week isolation | [`Python/main.py`](../Python/main.py) |
| Provider clients and response parsing | [`Python/workflow_clients.py`](../Python/workflow_clients.py) |
| Pipeline orchestration and enrichment dependencies | [`Python/extraction_pipeline.py`](../Python/extraction_pipeline.py) |
| Rate limiting, concurrency, queues, and retries | [`Python/request_scheduler.py`](../Python/request_scheduler.py) |
| Record and branch-state models | [`Python/workflow_models.py`](../Python/workflow_models.py) |
| Terminal progress events | [`Python/workflow_progress.py`](../Python/workflow_progress.py) |
| Tag normalization and exception mapping | [`Python/tag_resolution.py`](../Python/tag_resolution.py) |
| Repository-relative artifact paths | [`Python/workflow_paths.py`](../Python/workflow_paths.py) |
| CSV serialization | [`Python/WriteCSV.py`](../Python/WriteCSV.py) |
| Steam chart validation | [`Python/ValidateEntries.py`](../Python/ValidateEntries.py) |
| PostgreSQL access and transactions | [`Python/db.py`](../Python/db.py) |
| Update CLI and operation registry | [`Python/UpdateDB.py`](../Python/UpdateDB.py), [`Python/database_updates/`](../Python/database_updates/) |

## Enrichment dependencies

For each weekly entry, the pipeline obtains a historical rating and resolves an ITAD identifier. ITAD history supplies historical price and discount when available; Steam store HTML is the fallback for missing current price data and supplies community tags for games absent from the catalog. Unknown Steam category identifiers are resolved through app details only when needed.

Each enrichment branch reaches a terminal state. Provider failures are retained in the CSV `errors` field rather than silently converted into valid data. Unresolved tag names remain in `unresolved_tags` and block database application.

## Mutation boundaries

- `main.py`: reads PostgreSQL and writes local artifacts; never updates PostgreSQL.
- `ValidateEntries.py`: writes and classifies CSV/report artifacts; never updates PostgreSQL.
- `UpdateDB.py resolve tags`: optionally rewrites the reviewed CSV, exception mappings, and validation sidecar; never updates PostgreSQL.
- `UpdateDB.py apply csv`: validates evidence and applies one weekly CSV transactionally.
- `UpdateDB.py repair ...`: discovers candidates first; writes only with `--apply` and a valid bound.

All PostgreSQL queries and transactions are owned by [`Python/db.py`](../Python/db.py).

## Analytical & BI consumption

Read-only analytical views defined in [`migrations/002_create_analytics_views.sql`](../migrations/002_create_analytics_views.sql) expose cleaned game longevity metrics, separated play modes, and post-discount retention transitions on top of `games`, `tags`, and `weeksheet`. Those views feed [`SteamDB_PBI.pbix`](../SteamDB_PBI.pbix) and [`SteamDB_Dashboard.xlsx`](../SteamDB_Dashboard.xlsx) to answer [`docs/PB_questions.md`](PB_questions.md).
