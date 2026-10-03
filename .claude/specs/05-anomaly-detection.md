---
status: implemented
step: 05
title: Anomaly Detection
owner: analytics-engineer
depends_on: [04]
---

# Spec 05 — Anomaly Detection

## Overview

Build deterministic anomaly detection over computed metric snapshots. V1 uses explainable threshold rules plus statistical deviation when sufficient history exists. The model does not decide whether a metric is anomalous or how severe the anomaly is.

## Business Goal

Surface operational changes that deserve attention while keeping the detection logic understandable in an interview/demo.

## Depends On

- Spec 04 — Metrics Engine

## Scope

- anomaly rule registry;
- percentage-change / percentage-point threshold rules;
- optional z-score support when enough daily history exists;
- deterministic severity;
- anomaly persistence;
- anomaly list/detail API;
- tests against the planted Billing scenario.

## Out of Scope

- contributor analysis;
- AI explanation;
- machine-learned anomaly models;
- CUSUM/change-point detection in V1.

## Detection Rules

Keep thresholds centralized in code/config. Initial guidance:

- count metrics: medium at >=30% adverse change, high at >=50%;
- SLA breach rate: medium at >=3 percentage points adverse change, high at >=5 points;
- escalation rate: medium/high thresholds defined explicitly in registry;
- negative sentiment rate: explicit percentage-point thresholds;
- P1 ticket volume may escalate severity using absolute-count safeguards because small baselines can exaggerate percentages.

Exact thresholds must be documented in the registry and tests. Do not hide them in route handlers.

## Z-score

When at least seven comparable historical windows exist, the detector may calculate a z-score against historical daily values. Z-score is supporting evidence, not an LLM judgment.

If standard deviation is zero, do not divide by zero; treat z-score as unavailable.

## Severity

Severity is deterministic and must come from rules such as:

- `low`
- `medium`
- `high`
- `critical`

`critical` should require a defined business condition (for example a P1/SLA policy threshold), not merely a very large percentage on a tiny sample.

## API Changes

### `POST /api/anomalies/detect`

Runs detection for a supplied/latest analysis window using persisted or freshly requested metric snapshots. Re-running the same analysis must be idempotent.

### `GET /api/anomalies`

Filters:

- severity;
- status;
- metric key;
- date range.

### `GET /api/anomalies/{evidence_id}`

Returns anomaly, supporting metric snapshot, detector metadata, and threshold explanation.

## Architecture

Suggested files:

- `backend/app/services/anomalies/rules.py`
- `backend/app/services/anomalies/detector.py`
- `backend/app/repositories/anomaly_repository.py`
- `backend/app/schemas/anomalies.py`
- `backend/app/api/routes/anomalies.py`

## Database Changes

No new table beyond Spec 02. Add a uniqueness constraint/index migration only if needed to enforce idempotency for an analysis signature.

## New Dependencies

No new runtime dependency. Standard Python math/statistics is sufficient.

## Implementation Rules

- Never ask the LLM to classify severity.
- Every anomaly references a metric snapshot.
- Persist detector key, threshold metadata, and score so the result is explainable.
- Small-sample guards are mandatory for rate/rare-event metrics.
- Improvement should not automatically be flagged as an adverse anomaly unless a metric definition explicitly says both directions matter.

## Error and Edge Cases

- missing baseline;
- zero standard deviation;
- tiny sample sizes;
- percentage explosion from baseline close to zero;
- duplicate detection run;
- metric not configured for anomaly detection.

## Testing Requirements

- threshold boundary tests;
- percentage-point rule tests;
- small-sample tests;
- zero-standard-deviation test;
- severity determinism test;
- planted Billing anomaly is detected as high (or higher if a documented critical rule applies);
- normal non-Billing queues do not all become high/critical anomalies.

## Definition of Done

- [ ] Central anomaly rule registry exists.
- [ ] Severity is computed only in deterministic code.
- [ ] Planted Billing anomaly is detected.
- [ ] Detection output explains the triggering rule/threshold.
- [ ] `ANOM-` evidence IDs are persisted.
- [ ] Detection is idempotent for the same analysis signature.
- [ ] List/detail APIs work with typed schemas.
- [ ] Anomaly tests pass.
