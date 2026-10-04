---
status: verified
step: 09
title: AI Operations Brief
owner: ai-engineer
depends_on: [08]
---

# Spec 09 — AI Operations Brief

## Overview

Generate a concise structured operations brief from an Evidence Bundle using the OpenAI API. The model narrates existing evidence; it does not calculate operational truth.

## Business Goal

Turn a dense operational evidence set into an understandable morning brief while preserving citations for every factual claim.

## Depends On

- Spec 08 — AI Evidence Bundle

## Scope

- one application-owned OpenAI client boundary;
- structured output schema;
- prompt contract;
- brief persistence;
- claim persistence;
- bounded retry/error handling;
- brief API endpoints;
- mocked model tests.

## Out of Scope

- final runtime claim validation/provenance UI (Spec 10);
- action proposal generation (Spec 11);
- model-based evaluation (Spec 13).

## Structured Output Contract

The model must return fields equivalent to:

```json
{
  "headline": "...",
  "summary": "...",
  "claims": [
    {
      "claim_type": "observation",
      "text": "...",
      "evidence_ids": ["MTR-001", "SEG-002"]
    }
  ],
  "attention_items": ["..."]
}
```

Every factual claim requires at least one evidence ID. Attention items may recommend investigation focus but must not execute or create an action record yet.

## Prompt Rules

System/application prompt must clearly instruct:

- use only the provided Evidence Bundle;
- never invent evidence IDs;
- never calculate missing metrics;
- do not state unsupported causation;
- distinguish observation from inference;
- use concise operations language;
- if evidence is insufficient, say so rather than fill gaps.

## AI Client Boundary

Create a small provider abstraction such as `LLMClient`/`OpenAIBriefClient`. Business services should not scatter direct SDK calls.

Configuration:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- bounded timeout/retry settings

Do not hardcode a model version inside domain services.

## API Changes

### `POST /api/briefs/generate`

Builds/accepts the latest Evidence Bundle, calls the provider, parses structured output, persists a `draft` brief + claims, and returns the draft object.

### `GET /api/briefs/latest`

Before Spec 10, may return latest brief with its current validation status. After Spec 10, default user-facing behavior must prefer validated briefs.

### `GET /api/briefs/{brief_id}`

Returns typed brief + claims.

## Database Changes

Use `briefs`, `brief_claims`, and `llm_traces` from Spec 02. A minimal trace row should be recorded for each call now; richer observability is completed in Spec 14.

## Backend Files

Suggested:

- `backend/app/integrations/llm/base.py`
- `backend/app/integrations/llm/openai_client.py`
- `backend/app/services/briefs/generator.py`
- `backend/app/schemas/briefs.py`
- `backend/app/repositories/brief_repository.py`
- `backend/app/api/routes/briefs.py`
- tests

## New Dependencies

- official OpenAI Python SDK

## Implementation Rules

- Pydantic validates model output before persistence.
- Unknown/malformed structure fails explicitly.
- If API key is absent, return a stable `LLM_NOT_CONFIGURED` error/state; do not fabricate a brief.
- Tests use a fake/mock client; unit tests must not require network access.
- Never log API keys or full secret-bearing headers.
- Do not execute recommended actions.

## Error and Edge Cases

- API key missing;
- provider timeout;
- rate limit;
- malformed structured output;
- empty Evidence Bundle;
- model references an unknown ID (draft may persist but will be invalidated by Spec 10; do not silently repair the ID).

## Testing Requirements

- valid structured response persists brief + ordered claims;
- malformed response rejected;
- provider error produces typed application failure;
- missing API key behavior;
- fake client verifies exact bundle boundary;
- prompt/schema requires evidence IDs per factual claim.

## Definition of Done

- [ ] OpenAI access is isolated behind one client boundary.
- [ ] Brief output is structured and Pydantic-validated.
- [ ] Claims persist with evidence ID arrays.
- [ ] No authoritative metric calculation occurs in model code.
- [ ] Missing credentials never trigger fake output.
- [ ] LLM call trace is recorded.
- [ ] API endpoints return typed brief data.
- [ ] Unit tests run without network access.
