---
status: planned
step: 10
title: Claim Validation and Provenance
owner: ai-engineer
depends_on: [09]
---

# Spec 10 — Claim Validation and Provenance

## Overview

Validate AI brief claims against the exact Evidence Bundle and make every evidence ID inspectable from the UI. A parsed model response is not considered trustworthy until this validation passes.

## Business Goal

Allow a reviewer to click a citation and see the metric/anomaly/segment/event behind it, while preventing briefs with fabricated evidence IDs or prohibited causal assertions from being presented as valid.

## Depends On

- Spec 09 — AI Operations Brief

## Scope

- deterministic evidence-ID validation;
- claim validation state;
- causation guardrail for contextual events;
- brief-level valid/invalid state;
- generic evidence resolver API;
- frontend brief view with clickable evidence chips/drawer.

## Out of Scope

- full semantic entailment scoring by another LLM (Spec 13 evaluation may add optional model-based scoring);
- action proposals;
- real causal inference.

## Validation Rules

A claim is invalid when any of the following is true:

- evidence list is empty for a factual claim;
- an evidence ID is not in the bundle allow-list;
- an evidence ID cannot be resolved in persisted evidence;
- evidence belongs to an incompatible analysis window without explicit disclosure;
- claim uses prohibited causal wording tied to a contextual event.

V1 prohibited event-causation phrases include at least:

- `caused by`
- `due to`
- `resulted from`
- `led to`

Allowed cautious wording includes:

- `coincided with`
- `occurred after`
- `is temporally associated with`
- `warrants investigation`

Do not rely on the prompt alone for this guardrail.

## Brief State

After validation:

- all claims valid -> brief `status = valid`;
- any claim invalid -> brief `status = invalid` and validation errors persisted.

User-facing latest brief endpoints/UI must not label an invalid brief as validated truth.

## Evidence Resolver API

### `GET /api/evidence/{evidence_id}`

Resolve `MTR-`, `ANOM-`, `SEG-`, and `EVT-` evidence to a common typed envelope containing:

- evidence type;
- label;
- core values;
- analysis window;
- dimensions;
- sample size where applicable;
- calculation/detector/contribution metadata;
- provenance;
- contextual disclaimer for events.

Unknown ID -> `404` with stable error code.

## Brief API Changes

`POST /api/briefs/generate` should run validation after persistence (or call a validation service) and return final valid/invalid state.

Add or update frontend route:

- `/briefs/:id`

The brief UI displays claim citations as clickable chips/links. Clicking opens a provenance drawer/modal using the evidence resolver endpoint.

## Architecture

Suggested:

- `backend/app/services/briefs/validator.py`
- `backend/app/services/evidence/resolver.py`
- evidence resolver route
- frontend `features/briefs/`
- frontend provenance drawer component

## Database Changes

Use existing validation fields. No new table required.

## New Dependencies

No new dependency required.

## Implementation Rules

- Never auto-rewrite a fabricated evidence ID into a guessed real ID.
- Validation failure must be visible in logs/API state.
- Evidence drawer uses backend-provided calculation/provenance details; do not reconstruct formulas in React.
- A contextual event must display that temporal proximity does not prove causation.
- Keep text matching for causal guardrail normalized/case-insensitive and tested.

## Error and Edge Cases

- unknown evidence ID;
- deleted/missing evidence after brief generation;
- duplicate citations;
- one valid and one invalid claim;
- event claim uses prohibited causal phrase;
- no related event exists.

## Testing Requirements

- unknown ID invalidates claim/brief;
- valid IDs resolve;
- causal phrase + event evidence invalidates claim;
- cautious correlation wording remains allowed;
- invalid brief is not returned as latest validated brief;
- provenance drawer renders typed evidence details;
- frontend handles resolver 404/error.

## Definition of Done

- [ ] Every factual claim is deterministically checked for valid evidence IDs.
- [ ] Brief state becomes `valid` or `invalid` after validation.
- [ ] Prohibited causal assertions are rejected in V1.
- [ ] Evidence resolver supports MTR/ANOM/SEG/EVT IDs.
- [ ] Brief citations are clickable in the UI.
- [ ] Provenance shows windows/values/sample information.
- [ ] Invalid briefs are visibly separated from validated briefs.
- [ ] Validation/provenance tests pass.
