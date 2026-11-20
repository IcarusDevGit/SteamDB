## Context

The supported extraction CLI currently parses zero or more positional `dates`, validates each as a Tuesday, and passes the resulting list into an existing per-week processing loop. That loop already isolates extraction, CSV writing, validation, progress reporting, and failure handling by week. Command syntax is also reflected from the runtime parser into the generated command catalog, with handwritten examples maintained in the command descriptor and repository documentation.

## Goals / Non-Goals

**Goals:**

- Derive one ordered list of weekly dates from zero, one, or two positional date values before any extraction begins.
- Reuse the existing per-week execution and output behavior after date selection.
- Keep parser metadata suitable for automatic command-catalog generation.
- Make invalid ranges fail during command validation rather than partway through an extraction run.

**Non-Goals:**

- Supporting arbitrary non-contiguous week selection in the revised interface.
- Changing which Tuesday is selected when the command receives no dates.
- Adding a future-date or last-closed-week restriction that the current CLI does not enforce.
- Changing provider calls, extraction concurrency, CSV classification, validation, or database behavior.
- Updating the retired `Python_legacy/` implementation.

## Decisions

### Use two positional arguments

The parser will expose an optional `start_date` positional followed by an optional `end_date` positional. This preserves the existing zero-date and single-date forms and gives the concise multi-week form `START_DATE END_DATE`.

Flags such as `--start-date` and `--end-date` were considered, but they would make the common single-week invocation incompatible and more verbose. Retaining `dates` with variable arity was also considered, but it would preserve ambiguity between a range and an enumerated list.

### Validate boundaries before expanding the range

Each supplied boundary will use the existing ISO Tuesday validation. A separate date-selection function will reject an end date without a start date if invoked programmatically, reject a reversed range, and produce ISO-formatted Tuesdays at seven-day increments. Equal boundaries produce a one-element list.

Embedding expansion directly in the per-week loop was considered, but separating date selection makes the contract independently testable and ensures errors occur before provider work begins.

### Treat the end date as inclusive

Inclusive boundaries match the operator's chart-week vocabulary and make both the first and last requested weeks visible in the command. Expansion advances by seven days until the current date exceeds the end date.

An exclusive end was considered but would be surprising for date-oriented operator input and would force operators to specify the Tuesday after the final desired chart week.

### Preserve the existing execution loop

The expanded list will feed the current per-week loop unchanged. Existing multi-output directory checks will continue to use the derived list length, so an equal-boundary range behaves as a single-week run while a genuine multi-week range requires a directory when `--output` is provided.

Refactoring the pipeline to process the whole range in a single call was considered, but that would weaken current week-level failure isolation and broaden the change unnecessarily.

### Update generated and handwritten command documentation together

Runtime argument names and arity will flow into the generated catalog. The command descriptor examples, root extraction example, tests asserting parser metadata, and generated catalog will be updated in the same change.

## Risks / Trade-offs

- [Existing automation enumerates three or more Tuesdays] → Document the breaking syntax and provide equivalent start/end examples.
- [A large range can trigger substantial provider work] → Preserve visible per-week progress and existing provider scheduling; do not introduce an arbitrary range cap without a separate requirement.
- [Programmatic callers bypass `argparse`] → Centralize selection and range-order validation in a helper that tests can call directly.
- [Generated command documentation becomes stale] → Regenerate the catalog and run its freshness test as part of implementation verification.

## Migration Plan

Update operator invocations from enumerated dates such as `2026-08-04 2026-08-11 2026-08-18` to the inclusive range `2026-08-04 2026-08-18`. No data migration or rollback procedure is required; rollback consists of restoring the former parser and documentation.
