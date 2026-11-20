## Context

The active implementation lives in `Python/` and already has partial operator guidance in `Python/README.md` plus a module inventory in `Python/PROJECT_STRUCTURE.md`. Root-level notes and prompts include older assumptions, while the OpenSpec specifications contain the authoritative behavioral constraints for extraction, chart validation, tag synchronization, and validated database updates. Documentation must therefore be assembled from current code and specifications rather than treating every existing Markdown file as current.

The repository also contains credentials in local configuration, generated data and reports, binary analysis artifacts, and an intentionally isolated `Python_legacy/` tree. Documentation work must neither expose secrets nor present those materials as part of the supported workflow.

## Goals / Non-Goals

**Goals:**

- Give a new operator a clear route from installation through a safe first extraction.
- Explain the active system structure and the boundaries between extraction, validation, review, tag resolution, and database mutation.
- Make every supported command discoverable with prerequisites, safety semantics, inputs, outputs, and representative examples.
- Establish one repository-level entry point with focused documents that can be maintained independently.
- Ensure documentation claims and examples can be checked against current source, CLI parsers, tests, and OpenSpec requirements.

**Non-Goals:**

- Documenting, refactoring, or deleting `Python_legacy/` or `comparison/`.
- Promoting hidden compatibility aliases as supported primary commands.
- Describing generated datasets, analytical workbooks, prompt history, or implementation archaeology.
- Changing runtime behavior, schemas, dependencies, environment-variable names, or operational safeguards.
- Publishing real connection strings, API keys, or values from `.env.local` and `.neon`.

## Decisions

### Use a layered documentation set

Create a concise root `README.md` as the landing page and place detailed material under `docs/`. The planned documents are architecture, configuration, extraction, validation, database updates, tag resolution, testing, and troubleshooting. This keeps the first-run path readable while avoiding a single oversized manual.

Alternative considered: expand `Python/README.md` into the complete manual. This was rejected because it hides project-level setup below an implementation directory and makes topic ownership less clear.

### Document only the supported active surface

Treat `Python/`, active OpenSpec specifications, and active tests as evidence. Exclude `Python_legacy/`, `comparison/`, prompt files, generated artifacts, and legacy-only instructions. Compatibility aliases may be omitted unless needed to prevent operator confusion; if mentioned, they are clearly labeled compatibility-only and point to the canonical command.

Alternative considered: include a migration guide from every legacy command. This was rejected because the requested documentation is for the current project rather than historical implementations.

### Organize operational documentation around safety boundaries

Describe extraction as read-only, validation as artifact classification, tag resolution as CSV-only mutation, repairs as dry-run by default, and reviewed CSV application as an explicitly approved database mutation requiring passing validation evidence. Command pages will state safety behavior adjacent to examples rather than leaving it in a separate disclaimer.

Alternative considered: organize only by Python module. This was rejected because operators reason in workflows and mutation boundaries, not source-file order. The architecture page will retain the module mapping for maintainers.

### Derive configuration references without revealing values

Enumerate environment-variable names and their meaning from source reads, grouping required credentials separately from optional tuning controls. Use placeholders in examples and never copy local configuration values. Where the repository does not provide a dependency manifest or an unambiguous default, document the observed requirement and flag the gap rather than inventing an installation command.

Alternative considered: use `.env.local` as documentation input. This was rejected because even redacted processing creates unnecessary secret-exposure risk; source-level variable access is sufficient.

### Validate documentation structurally and against executable interfaces

Verify internal links and referenced paths, compare commands and flags with parser definitions or `--help` where executable, and run the existing test suite only as a regression check because documentation changes should not affect behavior. Manually check that exclusions and secret hygiene hold.

Alternative considered: rely on prose review alone. This was rejected because command drift and broken links are mechanically detectable.

## Risks / Trade-offs

- [The active CLI may expose undocumented compatibility aliases] → Document canonical commands and inspect parser registration so examples remain accurate without broadening the supported surface.
- [Environment configuration is distributed across modules] → Build the configuration reference from a repository-wide source search and cross-check tests for required/optional semantics.
- [Existing documents may contradict the new set] → Replace their active guidance with pointers or reconcile relevant text so there is one clear source for each topic.
- [No complete dependency manifest may exist] → Avoid speculative version pins; state verified prerequisites and create a clearly scoped follow-up if dependency management needs its own change.
- [Documentation can become stale] → Keep topic pages close to stable workflow boundaries, link to source modules, and include repeatable verification tasks.

## Migration Plan

1. Inventory supported commands, configuration names, data paths, and safety gates from the active code, tests, and specifications.
2. Write the repository README and focused `docs/` pages.
3. Reconcile `Python/README.md` and `Python/PROJECT_STRUCTURE.md` by retaining useful implementation-local guidance or replacing duplication with links.
4. Validate links, examples, path references, exclusions, and secret hygiene.
5. Review the final diff to confirm only documentation and planning artifacts changed.

Rollback consists of reverting the documentation files; no runtime or data migration is involved.
