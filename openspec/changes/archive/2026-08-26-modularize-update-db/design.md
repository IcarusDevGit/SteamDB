## Context

See `proposal.md` for motivation. The former `Python/UpdateDB.py` is a 312-line command aggregator containing persistence, provider requests, repair coordination, and duplicate CLI styles. It will move with its existing tree to `Python_legacy/`. The isolated `Python_temp/UpdateDB.py` proves a smaller approval-gated CSV workflow and will be promoted to `Python/`, but it does not provide an extension model for future repairs and currently delegates one transaction per week. Its `db.py` owns SQL but its row-by-row weekly upsert can conflict when existing games exchange unique ranks.

The stable operator convention is invoking `UpdateDB.py`. The extraction workflow must remain read-only, while approved application and repairs are explicit operator actions. The promoted and legacy trees must not import from one another; each must resolve only its own sibling modules and dependencies.

## Goals / Non-Goals

**Goals:**

- Keep the public entry point small as update and repair operations grow.
- Give each operation a simple function-based module boundary that is easy to test.
- Apply consistent targeting, dry-run, authorization, validation, reporting, and exit-status behavior.
- Preserve one database boundary and deliberate transaction ownership.
- Safely reconcile complete weekly rankings and atomically apply multi-week approved files.

**Non-Goals:**

- Creating a class hierarchy or dependency-injection framework for repairs.
- Automatically discovering modules through filesystem scanning or import side effects.
- Making extraction write business data.
- Preserving every legacy command when its behavior is superseded by reviewed extraction.
- Deleting the legacy implementation as part of this change.

## Decisions

### Keep `UpdateDB.py` as an explicit dispatcher

`UpdateDB.py` will build the root parser, register a small explicit command table, dispatch the selected handler, render its result, and translate exceptions into process exit codes. Application and repair commands will be grouped distinctly, for example `apply csv ...` and `repair prices ...`.

An explicit registry makes supported operations reviewable and prevents an arbitrary file from becoming executable merely by appearing in a directory. Automatic plugin discovery was considered but rejected because the expected operation count does not justify hidden imports and more complex failure handling.

### Organize operations in a function-based package

Create `Python/database_updates/` with focused modules. Each command module exposes functions equivalent to `register_parser(subparsers)` and `run(args, dependencies) -> UpdateResult`. Shared immutable result and candidate representations live in `common.py`. The initial shape is:

```text
Python/
|-- UpdateDB.py
|-- db.py
`-- database_updates/
    |-- __init__.py
    |-- common.py
    |-- apply_validated_csv.py
    `-- repairs/
        |-- __init__.py
        |-- ratings.py
        |-- prices.py
        |-- weekly_stats.py
        |-- game_names.py
        `-- tags.py
