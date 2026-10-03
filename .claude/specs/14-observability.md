---
status: planned
step: 14
title: Observability
owner: backend-engineer
depends_on: [13]
---

# Spec 14 — Observability

## Overview

Add production-like observability for model calls, analysis jobs, API failures, and action execution. The goal is inspectability, not adopting a large external monitoring platform.

## Business Goal

Show how the system behaves when calls fail or become slow/expensive and provide enough traces to debug the final demo.

## Depends On

- Spec 13 — Evaluation Framework

## Scope

- structured application logging;
- complete LLM trace capture;
- latency/error metadata for major pipeline stages;
- optional cost estimation driven by configuration;
- system/trace API;
- `/system` frontend page;
- safe redaction rules.

## Out of Scope

- Datadog/Grafana/Prometheus deployment;
- distributed tracing platform;
- production paging/alerting;
- hard-coded provider pricing.

## LLM Trace Requirements

For every model call record:

- operation (`brief_generation`, `action_proposal`, optional eval);
- model name;
- start/end or latency;
- input/output token counts when provider returns them;
- estimated cost only when price configuration is available;
- success/error status;
- safe error code/message;
- related brief/action/evaluation context where available.

Never store API keys or authorization headers.

## Cost Configuration

Provider prices change. Do not hardcode "current" pricing in source as a permanent truth.

Allow optional config such as:

- `OPENAI_INPUT_COST_PER_1M`
- `OPENAI_OUTPUT_COST_PER_1M`

If unset, `estimated_cost_usd = null` and UI shows "not configured."

## Pipeline Timing

Add lightweight timing/log context for:

- metric computation;
- anomaly detection;
- contributor computation;
- evidence assembly;
- brief generation + validation;
- action execution.

These do not all require new database tables; structured logs are acceptable except LLM traces and action executions already have persistence.

## API Changes

### `GET /api/system/health`

More detailed internal/demo health than public basic health, including database + configuration readiness. Never echo secrets.

### `GET /api/system/llm-traces`

Paginated/filterable safe trace metadata.

### `GET /api/system/summary`

Aggregated counts such as calls, errors, average latency, token totals, optional estimated cost for selected period.

## Frontend Changes

Route:

- `/system`

Show:

- service readiness;
- LLM call count/error rate;
- latency summary;
- token/cost summary where available;
- recent trace rows;
- recent action execution failures if any.

## New Dependencies

A lightweight structured logging library may be added if justified (for example `structlog`), otherwise use standard Python logging with structured extras. Do not add a full observability stack.

## Implementation Rules

- Correlation/request IDs where practical.
- Redact secrets and avoid raw ticket bodies.
- Logs must not contain full prompts if those prompts include large evidence payloads; log identifiers/sizes instead.
- Observability failure must not bring down the core request path.
- Pagination on trace list endpoint.

## Error and Edge Cases

- provider returns no token usage;
- cost rates unset;
- trace persistence fails;
- very large evidence bundle;
- repeated model error.

## Testing Requirements

- successful and failed LLM call traces;
- absent token/cost data;
- secret redaction test;
- system summary aggregation;
- system page loading/error states.

## Definition of Done

- [ ] Every LLM operation records safe trace metadata.
- [ ] Token/cost values degrade gracefully when unavailable.
- [ ] Major analysis stages produce structured timing/error logs.
- [ ] System endpoints expose safe operational summaries.
- [ ] `/system` page visualizes recent health/traces.
- [ ] No secret/raw sensitive fixture data appears in trace/log tests.
- [ ] Observability tests pass.
