## Context

See `proposal.md` for motivation and scope. The active tree contains workflow code, database operations, command-line entry points, data models, unit tests, and integration helpers. Some modules already have short module or class docstrings, but coverage and depth are inconsistent, and complex orchestration frequently has no inline explanation.

This change is documentation-only. Comments must remain synchronized with existing behavior and must not alter imports, signatures, control flow, formatting-sensitive data, or observable output.

## Goals / Non-Goals

**Goals:**

- Establish consistent documentation coverage across every non-empty Python module in `Python/`.
- Explain contracts and intent at module, class, function, and method boundaries.
- Make complex workflows easier to trace through selective phase comments.
- Keep tests readable by documenting reusable helpers and non-obvious arrangements rather than narrating ordinary assertions.
- Make behavioral preservation independently verifiable through diff review, compilation, and tests.

**Non-Goals:**

- Refactoring, renaming, reformatting, typing, or otherwise improving implementation code.
- Adding comments to `Python_legacy/`, `comparison/`, generated data, or non-Python files.
- Producing line-by-line commentary or duplicating information evident from names and expressions.
- Changing public documentation, OpenSpec behavior requirements, dependencies, schemas, or runtime behavior.

## Decisions

### Use layered documentation

Each non-empty module receives a module docstring. Classes receive docstrings describing responsibility and, where relevant, owned state, collaborators, and lifecycle. Meaningful functions and methods receive contract-focused docstrings covering inputs, outputs, side effects, significant errors, and processing sequence when those details are not already obvious from the signature.

This layered approach is preferred over inline-only documentation because it gives readers useful context before they enter an implementation. The alternative—adding comments only within function bodies—would leave APIs and object roles unexplained.

### Reserve inline comments for decisions and processing phases

Inline comments will identify meaningful phases or explain reasoning around validation, batching, concurrency, caching, fallback logic, state transitions, atomic file writes, and database transactions. They will be placed immediately before the relevant block and kept concise.

Comments that translate a statement into English will not be added. This avoids visual noise and reduces the likelihood that comments drift away from code behavior.

### Tailor documentation to code role

Production modules receive complete boundary documentation and selective flow comments. Data containers and enums receive concise explanations of their semantic role rather than verbose field-by-field narration. Tests rely on descriptive test names; only helper classes/functions, fixtures, complex setup, and unusual assertions receive additional explanation. Empty package initializers may remain empty because a synthetic comment would add no information.

This role-aware treatment is preferred over enforcing identical comment density in every file.

### Apply and review in dependency-oriented groups

Implementation will proceed through shared models/utilities, extraction and client workflows, validation/database workflows, then tests and integration helpers. The highest-complexity modules receive an additional review for accurate descriptions of concurrency, state, and transactional guarantees.

The final diff must contain documentation-only edits. Compilation and the existing full test suite will verify that documentation placement did not introduce syntax errors or behavior changes.

## Risks / Trade-offs

- [Comments become stale or assert guarantees the code does not provide] → Derive each comment from the adjacent implementation, avoid speculative claims, and review high-complexity workflows against their tests.
- [Excessive comments reduce readability] → Prefer boundary docstrings and block-level intent comments; reject statement-by-statement narration.
- [A documentation edit accidentally changes behavior] → Keep edits documentation-only, inspect the final diff, compile the complete `Python/` tree, and run the full test suite.
- [Uniform coverage creates low-value prose in trivial code] → Allow concise docstrings and leave empty `__init__.py` files untouched; focus detailed prose on complex logic.
- [Test documentation duplicates descriptive test names] → Limit test comments to reusable helpers, complex setup, and non-obvious reasoning.

## Migration Plan

1. Add documentation in dependency-oriented groups, reviewing each group for documentation-only diffs.
2. Compile all Python modules to detect misplaced docstrings or syntax errors.
3. Run the complete test suite and inspect failures for accidental behavioral changes.
4. Review the final diff for excluded paths, redundant narration, and inaccurate guarantees.

Rollback consists of reverting the documentation-only edits; no data or configuration migration is required.
