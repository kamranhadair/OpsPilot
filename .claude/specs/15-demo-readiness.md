---
status: planned
step: 15
title: Demo and Production Readiness
owner: architect
depends_on: [14]
---

# Spec 15 — Demo and Production Readiness

## Overview

Close the full vertical slice, automate the canonical demo scenario, add end-to-end verification, and document what is production-like versus intentionally mocked.

## Business Goal

Make OpsPilot cloneable, runnable, explainable, and dependable enough for a 3–4 minute portfolio demo that includes one failure/control case rather than only a happy path.

## Depends On

- Spec 14 — Observability

## Scope

- analysis orchestration service;
- demo reset/run scripts guarded by environment;
- one-click/manual analysis trigger for demo;
- final navigation across dashboard/brief/actions/evaluations/system;
- Playwright vertical-slice test;
- architecture/runbook/demo documentation;
- final quality gates;
- production-readiness gap list.

## Out of Scope

- making the app truly multi-tenant/production-authenticated;
- replacing mock integration with Jira;
- cloud infrastructure automation unless separately approved.

## Analysis Orchestration

Create one application service (not a route with inline logic) that runs:

```text
compute required metrics
-> detect anomalies
-> compute contributors
-> assemble evidence bundle
-> optionally generate brief when LLM is configured
-> validate brief
```

The service returns stable IDs for the resulting analysis artifacts. It does not automatically approve or execute actions.

Expose a demo/development-only endpoint or UI control to run the analysis. In non-demo production mode, the unsafe demo/reset capability must be disabled.

## Demo Reset

Provide a deterministic reset workflow that:

1. confirms demo/development environment;
2. resets synthetic data safely;
3. clears derived demo artifacts;
4. reseeds the fixed dataset;
5. leaves database in known pre-analysis state.

Do not implement a generic unauthenticated destructive endpoint available in production.

## Canonical Demo Story

The final demo must support this flow:

1. Reset/seed known support dataset.
2. Open dashboard and show normal/current metrics.
3. Run analysis for the final window.
4. Show high Billing anomaly.
5. Drill down to EMEA Enterprise contributor evidence.
6. Generate validated AI brief with citations.
7. Click a metric/segment citation to inspect provenance.
8. Show a cautious deployment correlation statement rather than unsupported causation.
9. Generate an `open_investigation` proposal.
10. Demonstrate that execute-before-approval is blocked (automated test or UI explanation; do not intentionally corrupt live demo state).
11. Human reviews/edits and approves.
12. Execute mock adapter and show `INV-*` reference.
13. Show evaluation page and system/LLM trace page.

## Browser Test

Create a Playwright test that verifies the main happy path against a local test/demo environment. Network calls to OpenAI should be controllable: either use a deterministic test provider fixture or mark the live-AI portion separately. The core end-to-end test must not require paid network access.

## Documentation

README must include:

- problem statement/customer scenario;
- architecture diagram (Mermaid acceptable);
- why metrics/anomalies are deterministic;
- evidence/grounding design;
- human approval boundary;
- setup and environment variables;
- seed/run/test commands;
- evaluation approach;
- known V1 limitations;
- productionization checklist.

Add a short demo runbook/script under `docs/` if useful.

## Production Readiness Gap List

Explicitly document at least:

- production identity/RBAC;
- real data source ingestion and secrets management;
- background scheduling/queues;
- tenant isolation;
- real Jira/Slack integration;
- external monitoring/alerting;
- retention/privacy policy;
- load/performance testing;
- backup/recovery;
- model/provider governance.

## API/Frontend Changes

Add only the minimal demo analysis trigger/status functionality required. Reuse existing screens; do not redesign the product into a chatbot.

## New Dependencies

- Playwright if not already installed/configured.

No orchestration framework is required.

## Implementation Rules

- Demo reset/run functionality is environment-guarded.
- Core E2E test is reproducible/offline with fake model responses.
- Live OpenAI demo remains optional and configuration-driven.
- Do not hide known limitations in README.
- Do not add unrelated "portfolio polish" features until all quality gates pass.

## Testing Requirements

- Playwright canonical happy path;
- explicit execute-without-approval API test remains present;
- demo reset idempotency;
- demo-only endpoints unavailable when environment guard is off;
- full backend/frontend quality checks;
- evaluation suite run.

## Definition of Done

- [ ] One command/workflow resets and seeds the demo safely.
- [ ] One analysis orchestration path produces metrics -> anomalies -> contributors -> evidence -> validated brief.
- [ ] Canonical Billing/EMEA Enterprise scenario is visible end to end.
- [ ] Citation provenance is inspectable.
- [ ] Investigation cannot execute without human approval.
- [ ] Approved action creates one mock `INV-*` reference.
- [ ] Evaluation and system pages are usable.
- [ ] Core Playwright flow passes without paid network dependency.
- [ ] README/runbook explains architecture, trade-offs, failures, and production gaps.
- [ ] Backend tests/lint/type-check pass.
- [ ] Frontend tests/lint/type-check pass.
- [ ] `/demo-check` can verify the final scenario.
