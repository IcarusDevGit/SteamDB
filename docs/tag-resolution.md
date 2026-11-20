# Tag resolution

Extraction leaves tag names that cannot be mapped safely in the CSV's `unresolved_tags` column. These names block database application. The resolver proposes or applies mappings to the reviewed artifact without updating PostgreSQL.

## Dry run

Run the canonical command without `--apply` to inspect proposals:

```powershell
python Python\UpdateDB.py resolve tags helpers\CSV\steam_top_100_2026-08-04_<timestamp>.csv
```

Resolution is case-insensitive after trimming and uses this precedence:

1. existing PostgreSQL tag names;
2. configured exception mappings;
3. one Steam tag-list response per invocation;
4. explicit operator mappings.

A dry run does not change the CSV, validation report, exception file, or database.

## Explicit mappings

Supply repeatable `NAME=ID` mappings:

```powershell
python Python\UpdateDB.py resolve tags helpers\CSV\weekly.csv --map "Dystopian=1001" --map "Automation=255534"
```

Identifiers must be positive. The resolver rejects malformed, ambiguous, or catalog-conflicting mappings before changing artifacts.

## Apply mappings

```powershell
python Python\UpdateDB.py resolve tags helpers\CSV\weekly.csv --map "Dystopian=1001" --apply
```

Apply mode requires an existing passing sidecar whose week and digest match the original CSV. It then:

1. aligns the affected `tags`, `tag_ids`, and `unresolved_tags` fields;
2. preserves unrelated CSV fields;
3. stores used explicit exception mappings;
4. replaces changed files atomically;
5. revalidates the changed CSV and creates fresh digest-bound evidence.

If some names remain unresolved, successfully mapped names are retained but the command exits unsuccessfully and database application remains blocked. A validation mismatch or provider error also leaves the result ineligible.

Tag resolution never inserts tags, changes game records, or writes weekly rows in PostgreSQL. Those mutations remain behind the separately approved CSV application command.
