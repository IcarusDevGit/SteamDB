## Why

Operators currently have to enumerate every Tuesday when extracting several consecutive chart weeks. Accepting a start date with an optional end date makes contiguous multi-week runs shorter, clearer, and less error-prone while preserving the existing default and single-week workflows.

## What Changes

- Replace the extraction command's arbitrary list of Tuesday dates with a required start date and optional end date when dates are supplied.
- Preserve no-date behavior by extracting the last closed Tuesday.
- Preserve single-date behavior by extracting only the supplied start date.
- When an end date is supplied, expand the inclusive range into consecutive Tuesdays and process each week independently.
- Reject malformed dates, non-Tuesday boundaries, and ranges whose end precedes their start before extraction begins.
- Update extraction tests, command metadata, examples, and generated operator documentation for the revised interface.
- **BREAKING**: Invocations that enumerate three or more individual Tuesday dates are no longer accepted; operators must provide the first and last Tuesday instead.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `data-extraction-workflow`: Change multi-week date selection from an arbitrary list of Tuesdays to an inclusive range defined by a start Tuesday and optional end Tuesday.

## Impact

The change affects the supported `Python/main.py` CLI parser and date-selection logic, its unit tests, the extraction command descriptor in `Python/command_catalog.py`, the generated `docs/commands.md` catalog, and extraction examples in repository documentation. It does not affect `Python_legacy/`, database writes, provider behavior, per-week artifact isolation, or exit-status aggregation.
