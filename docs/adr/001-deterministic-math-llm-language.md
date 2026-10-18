# ADR-001: Deterministic math, LLM for language

*Status: accepted · 2026-10-17*

## Context

The project needs forecasts, KPIs, reorder points and anomaly flags, plus explanations,
investigations and reports. LLM agents can do both, but LLM output is nondeterministic, hard
to test and can invent numbers.

## Decision

- All calculations (ingestion, validation, KPIs, forecasts, inventory math, anomaly flags) are
  plain Python/SQL with unit tests.
- LLMs are used only where judgment or language is needed: market interpretation, root-cause
  investigation (choosing what evidence to pull), report writing, and routing chat questions.
- LLM-written text may only contain numbers that appear in cited tool results; a deterministic
  validator checks this.

## Consequences

- Results are reproducible and testable; CI runs without an LLM (fake model).
- Fewer, cheaper LLM calls.
- Some agents in the brief become deterministic graph nodes rather than LLM agents. This is
  intentional and is explained in interviews as a design choice.
