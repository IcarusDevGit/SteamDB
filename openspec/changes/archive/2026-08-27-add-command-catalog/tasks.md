## 1. Command Registry

- [x] 1.1 Add the shared command and deprecated-alias descriptor model, including validation for identities, parser sources, operational metadata, safeguards, environment defaults, examples, and canonical replacements; verify focused registry validation tests pass.
- [x] 1.2 Register the extraction, standalone validation, apply CSV, resolve tags, ratings repair, prices repair, and weekly-stats repair commands without changing their runtime invocations; verify the inventory test reports exactly the supported command set.
- [x] 1.3 Register every hidden `UpdateDB.py` compatibility alias with its canonical replacement and verify alias validation rejects missing or invalid replacement identities.

## 2. Parser Introspection and Catalog Rendering

- [x] 2.1 Implement side-effect-free construction and traversal of standalone and nested `argparse` parsers, extracting argument names, position, required status, arity, choices, defaults, metavars, help, and repeatability; verify parser-shape tests cover every current command.
- [x] 2.2 Add registry-to-runtime completeness checks for public update command groups and maintained standalone entry points; verify tests fail with an identified command when registration is missing, duplicated, or cannot expose parser metadata.
- [x] 2.3 Implement deterministic Markdown rendering for supported commands and a separate deprecated-alias appendix, including effects, safeguards, environment-derived defaults, and examples; verify snapshot/content tests cover all required catalog fields and produce identical output across repeated renders.
- [x] 2.4 Add a command that writes the rendered catalog to `docs/commands.md` with normalized line endings and a generated-file notice; verify running it twice produces no second file change.

## 3. Documentation Integration

- [x] 3.1 Generate and commit `docs/commands.md`, then verify it documents all seven supported command forms and every applicable argument while keeping compatibility aliases out of the primary catalog.
- [x] 3.2 Add command-catalog links to `README.md` and `Python/README.md`, and document the registration and regeneration convention for contributors; verify both links resolve and the documented generation command succeeds.

## 4. Automated Validation

- [x] 4.1 Add a freshness test comparing the committed catalog with an in-memory render and include an actionable regeneration command in failures; verify the test fails after a temporary metadata difference and passes after regeneration.
- [x] 4.2 Verify catalog generation does not dispatch handlers or require database/network access by running the catalog tests with external dependencies unavailable or mocked to fail on use.
- [x] 4.3 Run the complete active Python test suite and `openspec validate add-command-catalog --strict`, and verify all checks pass without changes to existing CLI behavior.
