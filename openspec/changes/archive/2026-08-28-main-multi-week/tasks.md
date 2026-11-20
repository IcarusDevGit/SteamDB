## 1. Date Range Contract

- [x] 1.1 Add CLI tests for no dates, one start Tuesday, an inclusive start/end range, equal boundaries, malformed or non-Tuesday boundaries, reversed ranges, and excess positional dates; verify the focused extraction CLI test module fails against the old parser for the new cases.
- [x] 1.2 Replace the variable-length `dates` positional with optional `start_date` and `end_date` positionals and add a date-selection helper that expands inclusive Tuesdays and rejects reversed ranges; verify the focused parser and helper tests pass.

## 2. Multi-Week Execution

- [x] 2.1 Feed the selected or expanded weekly dates into the existing per-week execution loop while preserving the last-closed-Tuesday default; verify CLI tests observe each inclusive range week exactly once and preserve single-week behavior.
- [x] 2.2 Cover output resolution and failure isolation for expanded ranges, including equal-boundary single-week output and genuine multi-week directory output; verify the focused multi-week execution tests pass.

## 3. Operator Documentation

- [x] 3.1 Update extraction command metadata, safeguards, and examples for `START_DATE [END_DATE]`, including migration away from enumerated dates; verify command-catalog parser metadata tests recognize `start_date` and `end_date`.
- [x] 3.2 Update applicable README or extraction guidance and regenerate `docs/commands.md`; verify `python Python/generate_command_catalog.py` succeeds and the catalog freshness test passes.

## 4. Verification

- [x] 4.1 Run the complete active Python test suite and verify all tests pass without changes under `Python_legacy/`.
- [x] 4.2 Run strict OpenSpec validation for `main-multi-week` and verify the proposal, delta specification, design, and task artifacts are valid.
