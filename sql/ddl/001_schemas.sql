-- Layered schemas. Permissions follow layers (see 900_roles_and_grants.sql).
--   raw       append-only source payloads (public APIs) — never updated in place
--   synthetic seeded, generated operational data — kept apart from real data
--   staging   typed, deduplicated views/tables built by dbt
--   core      star schema (dimensions + facts) built by dbt
--   mart      KPI and dashboard/agent-ready aggregates built by dbt
--   ops       pipeline runs, watermarks, data quality, lineage, audit

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS synthetic;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()
