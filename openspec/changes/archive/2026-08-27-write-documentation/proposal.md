## Why

The active SteamDB workflow lacks a coherent repository-level documentation entry point, making setup, operation, and maintenance harder to understand than necessary. Existing notes are fragmented and sometimes mix the active implementation with obsolete legacy instructions.

## What Changes

- Add a repository-level README that explains the project's purpose, active workflow, prerequisites, quick start, and documentation map.
- Add focused documentation for architecture, configuration, extraction, validation, reviewed database updates, tag resolution, testing, and troubleshooting.
- Document the active `Python/` implementation and its supported commands using evidence from the current code and OpenSpec requirements.
- Explicitly exclude `Python_legacy/`, legacy-only commands, comparison utilities, generated artifacts, and obsolete prompt documents from the documented project surface.
- Replace or reconcile active documentation that is duplicated, fragmented, or misleading.
- Ensure examples do not expose credentials and clearly distinguish read-only operations, dry runs, approval gates, and database mutations.

## Capabilities

### New Capabilities

None. This is a documentation-only change and opts out of specification deltas.

### Modified Capabilities

None. No externally observable workflow requirements change.

## Impact

The change affects Markdown documentation at the repository root and in a dedicated documentation directory, plus existing active documentation where consolidation is appropriate. Application code, database behavior, command compatibility, dependencies, generated data, `Python_legacy/`, and `comparison/` are not changed.
