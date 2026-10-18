-- Real public market data, stored as vintages.
-- A revised value becomes a NEW row (new realtime_start); old rows are never overwritten.
-- That lets forecasts use only what was known on the forecast date (no look-ahead leakage).
-- realtime_end is deliberately NOT stored: it changes when a later revision arrives, which
-- would force an UPDATE. Staging derives it as LEAD(realtime_start) - 1 day.
CREATE TABLE IF NOT EXISTS raw.market_observation (
    source         TEXT          NOT NULL,          -- 'fred' | 'census' | 'bls'
    series_id      TEXT          NOT NULL,
    obs_date       DATE          NOT NULL,          -- period the value describes
    value          NUMERIC(20,6),                   -- NULL when the publisher reports missing ('.')
    realtime_start DATE          NOT NULL,          -- first day this value was the published one
    is_synthetic   BOOLEAN       NOT NULL DEFAULT FALSE CHECK (is_synthetic = FALSE),
    ingestion_run_id UUID        NOT NULL,
    fetched_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (source, series_id, obs_date, realtime_start)
);

-- Series metadata as published (title, units, frequency), one row per series.
CREATE TABLE IF NOT EXISTS raw.market_series (
    source             TEXT        NOT NULL,
    series_id          TEXT        NOT NULL,
    title              TEXT        NOT NULL,
    units              TEXT,
    frequency          TEXT,
    seasonal_adjustment TEXT,
    notes              TEXT,
    source_last_updated TIMESTAMPTZ,
    fetched_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source, series_id)
);
