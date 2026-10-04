---
status: implemented
step: 13
title: Evaluation Framework
owner: evaluator
depends_on: [12]
---

# Spec 13 — Evaluation Framework

## Overview

Build a repeatable evaluation harness for the deterministic analytics, AI grounding behavior, and human-approval boundary. Evaluation results must include real failure cases rather than only a single success metric.

## Business Goal

Prove that OpsPilot is measured as a system: not merely whether the UI looks good, but whether it detects the right operational changes, cites the right evidence, avoids unsupported claims, and respects approval policy.

## Depends On

- Spec 12 — Human Approval and Execution

## Scope

Create deterministic evaluation suites for:

- metric correctness;
- anomaly detection;
- false-positive behavior;
- contributor attribution;
- citation validity;
- causal-language guardrail;
- action grounding;
- approval boundary;
- historical replay over selected dataset days.

Add optional model-based citation-support evaluation only when an API key/config explicitly enables it.

## Out of Scope

- training/fine-tuning models;
- external benchmark services;
- claiming statistical significance from the small demo dataset.

## Evaluation Cases

Store version-controlled cases under `backend/app/evals/cases/` or equivalent. Include at least:

1. **Planted Billing spike** — expected to be detected.
2. **Normal queue/day** — should not become high/critical without evidence.
3. **EMEA Enterprise attribution** — expected top contributor family.
4. **Fabricated citation** — must fail validation.
5. **Unsupported causal wording** — must fail validation.
6. **Grounded correlation wording** — should pass runtime guardrail.
7. **Ungrounded action evidence** — proposal rejected.
8. **Execute without approval** — blocked.

## Evaluation Metrics

Report at minimum:

- metric fixture pass rate;
- expected anomaly recall for planted cases;
- high/critical false-positive count/rate on designated normal cases;
- contributor top-k hit rate;
- citation ID validity rate;
- runtime causation-guard pass/fail count;
- action grounding pass rate;
- approval-boundary pass rate.

If optional model-based claim-support scoring runs, label it separately from deterministic checks and record model/config used.

## Replay

Provide a replay runner for at least the final seven analysis days. It should run the deterministic pipeline for each day and summarize which anomalies would have appeared.

Do not mutate the canonical seed irreversibly during replay. Use transaction rollback, isolated test database, or explicitly regenerated demo state.

## Reports

Write machine-readable report:

- `backend/evals/reports/latest.json`

Optionally write a human-readable Markdown companion.

Do not commit volatile timestamp-only diffs by default unless the user wants stored reports in git.

## API Changes

### `GET /api/evaluations/latest`

Return the latest available evaluation report or a clear `not_run` state.

## Frontend Changes

Add route:

- `/evaluations`

Show:

- deterministic evaluation summary;
- pass/fail by category;
- failed case details;
- optional model-based section clearly labeled;
- replay summary.

## CLI

Provide a runner such as:

```bash
python -m app.evals.run --suite all
python -m app.evals.run --suite ai
python -m app.evals.run --suite deterministic
```

Exact module path may vary but must be documented.

## New Dependencies

Prefer existing test stack. Add no evaluation framework dependency unless it materially simplifies the project.

## Implementation Rules

- Deterministic evaluations must run without OpenAI/network access.
- Optional AI/model-based evaluations must report `not_run`, not pass, when credentials are unavailable.
- Keep expected planted-scenario facts versioned with seed version.
- An evaluator should report failures; it should not silently change thresholds to make the suite pass.

## Error and Edge Cases

- no evaluation report yet;
- seed version mismatch;
- optional AI evaluator unavailable;
- replay produces no data for a date;
- evaluation runner partially fails.

## Testing Requirements

Test the evaluator itself using tiny fixtures so a broken reporting layer cannot falsely show green.

## Definition of Done

- [ ] Versioned evaluation cases cover all listed categories.
- [ ] Deterministic suite runs offline.
- [ ] Planted Billing anomaly is detected by the golden case.
- [ ] Normal-case false positives are reported.
- [ ] Citation and causation failures are represented explicitly.
- [ ] Approval bypass case fails as expected.
- [ ] Replay produces a multi-day summary.
- [ ] Latest evaluation report is available through API/UI.
- [ ] Optional model-based eval never silently counts as passed when not run.
