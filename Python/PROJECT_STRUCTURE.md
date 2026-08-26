# Isolated extraction workflow module map

| Responsibility | Target module |
|---|---|
| CLI and date selection | `main.py` |
| Weekly top sellers and provider clients | `workflow_clients.py` |
| Normalized records and states | `workflow_models.py` |
| Provider limits, retry, and backpressure | `request_scheduler.py` |
| Dependency-aware orchestration and ITAD batching | `extraction_pipeline.py` |
| ITAD lookup/history | `workflow_clients.py` |
| Historical ratings | `workflow_clients.py` |
| Steam HTML price/tags and app-details categories | `workflow_clients.py` |
| Tag normalization | `tag_resolution.py` |
| Database queries and transactions | `db.py` |
| Validated persistence CLI | `UpdateDB.py` |
| Update operation registry and result model | `database_updates/` |
| Function-based targeted repairs | `database_updates/repairs/` |
| CSV serialization | `WriteCSV.py` |
| Weekly chart validation and sidecars | `ValidateEntries.py`, `validation_models.py` |
| Passing CSV/report pairs | repository `helpers/CSV/` directory |
| Failed/error CSV/report pairs | repository `helpers/CSV_error/` directory |

The legacy scripts remain available for comparison, but the isolated workflow
does not import or execute any module from the repository's `Python_legacy/` directory.
