---
status: verified
step: 06
title: Contributor Analysis
owner: analytics-engineer
depends_on: [05]
---

# Spec 06 — Contributor Analysis

## Overview

Explain where an anomaly is concentrated by computing ranked segment contributions across known operational dimensions. This is deterministic attribution of observed delta, not causal inference.

## Business Goal

Move from "Billing volume increased" to a defensible statement such as "most excess Billing volume is concentrated in EMEA Enterprise accounts."

## Depends On

- Spec 05 — Anomaly Detection

## Scope

For each eligible anomaly, compute contributor candidates across:

- region;
- customer tier;
- category;
- product;
- support team;
- selected combinations, especially `region + customer_tier` for the canonical demo.

Persist the top contributors with `SEG-` evidence IDs.

## Out of Scope

- causal root-cause analysis;
- LLM-generated contributor rankings;
- arbitrary high-cardinality customer-level explanations in V1.

## Contribution Formulas

### Count metrics

For each segment:

`delta = current_segment_count - normalized_baseline_segment_count`

Only positive deltas participate in a positive-spike contribution denominator.

`contribution_pct = positive_segment_delta / sum(all_positive_segment_deltas) * 100`

### Rate metrics

For a rate such as SLA breach rate, compute excess events rather than simply comparing percentages:

`expected_current_events = current_segment_denominator * baseline_segment_rate`

`excess_events = actual_current_events - expected_current_events`

Positive excess events form the contribution denominator.

Document numerator, denominator, and formula in provenance.

## Ranking Rules

- rank descending by positive contribution;
- store top 5 per dimension family by default;
- suppress/flag segments that fail minimum sample sizes;
- percentages may not sum to exactly 100 after top-N truncation; API should expose `other_contribution_pct` where useful.

## API Changes

### `POST /api/anomalies/{evidence_id}/contributors/compute`

Computes/persists contributor analysis idempotently.

### `GET /api/anomalies/{evidence_id}/contributors`

Returns ranked contributor groups with provenance.

## Architecture

Suggested files:

- `backend/app/services/contributors/engine.py`
- `backend/app/services/contributors/formulas.py`
- `backend/app/repositories/contributor_repository.py`
- `backend/app/schemas/contributors.py`
- contributor route additions

## Database Changes

Use `anomaly_contributors` from Spec 02. Add indexes/uniqueness only if required for idempotent dimension/rank storage.

## New Dependencies

No new dependency required.

## Implementation Rules

- Use the same current/baseline windows as the anomaly's metric evidence.
- Contributor statements mean "share of observed excess/change," not "cause."
- Do not silently mix incompatible dimensions or baseline windows.
- Do not generate contributor facts with the LLM.
- Persist sufficient provenance to recompute the result.

## Error and Edge Cases

- no positive contributors;
- baseline segment missing;
- new segment appears only in current window;
- rate segment has zero denominator;
- top contributor is based on too few records;
- anomaly metric does not support segmentation.

## Testing Requirements

- count contribution arithmetic;
- rate excess-event arithmetic;
- top-N ranking;
- new-segment behavior;
- minimum-sample suppression;
- canonical demo verifies EMEA Enterprise is a primary/top contributor to the planted Billing spike.

## Definition of Done

- [ ] Eligible anomalies can compute contributors across documented dimensions.
- [ ] Count and rate formulas are tested separately.
- [ ] Contributor results use `SEG-` evidence IDs.
- [ ] Provenance stores formula/window/sample information.
- [ ] Canonical Billing anomaly surfaces EMEA Enterprise prominently.
- [ ] No contributor output uses causal language.
- [ ] Contributor tests pass.
