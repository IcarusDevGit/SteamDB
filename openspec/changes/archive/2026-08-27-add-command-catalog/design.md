## Context

The active Python workflow exposes two standalone `argparse` entry points in `main.py` and `ValidateEntries.py`, plus a hierarchical dispatcher in `UpdateDB.py`. Update subcommands are already composed from module tuples in `database_updates/__init__.py`, and each module contributes a `register_parser` function. Hidden aliases are constructed separately inside `UpdateDB.py`. Argument details and operational guidance currently live across parser declarations and several topic guides.

The catalog must remain useful as operator documentation while being mechanically tied to runtime definitions. Importing parser builders is safe because the active modules guard execution with `if __name__ == "__main__"`, but generation must not invoke handlers, connect to PostgreSQL, or contact external providers.

## Goals / Non-Goals

**Goals:**

- Make supported command registration the source for catalog membership.
- Reuse runtime `argparse` structures for syntax and argument facts.
- Keep behavioral descriptions, examples, and safety notes explicit and reviewable.
- Detect missing registrations and stale generated documentation in tests.
- Preserve all current command invocations and compatibility behavior.

**Non-Goals:**

- Replacing `argparse` or redesigning command syntax.
- Dynamically importing every Python file or treating every executable module as supported.
- Cataloging `Python_legacy/`, comparison tooling, test entry points, or internal helper functions.
- Removing compatibility aliases or consolidating the three current executable scripts.
- Generating all topic documentation from command metadata.

## Decisions

### Use an explicit descriptor registry for catalog membership

Create a small registry whose entries describe canonical command identity, executable path and command path, parser source, behavior/effects, safeguards, examples, and support status. Standalone commands and `UpdateDB.py` leaf commands use the same descriptor shape. The catalog generator consumes this registry, and tests validate unique identities and usable parser sources.

An explicit registry defines the supported product surface without accidentally publishing test scripts or internal modules. Filesystem discovery was rejected because an `if __name__ == "__main__"` block does not mean a script is an operator-supported command. A completely handwritten Markdown inventory was rejected because it cannot reliably track parser changes.

### Reuse parser actions for argument facts

The generator constructs the existing parsers and walks their `argparse` actions to obtain positional/optional names, required status, arity, choices, defaults, metavars, and help text. For `UpdateDB.py`, it resolves the action chain for each registered leaf command. Parser construction only is allowed; handlers are never dispatched.

This avoids a parallel argument schema. Serializing `--help` output verbatim was rejected because it is harder to organize into stable Markdown and does not carry enough structured information for consistency checks.

### Supplement parser data with curated operational metadata

Parser actions cannot express important facts such as database mutation, artifact rewriting, provider access, dry-run semantics, environment-variable provenance, or preferred examples. Each descriptor therefore carries concise curated fields for purpose, effects, safeguards, environment-default annotations, and examples. Validation requires relevant fields based on command classification.

This is intentional duplication only for semantics absent from `argparse`; argument names and shapes remain parser-derived.

### Keep aliases explicit and separate

Compatibility aliases remain runtime behavior in `UpdateDB.py`, while registry alias records map each legacy invocation to a canonical command identity. Rendering places them in a deprecated appendix and excludes them from the primary navigation and examples.

### Generate deterministic Markdown and test it as an artifact

The renderer uses a fixed command ordering from the registry, stable argument ordering from parser actions, normalized line endings, and no timestamps or machine-specific paths. A generation CLI writes `docs/commands.md`; its pure render function returns text for tests. A freshness test compares that text with the committed file and reports the regeneration command on mismatch.

README files link to the committed output rather than invoking generation during documentation viewing.

### Enforce completeness against maintained runtime surfaces

Validation compares registry leaf identities with the public `UpdateDB.py` command modules and with an explicit set of supported standalone entry points. Adding a public update module to its command group or adding a supported standalone entry point requires a matching descriptor. The convention is documented next to the registry and exercised by tests.

This makes automatic registration precise: newly added commands enter the catalog through the same maintained registration boundary, and bypassing that boundary produces a test failure. Broad source scanning was rejected as both noisy and semantically unreliable.

## Risks / Trade-offs

- [Curated behavior metadata can become stale even when argument data is current] → Require metadata fields, keep them concise, and test representative safety statements and command identities.
- [Walking private or version-sensitive `argparse` structures could be brittle] → Limit inspection to documented parser/action attributes and isolate traversal behind focused helper functions with parser-shape tests.
- [Importing command modules could gain side effects later] → Keep generation limited to parser construction and add a test that generation succeeds without database or network dependencies.
- [A contributor may create a new standalone script but not declare it supported] → Document that support begins at registry inclusion; validate the explicitly maintained standalone entry-point list rather than guessing from files.
- [Generated Markdown is less convenient for manual edits] → Add a generated-file notice and keep all editable prose in registry metadata or surrounding topic guides.

## Migration Plan

1. Add the registry, descriptors for all current supported commands, and deprecated alias mappings without changing dispatch.
2. Add parser-introspection, validation, and deterministic rendering utilities.
3. Generate and commit `docs/commands.md`, then add README navigation links.
4. Add registry completeness, parser alignment, side-effect-free generation, and freshness tests.
5. Run the Python test suite and OpenSpec validation. Rollback consists of removing the new registry/generator/catalog/tests and README links; runtime command dispatch remains unchanged throughout.