```

Modules provide sufficient namespacing for stateless operations. Classes were considered but rejected as the default because they would add ceremony without persistent state. A future repair may introduce a private class if it owns meaningful batching or lifecycle state while preserving the function contract at the command boundary.

### Separate candidate discovery from application

A repair handler first resolves a bounded target, reads candidates through `db.py`, obtains any external values through existing provider clients, validates proposed changes, and creates an `UpdateResult`. Without explicit application authorization it stops after reporting. With authorization it passes only validated candidates to a purpose-specific transactional `db.py` function.

This avoids database writes interleaved with remote calls and makes dry-run output representative of the intended mutation. A single streaming fetch-and-update loop was rejected because provider failure could leave an opaque partial repair.

### Centralize safety policy while keeping repair rules local

Shared parsing and result helpers enforce dry-run defaults, explicit `--apply`, outcome counters, and consistent exit codes. Each repair owns its appropriate targeting rules and candidate validation because price, rating, tag, and ranking repairs have different valid inputs. Apply mode requires a bounded target; a repair may define a safe default only when it can report that bound before mutation.

A universal target schema was considered but rejected because it would expose meaningless flags for some operations. Conversely, fully independent safety handling was rejected because command behavior would drift.

### Apply a reviewed CSV in one database transaction

CSV parsing and complete validation occur before opening a write transaction. The update service passes all records to one `db.py` application function, which owns commit and rollback for the entire file rather than opening one transaction per week. This prevents a later week from failing after earlier weeks have committed.

Per-week transactions were considered for lower lock duration but rejected because the operator authorizes one reviewed artifact and should receive all-or-nothing semantics for that artifact.

### Reconcile weekly rows as a set

For every week represented in an approved file, the database boundary will reconcile the validated weekly set in a way that cannot transiently violate both `(week_date, rank)` and `(week_date, game_id)` uniqueness when ranks change. Implementation may stage rows, use a set-based statement, or temporarily move affected ranks inside the same transaction; the chosen SQL must preserve rows outside the authorized set unless the operation explicitly represents a complete-week replacement.

Continuing row-by-row `ON CONFLICT (week_date, game_id)` upserts was rejected because two existing games exchanging ranks can collide with the independent rank constraint.

### Inventory legacy repairs before migration

Legacy commands will be classified as superseded, still operationally required, or compatibility aliases. Required commands move into focused repair modules and gain the common safety contract. Superseded commands are documented and removed rather than retained inside the dispatcher. Temporary aliases may translate legacy spellings to the new command path without duplicating implementation.

Copying all legacy behavior was rejected because it would preserve obsolete provider flows and undermine the reviewed extraction boundary. Removing everything without inventory was also rejected because operators may still rely on targeted maintenance.

### Promote the isolated tree and retain an import-isolated legacy tree

Rename the current `Python/` directory to `Python_legacy/`, then rename `Python_temp/` to `Python/`. Active commands, tests, and documentation will reference the promoted `Python/` tree. Evidence and documentation specifically describing the former implementation will reference `Python_legacy/`. Neither tree may alter `sys.path` to load the other or import modules from the other directory.

Keeping `Python_temp/` indefinitely was rejected because it falsely describes the selected implementation as temporary. Merging the trees was rejected because duplicate module names and incompatible workflow boundaries would make import resolution ambiguous.

## Risks / Trade-offs

- [Dry-run discovery can become stale before application] -> Keep discovery and apply in one invocation initially, report the effective target, and revalidate persistence preconditions in the transaction.
- [Whole-file transactions may hold locks longer for large CSVs] -> Validate outside the transaction, batch SQL within it, and keep provider access outside it.
- [Repair modules may duplicate orchestration patterns] -> Centralize result, authorization, and reporting helpers while leaving domain validation local.
- [Legacy command changes may disrupt operator habits] -> Inventory usages, document mappings, and retain thin aliases only where there is evidence of continued use.
- [Weekly set reconciliation can accidentally affect records outside scope] -> Define whether input is a complete-week replacement, validate identities and rank ranges, and test preservation of unauthorized rows.
- [A shared `dependencies` value can become an informal service container] -> Keep dependencies explicit and minimal; introduce typed protocols only when tests demonstrate a need.

## Migration Plan

1. Rename the former implementation to `Python_legacy/`, promote `Python_temp/` to `Python/`, update references, and verify import isolation in both trees.
2. Add the update package, shared result contract, and explicit dispatcher while keeping approved CSV behavior covered by tests.
3. Move CSV parsing and validation into its operation module and change `db.py` to accept all validated records under one transaction.
4. Implement and integration-test conflict-safe weekly reconciliation, including exchanged ranks and rollback across multiple weeks.
5. Inventory legacy commands and call sites, then migrate required repairs one at a time with dry-run, bounded targeting, and explicit apply behavior.
6. Add documented aliases for required compatibility and document superseded commands and their replacement workflow.
7. Run unit and disposable-database integration tests before declaring the promoted workflow complete. Roll back the directory promotion by restoring the two original directory names; no schema rollback is expected.
