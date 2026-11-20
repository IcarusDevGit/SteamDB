## 1. Shared Models and Utilities

- [x] 1.1 Document `workflow_models.py`, `validation_models.py`, and `database_updates/common.py` with module/class/function docstrings that explain model semantics, state, and result lifecycles; verify every non-trivial definition has accurate boundary documentation.
- [x] 1.2 Document `workflow_paths.py`, `workflow_progress.py`, `request_scheduler.py`, `tag_resolution.py`, and `WriteCSV.py`, adding inline comments only for non-obvious path rules, event formatting, rate limiting/retry behavior, tag resolution precedence, and CSV I/O; verify the diff contains documentation-only changes.

## 2. Extraction and Provider Workflows

- [x] 2.1 Document `extraction_pipeline.py`, including client contracts, batching lifecycle, concurrent branch orchestration, caching, state transitions, and terminal-state enforcement; verify comments match the pipeline tests and do not claim stronger failure guarantees than the code provides.
- [x] 2.2 Document `workflow_clients.py`, including provider responsibilities, request/response parsing, retry escalation, synchronous worker boundaries, and provider-specific fallback behavior; verify comments align with the client tests and actual request construction.
- [x] 2.3 Document `main.py` with CLI, date validation, dependency construction, extraction, output selection, and validation-flow contracts; verify the documented processing order matches the implementation and CLI tests.

## 3. Validation and Database Workflows

- [x] 3.1 Document `ValidateEntries.py`, including CSV identity parsing, Steam chart retrieval, comparison, evidence generation, artifact classification, and error behavior; verify the descriptions match the validation tests.
- [x] 3.2 Document `db.py` with connection, catalog snapshot, bulk-write, transaction, rollback, and repair-query contracts; verify transaction comments correspond exactly to commit, rollback, and cleanup paths.
- [x] 3.3 Document `UpdateDB.py` and `database_updates/apply_validated_csv.py`, including command dispatch, compatibility aliases, approval gates, structural/semantic validation, evidence checks, and atomic persistence; verify the diff preserves signatures and control flow.
- [x] 3.4 Document `database_updates/resolve_csv_tags.py` with mapping precedence, discovery, rewrite, validation, atomic replacement, and dry-run behavior; verify comments match tag-resolution tests and describe filesystem side effects accurately.
- [x] 3.5 Document `database_updates/repairs/common.py`, `ratings.py`, `prices.py`, and `weekly_stats.py` with target validation, discovery concurrency, dry-run/apply boundaries, and persistence behavior; verify each command's documented behavior matches its registered arguments and tests.
- [x] 3.6 Review `database_updates/__init__.py` and `database_updates/repairs/__init__.py`; add concise package docstrings only if they convey useful package responsibility, and verify empty initializers remain untouched when documentation would be artificial.

## 4. Tests and Integration Helpers

- [x] 4.1 Document reusable fakes, fixtures, helper classes/functions, and complex setup across `Python/Tests/test_*.py` without narrating ordinary assertions or duplicating descriptive test names; verify all test modules were reviewed and comments focus on non-obvious intent.
- [x] 4.2 Document `Python/Tests/integration_disposable_db.py`, including environment safeguards, disposable schema lifecycle, connection wrapper, fixture creation, and cleanup expectations; verify safety-related comments match the implemented guards and teardown flow.
- [x] 4.3 Review `Python/Tests/__init__.py`; add a package docstring only if useful, and verify it remains empty if no meaningful package responsibility needs explanation.

## 5. Verification and Quality Review

- [x] 5.1 Compile every Python file under `Python/` with `python -m compileall Python` (or the repository's configured Python executable) and verify compilation succeeds.
- [x] 5.2 Run the complete test suite with the repository-documented test command and verify all unit and integration-safe tests pass without behavior changes.
- [x] 5.3 Inspect the final diff and verify edits are limited to `Python/**/*.py`, contain only docstrings/comments, do not touch `Python_legacy/` or `comparison/`, and avoid redundant line-by-line narration.
- [x] 5.4 Perform a focused accuracy review of `extraction_pipeline.py`, `workflow_clients.py`, `ValidateEntries.py`, `db.py`, and `database_updates/`; verify comments correctly describe concurrency, fallback, validation, atomic-write, and transaction behavior.
