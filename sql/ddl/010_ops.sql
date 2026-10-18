-- Operational metadata: every pipeline action leaves a row here.

-- One row per connector execution (per source, per run).
CREATE TABLE IF NOT EXISTS ops.ingestion_run (
    ingestion_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID        NOT NULL,              -- the daily pipeline run this belongs to
    source           TEXT        NOT NULL,              -- 'fred' | 'census' | 'bls' | 'synthetic'
    series_id        TEXT,                              -- NULL for whole-source runs
    status           TEXT        NOT NULL
                     CHECK (status IN ('running', 'loaded', 'no_new_release', 'failed')),
    rows_fetched     INT         NOT NULL DEFAULT 0 CHECK (rows_fetched >= 0),
    rows_inserted    INT         NOT NULL DEFAULT 0 CHECK (rows_inserted >= 0),
    source_last_updated TIMESTAMPTZ,                    -- publisher's own "last updated" stamp
    error_message    TEXT,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_ingestion_run_source
    ON ops.ingestion_run (source, series_id, started_at DESC);

-- Latest publisher timestamp we have fully loaded, per series.
-- Publication-aware ingestion compares the API's last_updated with this value.
CREATE TABLE IF NOT EXISTS ops.source_watermark (
    source              TEXT        NOT NULL,
    series_id           TEXT        NOT NULL,
    last_updated        TIMESTAMPTZ NOT NULL,
    last_observation_date DATE,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source, series_id)
);

-- One row per data quality check result.
CREATE TABLE IF NOT EXISTS ops.dq_result (
    dq_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID        NOT NULL,
    table_name   TEXT        NOT NULL,
    check_name   TEXT        NOT NULL,
    severity     TEXT        NOT NULL CHECK (severity IN ('critical', 'warning')),
    status       TEXT        NOT NULL CHECK (status IN ('pass', 'warn', 'fail')),
    failing_rows BIGINT      NOT NULL DEFAULT 0,
    details      JSONB,
    checked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Run-level lineage: which source fed which table in which run.
CREATE TABLE IF NOT EXISTS ops.lineage_edge (
    run_id       UUID        NOT NULL,
    from_node    TEXT        NOT NULL,   -- e.g. 'fred:RSNSR'
    to_node      TEXT        NOT NULL,   -- e.g. 'raw.market_observation'
    rows_moved   BIGINT      NOT NULL DEFAULT 0,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, from_node, to_node)
);

-- Append-only audit trail for consequential actions (approvals, config changes).
CREATE TABLE IF NOT EXISTS ops.audit_log (
    audit_id    BIGSERIAL PRIMARY KEY,
    actor       TEXT        NOT NULL,
    action      TEXT        NOT NULL,
    entity      TEXT        NOT NULL,
    entity_id   TEXT,
    details     JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
