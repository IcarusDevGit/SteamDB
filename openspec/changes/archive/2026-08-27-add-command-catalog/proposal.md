## Why

The supported Python command surface is distributed across several entry points and module registries, while its documentation is maintained separately and can become incomplete when commands or arguments change. Operators and contributors need one authoritative catalog that explains every supported command and argument and detects undocumented additions.

## What Changes

- Add a generated Python command catalog to the operator documentation and link it from the repository and active-Python README files.
- Introduce a central documentation registry for supported standalone entry points and registered `UpdateDB.py` command groups.
- Derive command and argument details from the same `argparse` parsers used at runtime, supplemented by registry metadata for behavior, safety, and examples.
- Document hidden compatibility aliases in a clearly separated deprecated section without presenting them as supported workflows.
- Add automated checks that fail when a supported command is missing from the registry or the committed catalog is stale.
- Define the registration convention that every newly supported Python command must follow.

## Capabilities

### New Capabilities

- `python-command-catalog`: Provides a complete, generated catalog of supported Python commands, arguments, operational behavior, and deprecated aliases, with automatic completeness and freshness checks.

### Modified Capabilities

None.

## Impact

- Affects Python CLI composition and metadata around `Python/main.py`, `Python/ValidateEntries.py`, `Python/UpdateDB.py`, and `Python/database_updates/`.
- Adds a documentation-generation utility, a committed catalog under `docs/`, README navigation links, and command-catalog tests.
- Does not change existing command syntax, runtime behavior, database safety boundaries, or supported external APIs.
- Excludes `Python_legacy/`, comparison utilities, tests used as scripts, and internal modules without a supported operator CLI.
