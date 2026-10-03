---
description: Verify the complete OpsPilot portfolio demo
---

# Demo Check

Verify the canonical OpsPilot end-to-end demo defined by Spec 15.

## Preconditions

Read `CLAUDE.md` and Spec 15. If Spec 15 is not implemented, run only the portions that exist and report `NOT READY`; do not create missing demo features inside this command.

## Verification sequence

Use the repository's documented demo/reset/test tooling to verify:

1. demo environment guard is enabled for reset;
2. deterministic dataset resets/seeds successfully;
3. metrics compute for the final window;
4. planted Billing anomaly is detected;
5. contributor analysis surfaces EMEA Enterprise prominently;
6. Evidence Bundle contains valid MTR/ANOM/SEG/EVT IDs;
7. deterministic/fake-provider brief validates with grounded citations;
8. provenance resolver returns cited evidence;
9. unsupported causation case is rejected by tests/evaluation;
10. investigation proposal is pending approval;
11. execute-before-approval is blocked;
12. human approval succeeds;
13. mock execution creates exactly one `INV-*` reference;
14. evaluation report is available;
15. system/LLM trace information is available;
16. Playwright canonical flow passes when configured.

## Output

Print a checklist like:

```text
DEMO READY / DEMO NOT READY
[PASS] Dataset seeded
[PASS] Metrics computed
...
```

For every failure include the responsible spec/layer and the command/test that failed.

Do not modify application behavior just to force a green demo.
