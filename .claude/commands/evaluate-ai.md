---
description: Run OpsPilot AI grounding evaluation suite
argument-hint: [optional-suite]
---

# Evaluate AI

Run the OpsPilot evaluation harness, focusing on AI grounding and policy behavior. `$ARGUMENTS` may specify a supported suite such as `ai`, `all`, or `deterministic`; default to `ai` when omitted and the evaluation runner supports it.

## Preconditions

1. Read `CLAUDE.md`.
2. Read Spec 13 and its dependencies relevant to AI validation.
3. Confirm the evaluation runner exists. If Spec 13 is not implemented, stop and report that dependency rather than inventing a new ad hoc evaluator.

## Run

Use the repository-documented evaluation CLI. Evaluate/report at minimum when available:

- citation ID validity;
- unsupported causal-language rejection;
- grounded cautious correlation behavior;
- action evidence grounding;
- invalid brief/action cases;
- optional semantic citation-support scores.

## Network/model behavior

Deterministic evaluation must run without network access.

If optional model-based scoring requires credentials and they are unavailable, it must be reported as `NOT RUN`; do not count it as pass or fail.

## Output

### Summary
Show pass/fail/not-run metrics.

### Failed cases
For each: case ID, expected, observed, likely responsible layer.

### Model-based section
Clearly identify model/config if used.

### Report artifact
State the path of `latest.json`/generated report if present.

Do not fix production code during this command.
