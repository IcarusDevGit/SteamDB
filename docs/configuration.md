# Configuration

The active Python modules load `.env.local` and then `.env` from the repository root. Existing process variables take precedence. Do not commit either file or place real secrets in documentation.

## External services

| Variable | Required | Purpose / default |
|---|---:|---|
| `STEAM_API_KEY` | Yes | Steam weekly chart and tag-list requests |
| `ITAD_API_KEY` | Yes for price history | IsThereAnyDeal identifier lookup and history |
| `ITAD_COUNTRY` | No | ITAD price country; default `US` |
| `STEAM_CHART_COUNTRY` | No | Weekly chart country; default empty for the global chart |
| `STEAM_STORE_COUNTRY` | No | Steam request/storefront context; default `US` |

Example:

```dotenv
STEAM_API_KEY=<steam-api-key>
ITAD_API_KEY=<itad-api-key>
ITAD_COUNTRY=US
STEAM_CHART_COUNTRY=
STEAM_STORE_COUNTRY=US
```

## PostgreSQL

Use `DATABASE_URL` or individual connection variables. `DATABASE_URL` takes precedence.

| Preferred | Compatibility fallback | Default |
|---|---|---|
| `PGHOST` | `DB_HOST` | `localhost` |
| `PGPORT` | `DB_PORT` | `5432` |
| `PGDATABASE` | `DB_NAME` | `Steam` |
| `PGUSER` | `DB_USER` | `postgres` |
| `PGPASSWORD` | `DB_PASS` | none |
| `PGSSLMODE` | — | driver default |
| `PGCHANNELBINDING` | — | driver default |

Example:

```dotenv
DATABASE_URL=<postgresql-connection-url>
```

## Pipeline controls

| Variable | Default | Meaning |
|---|---:|---|
| `PIPELINE_MAX_ENTRIES` | `100` | Maximum concurrently admitted enrichment records |
| `ITAD_BATCH_SIZE` | `100` | Maximum app identifiers per ITAD lookup batch |
| `ITAD_BATCH_WAIT` | `0.05` | Seconds to wait while collecting an ITAD batch |

The corresponding `main.py` command-line flags override these defaults for one invocation.

## Provider scheduling

Each provider supports `<PREFIX>_INTERVAL`, `<PREFIX>_CONCURRENCY`, `<PREFIX>_QUEUE_SIZE`, and `<PREFIX>_RETRIES`.

| Prefix | Interval | Concurrency | Queue | Retries |
|---|---:|---:|---:|---:|
| `STEAM_WEB` | `1.0` | `1` | `100` | `3` |
| `STEAM_STORE` | `1.0` | `2` | `100` | `3` |
| `ITAD` | `0.3` | `4` | `200` | `3` |

For example, `STEAM_STORE_CONCURRENCY=1` serializes Steam store requests. Intervals are seconds. Concurrency and queue sizes must be positive.

## Disposable integration test

`ALLOW_DISPOSABLE_DB_TEST=1` is required before the real PostgreSQL integration script will run. See [Testing](testing.md); never set it casually against an important database.
