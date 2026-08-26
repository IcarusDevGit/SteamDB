## 1. Validation Models and CSV Input

- [x] 1.1 Add validation result, weekly result, chart identity, and difference models with `passed`, `failed`, and `error` outcomes; verify model serialization tests produce the documented report fields.
- [x] 1.2 Implement raw-byte SHA-256 calculation and single-week CSV parsing using only week, rank, and application identifier for comparison; verify unit tests accept one week, reject multiple distinct weeks, and prove enrichment-field changes do not affect comparison results.
- [x] 1.3 Detect malformed identities, incorrect counts, duplicate ranks, and duplicate application identifiers before chart comparison; verify focused tests report each condition against its week.

## 2. Steam Global Chart Retrieval

- [x] 2.1 Implement construction and fetching of `https://store.steampowered.com/charts/topsellers/global/{date}` for the CSV week through an injectable client; verify request tests assert the correct global URL and date.
- [x] 2.2 Isolate parsing of the page bootstrap and dynamic derivation of the complete-chart request without production hard-coded dates, timestamps, or fixture counts; verify stored HTML fixture tests recover the rendered identities and request parameters.
- [x] 2.3 Parse the complete Top 100 response and require the page's rendered identities to match its prefix, rejecting missing, non-application, incomplete, or inconsistent chart data; verify fixture tests distinguish parser/source errors from data mismatches.

## 3. Comparison, Reporting, and Standalone CLI

- [x] 3.1 Implement deterministic comparison of expected and extracted identities by rank and application identifier; verify tests cover exact matches, wrong ranks, missing entries, unexpected entries, and combined differences.
- [x] 3.2 Produce one result for the CSV's single week where a mismatch produces `failed`, a fetch/parser problem produces `error`, and multiple input weeks produce `error`; verify tests cover all outcomes.
- [x] 3.3 Write the versioned `<csv-stem>.validation.json` sidecar atomically beside the CSV with its digest, source URLs, counts, duplicates, and differences; verify report tests parse complete sidecars for all three statuses and confirm the CSV remains byte-for-byte unchanged.
- [x] 3.4 Add `Python/ValidateEntries.py` as a callable validator and standalone CLI that reports CSV and sidecar paths and uses distinct success, mismatch, and external-error exit codes; verify CLI tests assert output, exit status, and artifact preservation.

## 4. Extraction Workflow Integration

- [x] 4.1 Add repository-safe `helpers/CSV` and `helpers/CSV_error` path generation with collision-resistant filenames containing the week; verify path tests keep every generated artifact in its classified directory.
- [x] 4.2 Refactor `Python/main.py` to run extraction, CSV writing, and shared validation independently for each requested date before advancing; verify a multi-date integration test observes one single-week CSV and validation call per date.
- [x] 4.3 Classify each CSV and adjacent report under `helpers/CSV` only for `passed` and under `helpers/CSV_error` for `failed` or `error`; verify integration tests cover all three outcomes and retain byte-identical CSV content.
- [x] 4.4 Aggregate weekly command outcomes without aggregating CSV content; verify a mixed-outcome test returns an unsuccessful overall status while preserving and reporting an earlier passing weekly pair and every later failed/error pair produced.
- [x] 4.5 Preserve earlier weekly artifacts when a later extraction fetch raises before CSV creation; verify the command reports the failed week, returns unsuccessfully, and leaves earlier classified artifacts unchanged.

## 5. Database Application Gate

- [x] 5.1 Add sidecar resolution to the validated CSV update operation, using the adjacent default report and supporting an explicit report path; verify argument tests cover both resolution paths.
- [x] 5.2 Before opening a database connection, require exactly one CSV week, a parseable `passed` report, matching raw-byte CSV digest, and exact identity with that week in addition to `--approved`; verify gate tests reject multi-week CSVs, missing, malformed, `failed`, `error`, stale-digest, and wrong-week reports.
- [x] 5.3 Preserve the existing structural and semantic checks after the chart-evidence gate and allow application only when all gates pass; verify mocked integration tests prove rejected inputs never request a database connection and a fully valid approved input reaches the apply boundary.

## 6. Migration, Documentation, and Verification

- [x] 6.1 Reuse or retire relevant behavior from `comparison/compare_weekly_chart.py` without importing `Python_legacy` from production validation code; verify a repository search and import test show the active validator is isolated from the legacy tree.
- [x] 6.2 Add representative CSV, HTML-bootstrap, and complete-chart fixtures and run the deterministic validator, extraction, and database-gate test suites; verify the project test command completes successfully without network access.
- [x] 6.3 Document one-CSV-per-week extraction, `helpers/CSV` and `helpers/CSV_error` classification, mixed command outcomes, standalone revalidation, correction workflow, and the strengthened `UpdateDB.py` approval command; verify every documented command matches the implemented CLI help output.
- [x] 6.4 Perform an optional authorized live historical-week smoke check against Steam and record the result separately from deterministic acceptance; verify any network or page-format failure produces an `error` report and cannot authorize database application.
