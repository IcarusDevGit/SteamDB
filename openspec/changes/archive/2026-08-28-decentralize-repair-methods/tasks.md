## 1. Characterize Existing Repair Persistence

- [x] 1.1 Add focused tests for rating and price candidate SQL, target filtering, limits, guarded updates, affected-row counts, commit, rollback, and connection closure; verify the tests describe current observable repair behavior before relocation.
- [x] 1.2 Add focused tests for weekly-stat update variants, affected-row counts, atomic rollback, and connection closure; verify all field-selection paths are covered before relocation.

## 2. Decentralize Existing Repair Methods

- [x] 2.1 Move rating candidate selection and transactional updates into `ratings.py` using an injectable connection factory that defaults to `db.get_connection`; verify rating dry-run, bounded apply, mixed outcomes, progress, and SQL tests pass.
- [x] 2.2 Move price candidate selection and transactional updates into `prices.py` using the same connection-factory pattern; verify price dry-run, bounded apply, fallback discovery, mixed outcomes, progress, and SQL tests pass.
- [x] 2.3 Move weekly-stat transactional updates into `weekly_stats.py` using the same connection-factory pattern; verify all/individual field modes, progress, affected counts, and rollback tests pass.
- [x] 2.4 Remove repair-specific candidate and mutation helpers from `db.py` while retaining connection setup and main-workflow database behavior; verify repository searches find no repair-module delegation to removed `db.py` methods and existing main workflow tests pass.

## 3. Integration and Documentation

- [x] 3.1 Extend the disposable PostgreSQL integration scenario to exercise rating, price, and weekly-stat repairs through their module-owned persistence functions; verify all updates remain targeted and transactional.
- [x] 3.2 Update database repair contributor documentation to state that repair modules own operation-specific SQL while `db.py` retains connection and main-workflow behavior; verify documentation contains no instruction to add repair methods to `db.py`.

## 4. Final Verification

- [x] 4.1 Run focused repair, progress, main-workflow, and disposable-database tests and verify relocation preserves command behavior, output counts, transactional guarantees, and the validated CSV application contract.
- [x] 4.2 Run the complete active Python test suite and verify all tests pass without changes to `Python_legacy/`.
- [x] 4.3 Run strict OpenSpec validation for `decentralize-repair-methods` and verify every remaining planning artifact and delta specification is valid.
