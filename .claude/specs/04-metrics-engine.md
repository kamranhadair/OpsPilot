---
status: verified
step: 04
title: Metrics Engine
owner: analytics-engineer
depends_on: [03]
---

# Spec 04 — Metrics Engine

## Overview

Build the deterministic analytics layer that converts ticket data into authoritative operational metric snapshots with baselines and provenance.

## Business Goal

Give OpsPilot a trustworthy source of operational facts before any model is involved.

## Depends On

- Spec 03 — Synthetic Data Generator

## Scope

Implement a central metric registry and computation engine for:

- `ticket_volume`
- `open_backlog`
- `p1_ticket_volume`
- `first_response_minutes`
- `resolution_minutes`
- `sla_breach_rate`
- `escalation_rate`
- `negative_sentiment_rate`

Support overall metrics and filtered/dimensional metric snapshots needed by later contributor analysis.

## Out of Scope

- anomaly classification;
- contributor ranking;
- LLM narration;
- frontend charts.

## Metric Window Contract

Default demo analysis:

- current window: the 24 hours ending at the requested `window_end`;
- baseline: the seven complete preceding 24-hour windows immediately before the current window.

For count/average metrics, baseline value is the mean equivalent-window value across the seven baseline days. For rates, baseline value is the rate across the appropriate baseline population, using numerator/denominator semantics documented by the metric definition.

The engine must not include the current window in its own baseline.

## Metric Definitions

Each metric definition must declare at least:

- key;
- display name;
- unit (`count`, `minutes`, `percent`);
- aggregation type;
- numerator/denominator when applicable;
- supported dimensions;
- direction where an increase is operationally worse/better;
- minimum sample size if required.

Supported dimensions for V1:

- `category`
- `product`
- `region`
- `customer_tier`
- `support_team`

## Provenance

Every `metric_snapshots` row must include provenance that allows a reviewer to understand:

- source table/entity;
- metric definition version/key;
- current and baseline windows;
- filters/dimensions;
- row/sample counts;
- computation timestamp.

Do not store an opaque natural-language explanation as the only provenance.

## Change Calculation

For non-zero baseline:

`change_pct = ((current - baseline) / abs(baseline)) * 100`

When baseline is zero:

- current zero -> `change_pct = 0`;
- current non-zero -> `change_pct = null` and provenance includes `baseline_zero: true`.

Never return infinity.

For rate metrics also expose percentage-point difference through response schemas even if it is not a dedicated database column.

## API Changes

### `POST /api/metrics/compute`

Input includes optional `window_end` and optional requested dimension filters. Computes/persists an idempotent set of metric snapshots for that exact analysis signature.

### `GET /api/metrics/overview`

Returns latest/current overview snapshots for the eight metric keys.

### `GET /api/metrics/{metric_key}`

Returns time-series snapshots with validated date/window filters.

## Architecture

Create:

- metric registry;
- computation query layer;
- metrics service;
- repository persistence;
- Pydantic API schemas.

Do not duplicate metric formulas between SQL and frontend code.

## Backend Files

Suggested structure:

- `backend/app/services/metrics/definitions.py`
- `backend/app/services/metrics/engine.py`
- `backend/app/services/metrics/provenance.py`
- `backend/app/repositories/metric_repository.py`
- `backend/app/schemas/metrics.py`
- `backend/app/api/routes/metrics.py`
- `backend/tests/metrics/*`

## New Dependencies

No new dependency is required. SQLAlchemy/SQL/Python are sufficient.

## Implementation Rules

- All authoritative math is backend code/SQL.
- Persist snapshots only after a computation succeeds completely for that item.
- Repeating the same computation signature must not create uncontrolled duplicates; use a deterministic uniqueness strategy or explicit replacement policy.
- Round only for presentation; preserve adequate precision in storage.
- Median/percentiles are out of scope unless required to implement the listed metrics.

## Error and Edge Cases

- empty current window;
- empty baseline;
- baseline zero;
- insufficient samples for latency/rate metrics;
- invalid metric key or dimension;
- `window_end` outside available data.

## Testing Requirements

- unit tests for each metric formula;
- known-fixture tests comparing engine output against directly computed expected values;
- baseline exclusion test;
- zero-baseline behavior;
- rate numerator/denominator correctness;
- idempotent snapshot computation;
- API validation tests.

## Definition of Done

- [ ] All eight metrics exist in one central registry.
- [ ] Current and seven-day baseline values are computed correctly.
- [ ] Metric evidence IDs use `MTR-` prefix.
- [ ] Provenance includes windows, filters, and sample size.
- [ ] Zero-baseline behavior never yields infinity/NaN.
- [ ] Metric endpoints return typed schemas.
- [ ] No frontend or LLM code calculates these authoritative metrics.
- [ ] Metrics tests pass.
