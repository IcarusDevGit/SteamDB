# Active Python module map

For system flow and mutation boundaries, see [`docs/architecture.md`](../docs/architecture.md).

| Responsibility | Module |
|---|---|
| CLI, date selection, per-week execution | `main.py` |
| Provider clients and parsers | `workflow_clients.py` |
| Normalized records and branch states | `workflow_models.py` |
| Provider limits, retries, and backpressure | `request_scheduler.py` |
| Dependency-aware orchestration and ITAD batching | `extraction_pipeline.py` |
| Tag normalization | `tag_resolution.py` |
| Repository-relative output paths | `workflow_paths.py` |
| Progress event reporting | `workflow_progress.py` |
| PostgreSQL queries and transactions | `db.py` |
| CSV serialization | `WriteCSV.py` |
| Chart validation and sidecars | `ValidateEntries.py`, `validation_models.py` |
| Update CLI | `UpdateDB.py` |
| Update operation registry and result model | `database_updates/` |
| Function-based repairs | `database_updates/repairs/` |
| Active automated tests and fixtures | `Tests/` |

Runtime review artifacts live in repository `helpers/CSV/` after passing validation and `helpers/CSV_error/` while staged, failed, or errored.
