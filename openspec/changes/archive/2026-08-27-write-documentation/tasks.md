## 1. Evidence Inventory

- [x] 1.1 Inventory canonical CLI commands, arguments, safety defaults, and output paths from the active `Python/` parsers and verify each planned example against source or executable `--help` output.
- [x] 1.2 Inventory environment-variable names, external services, database prerequisites, and optional tuning controls from active source and tests, verifying that no local secret values are captured.
- [x] 1.3 Map active modules, workflow stages, validation states, generated artifacts, and database mutation boundaries against the current OpenSpec specifications and tests, recording any documentation gaps or contradictions to resolve.

## 2. Documentation Entry Point

- [x] 2.1 Create the root `README.md` with project purpose, active-scope statement, prerequisites, safe quick start, workflow overview, and links to detailed pages; verify every linked file and example path exists.
- [x] 2.2 Create `docs/architecture.md` covering the active module map, provider-to-artifact data flow, validation/review boundary, and database update boundary; verify all referenced modules are in `Python/` and no legacy module is presented as active.
- [x] 2.3 Create `docs/configuration.md` documenting verified environment-variable names with placeholder values, required versus optional semantics, and external-service roles; verify it contains no value copied from `.env.local`, `.neon`, or connection files.

## 3. Operator Workflows

- [x] 3.1 Create `docs/extraction.md` describing date selection, provider orchestration, read-only behavior, outputs, partial failures, and canonical examples; verify commands and artifact paths against `Python/main.py` and active tests.
- [x] 3.2 Create `docs/validation.md` describing automatic and manual validation, sidecar integrity, pass/fail/error classification, and file movement; verify behavior against `Python/ValidateEntries.py`, validation models, and the top-100 validation specification.
- [x] 3.3 Create `docs/tag-resolution.md` describing unresolved-tag reporting, dry-run mappings, apply behavior, CSV/report regeneration, and the separation from database writes; verify examples against the active resolver parser and tag synchronization specification.
- [x] 3.4 Create `docs/database-updates.md` describing reviewed CSV application, approval and validation gates, transaction behavior, repair commands, dry-run defaults, bounded apply operations, and result reporting; verify commands against `Python/UpdateDB.py` and registered update modules.

## 4. Maintainer Guidance

- [x] 4.1 Create `docs/testing.md` with unit-test discovery, disposable PostgreSQL integration-test safeguards, fixture boundaries, and expected prerequisites; verify commands against the active test tree without enabling a real database mutation.
- [x] 4.2 Create `docs/troubleshooting.md` covering provider failures, validation mismatches, stale or missing sidecars, unresolved tags, database configuration failures, and safe retry paths; verify each recommendation preserves the documented mutation safeguards.
- [x] 4.3 Reconcile `Python/README.md` and `Python/PROJECT_STRUCTURE.md` with the new documentation by retaining implementation-local content or replacing duplication with clear links; verify no contradictory active instructions remain across these files.

## 5. Documentation Verification

- [x] 5.1 Check all relative Markdown links, referenced repository paths, headings, and command snippets and verify there are no broken internal references.
- [x] 5.2 Search the delivered documentation for `Python_legacy`, legacy-only entry points, comparison tooling, prompt history, generated artifact details, and credential-like values; verify exclusions are respected except for an explicit statement that legacy code is out of scope.
- [x] 5.3 Run the existing active unit-test suite as a regression check where the environment permits, and verify the final diff contains only documentation and OpenSpec planning artifacts with no runtime, generated-data, cache, or secret-file changes.
