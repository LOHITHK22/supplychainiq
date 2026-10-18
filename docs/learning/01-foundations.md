# Learning notes 01 — Foundations (tasks 1–6)

Short explanations of the concepts used so far, written to be re-explained in an interview.

## Layered schemas (`raw → staging → core → mart`, plus `ops`)

Each layer has one job and one set of permissions. `raw` keeps exactly what the source said;
`staging` cleans types and duplicates; `core` is the star schema; `mart` holds the numbers people
and agents read. If a KPI looks wrong you can walk back layer by layer to the original payload.

## Least-privilege database roles

Three login roles instead of one superuser:

- `sciq_ingest` writes pipeline tables but **cannot UPDATE or DELETE `raw`** — history is
  protected by the database, not by good intentions (a test proves it).
- `sciq_mcp` and `sciq_app` can only `SELECT` from `core`, `mart`, `ops`, with statement timeouts.

Interview line: "Even if an agent were tricked into asking for something harmful, the
credentials it runs with physically cannot do it."

## Idempotency

Running the same step twice gives the same result. Three mechanisms here:

1. Migrations are recorded in `ops.schema_migration` with a checksum, so each file runs once and
   edited files are rejected.
2. Observations insert with `ON CONFLICT DO NOTHING` on the natural key.
3. The watermark only advances in the same transaction as the data it describes.

## Publication-aware ingestion and vintages

Public statistics are published on a schedule and revised later. The loader asks FRED when a
series was last updated; if that has not changed since our watermark it records
`no_new_release` and downloads nothing. When it has changed, every vintage is appended. See
ADR-002 for why this prevents look-ahead leakage in forecasting.

## Retries with exponential backoff and jitter

Transient failures (HTTP 429, 5xx, network errors) are retried up to 5 times with randomised,
growing waits (`tenacity.wait_random_exponential`). Permanent failures (HTTP 400: bad key,
unknown series) are not retried. One failing series is recorded as `failed` and the others
continue.

## Secrets hygiene

Secrets live in `.env` (git-ignored) and are typed as `SecretStr` so they do not print.
SQLAlchemy engines use `hide_parameters=True` so bound values never appear in error messages
— added after a migration error echoed a password during development (that local password
was rotated).

## Testing pyramid so far

- Unit tests mock HTTP with `respx` (parsing, pagination, retries, error handling).
- Integration tests run the loader against a real PostgreSQL test database with a fake source
  (first load, no new release, revision, crash recovery, failure isolation, permission denial).
