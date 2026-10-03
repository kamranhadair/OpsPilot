---
status: planned
step: 08
title: AI Evidence Bundle
owner: ai-engineer
depends_on: [06]
---

# Spec 08 — AI Evidence Bundle

## Overview

Create the strict typed boundary between deterministic analytics and the LLM. The Evidence Bundle is the only operational evidence the brief-generation model may use in V1.

## Business Goal

Make model input inspectable, bounded, and auditable so the AI narrates precomputed facts instead of becoming an analytics engine.

## Depends On

- Spec 06 — Contributor Analysis

## Scope

Build an Evidence Bundle assembler containing:

- analysis window metadata;
- selected metric evidence;
- active anomaly evidence;
- top contributor evidence;
- related timeline events/incidents;
- explicit provenance summaries.

## Out of Scope

- LLM calls;
- brief generation;
- action proposals;
- raw ticket retrieval for the model.

## Evidence Bundle Schema

Create Pydantic models similar to:

```text
EvidenceBundle
  analysis_window
  metrics[]
  anomalies[]
  contributors[]
  related_events[]
  allowed_evidence_ids[]
```

Each item must include:

- `evidence_id`;
- `evidence_type`;
- human-readable label;
- structured facts/values;
- relevant dimensions/window;
- concise provenance fields.

The bundle must distinguish **observed facts** from **contextual events**. An incident/deployment item is not a causal finding.

## Selection Rules

V1 should include:

- overview metrics relevant to the current analysis;
- active/highest-severity anomalies;
- top contributors for included anomalies;
- related events occurring within a configurable time distance of the analysis/anomaly window.

Keep bundles bounded. Do not indiscriminately include every historical metric.

## Raw Data Restriction

The Evidence Bundle must not contain:

- raw ticket message bodies;
- arbitrary lists of thousands of ticket rows;
- secrets;
- database credentials;
- hidden SQL statements as the only explanation.

A small numeric sample count is fine. Ticket references for drilldown are not needed by the model in V1.

## API Changes

### `GET /api/evidence-bundles/latest`

Developer/demo inspection endpoint returning the current assembled bundle. This is useful for proving exactly what the model receives.

Do not expose secrets or internal credentials.

## Architecture

Suggested files:

- `backend/app/schemas/evidence.py`
- `backend/app/services/evidence/assembler.py`
- `backend/app/services/evidence/resolver.py`
- `backend/app/api/routes/evidence_bundles.py`
- tests

## Database Changes

No new persistence required for bundles in V1. They may be assembled from persisted evidence. If caching is introduced, it must not become a second source of truth.

## New Dependencies

No new dependency.

## Implementation Rules

- Only evidence IDs that exist in persisted evidence sources can enter `allowed_evidence_ids`.
- Deduplicate evidence IDs.
- Preserve the same analysis window across related metrics/anomalies unless explicitly marked otherwise.
- Related event language/metadata must not imply causation.
- The assembler is deterministic for a fixed database state and window.

## Error and Edge Cases

- no anomalies;
- no related events;
- contributor records missing;
- metric evidence from a mismatched window;
- duplicate evidence ID.

## Testing Requirements

- schema validation;
- deterministic bundle assembly;
- no raw ticket bodies/large row lists;
- all allowed IDs resolve;
- mismatched-window evidence rejected or clearly excluded;
- related event is labeled contextual, not causal.

## Definition of Done

- [ ] Typed Evidence Bundle models exist.
- [ ] Bundle contains metrics, anomalies, contributors, and optional related events.
- [ ] Bundle includes an explicit allow-list of evidence IDs.
- [ ] Raw ticket data is excluded.
- [ ] `GET /api/evidence-bundles/latest` exposes safe inspection data.
- [ ] Evidence bundle tests pass.
