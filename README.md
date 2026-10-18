# SupplyChainIQ

Autonomous market intelligence, demand forecasting and supply chain decision platform — an
independent portfolio project inspired by public descriptions of AI-driven retail supply chains.

> **Status:** Phase 1–3 (foundations). Built incrementally; each phase is merged only when its
> acceptance tests pass. Results in this README will come only from pipeline output tables.

**Data honesty:** operational data (orders, inventory, suppliers) is **synthetic**, generated
with a fixed seed and stored in the `synthetic` schema. Market data is **real public data**
(FRED, U.S. Census, BLS), stored in `raw` with full revision history. The two are never mixed.

This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of
St. Louis.

## Architecture (target)

Public APIs + synthetic generator → Prefect daily flow → PostgreSQL (`raw → staging → core →
mart`, plus `ops` audit) → deterministic forecasting and inventory math → four read-only MCP
servers → LangGraph agents (LLM only for analysis and writing) → Streamlit / Power BI / daily
report → human approval for any recommended action.

## Quick start (Windows, macOS, Linux)

Prerequisites: Docker Desktop, Python 3.12, [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env              # then set passwords and FRED_API_KEY
docker compose up -d db           # PostgreSQL 16 on localhost:5433
uv sync                           # install dependencies into .venv
uv run python -m supplychainiq.db.migrate                 # schemas, tables, roles
uv run python -m supplychainiq.ingestion.market_loader    # load FRED series (needs key)
uv run pytest                     # unit + integration tests
```

Running the loader twice in a row is safe: the second run records `no_new_release` for each
series and changes no data.

## Repository layout

| Path | Contents |
| --- | --- |
| `docs/` | Business requirements, architecture decisions (ADRs), data source notes, learning notes |
| `sql/ddl/` | Ordered, idempotent DDL applied by `supplychainiq.db.migrate` |
| `src/supplychainiq/` | Python package: config, logging, db, ingestion (more per phase) |
| `tests/unit`, `tests/integration` | Fast tests; tests that need PostgreSQL (auto-skipped if it is down) |

## License

MIT — see [LICENSE](LICENSE).
