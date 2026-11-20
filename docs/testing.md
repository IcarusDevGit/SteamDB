# Testing

## Unit tests

Run the active suite from the repository root:

```powershell
python -m unittest discover -s Python\Tests -t Python -p "test_*.py" -v
```

The suite covers pipeline orchestration, provider scheduling, parsing and tag resolution, path isolation, CSV serialization and application guards, chart validation, repair behavior, progress reporting, and source-tree isolation. Tests use fixtures and dependency injection; they should not require live providers or mutate the configured database.

Fixtures live under [`Python/Tests/fixtures/`](../Python/Tests/fixtures/). Keep reusable static inputs there rather than under runtime `helpers/` output directories.

## Disposable PostgreSQL integration test

[`Python/Tests/integration_disposable_db.py`](../Python/Tests/integration_disposable_db.py) exercises real PostgreSQL behavior in a temporary schema. It refuses to run unless:

- `ALLOW_DISPOSABLE_DB_TEST=1`; and
- either `DATABASE_URL` is available or `PGHOST`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD` are all set.

Run only against a database account allowed to create and drop a temporary schema:

```powershell
$env:ALLOW_DISPOSABLE_DB_TEST = "1"
python Python\Tests\integration_disposable_db.py
```

The script changes its search path to a uniquely named schema and cleans it up. The opt-in flag is a safety interlock, not a substitute for checking the target connection.

## Documentation-only regression check

Documentation changes should not alter runtime behavior. After editing docs:

1. run the unit suite;
2. verify relative links and referenced paths;
3. compare examples with active parser definitions;
4. inspect `git diff` and `git status` for unintended generated files or secrets.
