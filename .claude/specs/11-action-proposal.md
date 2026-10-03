---
status: planned
step: 11
title: Action Proposal
owner: ai-engineer
depends_on: [10]
---

# Spec 11 — Action Proposal

## Overview

Allow OpsPilot to draft one evidence-grounded operational action from a validated brief: opening an investigation. The action remains a proposal and cannot execute in this spec.

## Business Goal

Close the gap between insight and action while preserving a hard boundary between AI suggestion and human authority.

## Depends On

- Spec 10 — Claim Validation and Provenance

## Scope

- V1 action allow-list with one action: `open_investigation`;
- structured AI action proposal generation;
- evidence validation for proposals;
- persistence in `proposed_actions`;
- action list/detail API;
- review UI showing draft and supporting evidence.

## Out of Scope

- approval/rejection state transitions beyond placing a proposal in `pending_approval`;
- external execution;
- Jira/Slack integrations;
- additional action types.

## Proposal Contract

Structured model output should include:

```json
{
  "action_type": "open_investigation",
  "title": "Investigate EMEA Billing ticket spike",
  "description": "...",
  "rationale": "...",
  "investigation_steps": ["..."],
  "evidence_ids": ["ANOM-...", "SEG-...", "MTR-..."]
}
```

The backend controls the allow-list. Unknown action types are rejected even if returned by the model.

## Grounding Rules

- Source brief must have `status = valid`.
- Proposal evidence IDs must resolve and must be contained in the source brief/evidence bundle context.
- Proposal must not claim causal certainty unsupported by evidence.
- The model may suggest investigation steps; it may not claim the action has already occurred.

## State

On successful generation and validation:

`proposed -> pending_approval`

Do not auto-approve.

## API Changes

### `POST /api/briefs/{brief_id}/actions/propose`

Creates one pending proposal from a validated brief.

### `GET /api/actions`

Supports status filter; default can show pending approvals first.

### `GET /api/actions/{action_id}`

Returns proposal, supporting evidence IDs, source brief, and current state.

## Frontend Changes

Routes:

- `/actions`
- `/actions/:id`

The detail page must show:

- title/description/rationale;
- evidence citations;
- status;
- "Awaiting human approval" state;
- no execution button yet.

## Architecture

Reuse the LLM client boundary from Spec 09 with a separate operation/schema. Keep action business rules in an action service, not the provider client.

Suggested files:

- `backend/app/services/actions/proposer.py`
- `backend/app/services/actions/policy.py`
- `backend/app/schemas/actions.py`
- `backend/app/repositories/action_repository.py`
- `backend/app/api/routes/actions.py`
- frontend `features/actions/`

## Database Changes

Use `proposed_actions`. No new table.

## New Dependencies

No new dependency.

## Implementation Rules

- V1 allow-list contains only `open_investigation`.
- Never create proposal from an invalid brief.
- Never call an external system.
- Never create an approval record.
- Persist evidence IDs unchanged; do not invent or repair.
- Record AI/system audit events for proposal creation/state transition.

## Error and Edge Cases

- invalid brief;
- no actionable anomaly;
- malformed output;
- unsupported action type;
- invalid evidence ID;
- duplicate proposal request for same brief.

## Testing Requirements

- validated brief can create grounded proposal;
- invalid brief cannot;
- unsupported action type rejected;
- unknown evidence ID rejected;
- proposal is pending approval, never approved;
- duplicate generation policy tested;
- UI renders evidence and pending status.

## Definition of Done

- [ ] `open_investigation` is the only executable V1 action type.
- [ ] Proposal is structured and evidence-grounded.
- [ ] Source brief must be valid.
- [ ] Proposal ends in `pending_approval`.
- [ ] No external integration executes.
- [ ] Action list/detail UI exists.
- [ ] Proposal tests pass.
