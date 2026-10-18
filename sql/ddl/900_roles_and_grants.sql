-- Least-privilege roles. Passwords are set by the migration runner from environment
-- variables (never stored in SQL files).
--   sciq_ingest  pipeline: writes raw/synthetic/staging/core/mart/ops
--   sciq_mcp     MCP servers: read core/mart, insert-only into selected ops tables (Phase 6)
--   sciq_app     Streamlit / Power BI: read-only on core, mart, ops

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sciq_ingest') THEN
        CREATE ROLE sciq_ingest LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sciq_mcp') THEN
        CREATE ROLE sciq_mcp LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sciq_app') THEN
        CREATE ROLE sciq_app LOGIN;
    END IF;
END
$$;

-- ingest: full DML on pipeline schemas, plus CREATE so dbt can build models.
GRANT USAGE, CREATE ON SCHEMA raw, synthetic, staging, core, mart, ops TO sciq_ingest;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA raw, synthetic, staging, core, mart, ops TO sciq_ingest;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ops TO sciq_ingest;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, synthetic, staging, core, mart, ops
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sciq_ingest;

-- raw is append-only in spirit: revoke UPDATE/DELETE so history cannot be rewritten.
REVOKE UPDATE, DELETE ON ALL TABLES IN SCHEMA raw FROM sciq_ingest;
-- Exception: series metadata is a current-state snapshot, refreshed on each new release.
GRANT UPDATE ON raw.market_series TO sciq_ingest;

-- mcp + app: read-only on modelled layers. No access to raw or synthetic source tables.
GRANT USAGE ON SCHEMA core, mart, ops TO sciq_mcp, sciq_app;
GRANT SELECT ON ALL TABLES IN SCHEMA core, mart, ops TO sciq_mcp, sciq_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA core, mart, ops GRANT SELECT ON TABLES TO sciq_mcp, sciq_app;
-- dbt runs as sciq_ingest, so tables it creates need their own default grants.
ALTER DEFAULT PRIVILEGES FOR ROLE sciq_ingest IN SCHEMA core, mart, ops
    GRANT SELECT ON TABLES TO sciq_mcp, sciq_app;

-- Guardrail: these roles may never run long queries.
ALTER ROLE sciq_mcp SET statement_timeout = '15s';
ALTER ROLE sciq_app SET statement_timeout = '30s';
