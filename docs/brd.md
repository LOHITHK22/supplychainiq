# Business Requirements — SupplyChainIQ

*Version 0.1 · 2026-10-17 · Owner: Lohith Kovuri*

## 1. Context

A hypothetical U.S. e-commerce and distribution company runs **5 regional warehouses**
(Northeast, Southeast, Midwest, Southwest, West) and about **1,000 SKUs** across ~10 categories.
All operational data in this project is synthetic; market data is real and public.

## 2. Problem

1. Demand varies by product, season and region.
2. Warehouse inventory is not aligned with demand: some SKUs overstock, others stock out.
3. Supplier lead times fluctuate.
4. Overstock raises holding costs; understock causes lost sales.
5. Analysts join sales, inventory, supplier and market data by hand.
6. Reporting is reactive; management lacks one explanation of risks and actions.

## 3. Decisions the platform supports

| Decision | Who | Frequency | Inputs the platform provides |
| --- | --- | --- | --- |
| Which SKU-warehouses to replenish, and how much | Inventory planner | Daily | Days of supply, reorder point, recommended quantity, forecast reliability |
| Whether to transfer stock between warehouses | Inventory planner | Weekly | Regional forecasts, excess vs. shortage pairs |
| Which suppliers need escalation | Procurement | Weekly | On-time rate, lead-time trend and variability |
| What changed and what to prioritise today | Operations leadership | Daily | Daily brief: KPIs, risks, market changes, recommended actions with evidence |
| Whether a demand change is explainable | Analyst | Ad hoc | Root-cause hypotheses with evidence and uncertainty |

## 4. Personas and access

| Persona | Role in system | Access |
| --- | --- | --- |
| Operations leader | Reads daily brief and Executive page | Read-only |
| Inventory planner | Reviews and approves recommendations | Read + approve/reject |
| Analyst | Asks questions, investigates | Read-only + chat |
| Platform admin | Runs pipeline, manages config | Full |

## 5. Functional requirements (MVP)

- **FR1** Ingest public market series with publication-aware incremental loads; keep all revisions.
- **FR2** Generate a reproducible synthetic operational dataset (5 warehouses, 1,000 SKUs, ≥ 2 years).
- **FR3** Validate data (schema, nulls, duplicates, ranges, freshness) and stop downstream steps on critical failures.
- **FR4** Model data as a star schema; publish KPIs as tested tables.
- **FR5** Forecast SKU × warehouse demand at 7/30/90-day horizons with intervals; evaluate against baselines.
- **FR6** Compute days of supply, safety stock, reorder points and recommended order quantities.
- **FR7** Expose analytics to AI agents only through permissioned MCP tools (no free-form SQL).
- **FR8** Run a daily workflow automatically and produce a sourced daily report and alerts.
- **FR9** Require human approval before any recommendation is marked executed.
- **FR10** Answer natural-language questions with period, source, metrics, method and limitations.

## 6. Non-functional requirements

- Reproducible from a clean clone with Docker and one setup command.
- Idempotent pipeline runs; re-running a day changes nothing.
- No secrets in the repository; least-privilege database roles.
- Every number shown to a user is traceable to a table and run (`run_id`, `query_id`).
- Synthetic and real data are always labelled.

## 7. Out of scope

Real purchasing or payments; streaming ingestion; network optimisation solvers; training
foundation models; multi-tenant SSO; scraping sources without a clear licence.

## 8. KPIs

Defined in the planning document, section J, and implemented as dbt models in Phase 4.
