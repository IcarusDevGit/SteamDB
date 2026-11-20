## 1. Repair Core

- [x] 1.1 Add the game-tag repair module with null/empty candidate selection, deterministic app-ID ordering, optional `--appid` and `--limit` bounds, and `empty-tags` default targeting; verify query and target behavior with focused unit tests.
- [x] 1.2 Implement asynchronous Steam HTML discovery using the existing client, catalog snapshot, exception aliases, and tag resolver; verify tests cover successful, duplicate, partially unresolved, wholly unresolved, unavailable, and per-candidate failure outcomes.
- [x] 1.3 Implement atomic guarded persistence that updates only still-empty tag collections and reports affected row counts and progress; verify commit, rollback, concurrent-population, empty-update, and applied-count tests pass.

## 2. Command Integration

- [x] 2.1 Register `repair game-tags` with optional `--appid`, `--limit`, and `--apply`, allowing unbounded authorized application; verify parser and dry-run/apply orchestration tests pass.
- [x] 2.2 Add authoritative command-catalog metadata for the repair and regenerate `docs/commands.md`; verify registry completeness and catalog freshness tests pass.

## 3. End-to-End Verification

- [x] 3.1 Extend the disposable PostgreSQL integration scenario to prove default repair coverage, optional narrowing, resolved-subset persistence, preservation of populated/concurrently changed rows, and no invented tag records; verify the disposable database test passes.
- [x] 3.2 Run the full Python automated test suite and the strict OpenSpec validation for `repair-games-tags`, resolving any regressions before marking the change complete.
