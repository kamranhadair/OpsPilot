---
status: planned
step: 07
title: Operations Dashboard
owner: frontend-engineer
depends_on: [06]
---

# Spec 07 — Operations Dashboard

## Overview

Build the first production-like user experience: an operations overview, anomaly explorer, and anomaly drilldown backed entirely by deterministic analytics completed in Specs 04–06.

## Business Goal

Let a support operations manager understand current health and investigate a detected anomaly before AI narration is introduced.

## Depends On

- Spec 06 — Contributor Analysis

## Scope

Frontend routes:

- `/` — Operations Overview
- `/anomalies` — Anomaly Explorer
- `/anomalies/:evidenceId` — Anomaly Drilldown

Backend dashboard aggregation endpoint(s) as needed to avoid frontend N+1 calls.

## Out of Scope

- AI brief UI;
- evidence provenance drawer beyond basic evidence IDs;
- action approval;
- evaluation/system pages.

## User Flow

1. User opens dashboard.
2. Sees current metric cards with baseline comparisons.
3. Sees active anomalies ranked by severity/time.
4. Opens the Billing anomaly.
5. Sees current vs baseline metric values and detector explanation.
6. Sees contributor breakdown showing where the excess is concentrated.

## Dashboard Content

Metric cards should include at least:

- ticket volume;
- open backlog;
- SLA breach rate;
- escalations or escalation rate.

Also provide at least two visualizations, for example:

- ticket volume trend;
- SLA breach rate trend.

Anomaly list rows/cards include:

- severity;
- metric display name;
- current vs baseline change;
- detected time;
- primary context/filters.

## API Changes

Recommended:

### `GET /api/dashboard/overview`

Returns the latest overview metric cards, short metric trends, and active anomaly summary in one typed response.

Existing anomaly detail/contributor endpoints remain authoritative for drilldown.

## Frontend Architecture

Suggested feature folders:

- `src/features/dashboard/`
- `src/features/anomalies/`
- `src/components/layout/`
- `src/api/`

Use React Router for routes if not already installed.

## New Dependencies

- `recharts`
- `react-router-dom` if not already installed

Do not add a state-management framework unless clearly necessary. React query/caching libraries are optional only if justified; a small typed client + hooks is sufficient for V1.

## Implementation Rules

- Frontend receives already-computed values and severity.
- Frontend may format percent/minute/count values but not recompute business metrics.
- Every screen needs loading, error, empty, and success states.
- Use accessible labels and chart legends/tooltips.
- Evidence IDs should be visible where useful even before provenance drawer exists.
- Do not display fake placeholders when API data is absent.

## Visual Direction

Professional operations UI, not a chatbot. Prioritize dense but readable information hierarchy:

- top summary cards;
- trends;
- active anomalies;
- anomaly drilldown with contributors.

Avoid decorative AI gradients/robot imagery that makes the product look like a generic AI demo.

## Error and Edge Cases

- no metrics computed yet;
- no active anomalies;
- anomaly not found;
- contributor analysis unavailable;
- backend network failure.

## Testing Requirements

- overview renders API values;
- loading/error/empty states;
- anomaly click navigates to detail;
- detail renders severity and contributor data from API;
- no component computes anomaly severity or SLA rate;
- accessibility-oriented queries in tests where practical.

## Definition of Done

- [ ] Three routes above are implemented.
- [ ] Overview displays real backend metric snapshots.
- [ ] Trend charts use real API series.
- [ ] Active anomaly list is usable.
- [ ] Canonical Billing anomaly has a clear drilldown.
- [ ] Contributor breakdown visibly surfaces EMEA Enterprise.
- [ ] Loading/error/empty states exist.
- [ ] Frontend tests, lint, and type-check pass.
