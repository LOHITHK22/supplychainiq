# ADR-002: Store public data as append-only vintages

*Status: accepted · 2026-10-17*

## Context

Government statistics are revised after first publication. If we overwrite values, a model
backtested "as of" March would see numbers that were only published in June — look-ahead
leakage that makes accuracy look better than it would have been.

## Decision

- `raw.market_observation` is keyed by `(source, series_id, obs_date, realtime_start)`.
- Every revision is a new row; the pipeline role has no `UPDATE`/`DELETE` on `raw`.
- `realtime_end` is not stored (it would change when a later revision arrives); staging derives
  it with `LEAD(realtime_start)`.
- A series is downloaded only when the publisher's `last_updated` is newer than
  `ops.source_watermark`; otherwise the run records `no_new_release`.

## Consequences

- Point-in-time ("as known on date D") joins are possible for forecasting features.
- Storage grows with revisions, which is negligible at this scale.
- Loads are idempotent: re-fetching the same release inserts zero rows.
