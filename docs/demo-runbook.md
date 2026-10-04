# OpsPilot demo runbook (3–4 minutes)

A scripted walkthrough of the canonical story. It includes one **control case**: an execution that is blocked before approval. The automated version of this story is `frontend/e2e/demo.spec.ts` (`npm run e2e`).

## Before the audience arrives (about 2 minutes)

```bash
docker compose up -d db
cd backend
uv run alembic upgrade head
uv run python -m app.scripts.demo reset     # known pre-analysis state
uv run python -m app.evals.run              # fresh evaluation report for /evaluations
uv run uvicorn app.main:app --port 8000     # leave running
# second terminal
cd frontend && npm run dev                  # http://localhost:5173
```

- Set `ENVIRONMENT=development` (or `demo`). In any other environment the **Run analysis** control does not appear.
- **With an OpenAI key:** set `OPENAI_API_KEY` and `OPENAI_MODEL` for a live brief. The live model's wording varies from run to run. It is validated every time, and an `invalid` brief is shown as invalid (that is a valid demo talking point too).
- **Without a key:** the deterministic half of the demo works fully. The brief shows `not_configured`, which demonstrates that there is no fake fallback. To show the AI half offline, run the Playwright test and narrate from its trace (`npx playwright show-trace`).
- Rehearse once, then run `demo reset` again so the live run starts clean.

## Script

| # | Time | Do | Say |
|---|---|---|---|
| 1 | 0:00 | Terminal: show the `demo reset` output (checksum, 5,781 tickets, 1 event). | "Deterministic synthetic dataset, same checksum every time. Reset is CLI-only and refused outside demo environments." |
| 2 | 0:15 | Dashboard: "No metrics computed yet". | "Known pre-analysis state: nothing derived exists yet." |
| 3 | 0:25 | Press **Run analysis**. | "One orchestration path: metrics, then anomalies, contributors, the evidence bundle, then a brief and its validation. It never proposes or executes anything." |
| 4 | 0:40 | Show the metric cards and trends, then the run result's **Most severe** anomaly and the active anomalies table with the high Billing ticket-volume anomaly. | "Every number is SQL/Python from one metric registry. The model never computes a metric." |
| 5 | 1:00 | Open the Billing ticket-volume anomaly drilldown. | "Contributor analysis: EMEA / Enterprise accounts for most of the increase, with a documented formula and its own SEG- evidence ID." |
| 6 | 1:20 | Open the brief (link in the run result, or **Briefs**). Point at the green *Validated against evidence* banner. | "Every claim cites evidence IDs from the bundle. Unknown IDs or causal wording make a brief invalid." |
| 7 | 1:40 | Click a `SEG-` or `MTR-` citation; the provenance drawer opens. | "Click-through provenance: values, window, sample size, formula." |
| 8 | 1:55 | Read the deployment claim aloud. | "It says the deployment *coincided with* the increase and warrants investigation, not that it caused it. Correlation is not causation, and the validator enforces that." |
| 9 | 2:10 | Press **Propose investigation**. The action opens as *pending approval*. | "The AI drafts one allow-listed action type, grounded in the validated brief." |
| 10 | 2:25 | **Control case:** point out that there is no *Create investigation* button yet. Explain that the backend rejects `POST /execute` with `409 ACTION_INVALID_TRANSITION` before approval. The Playwright test and `tests/actions/test_approval_execution_api.py` prove it. | "The UI hiding a button isn't the control; the backend refuses the transition." Don't corrupt live state to show it. |
| 11 | 2:45 | Edit the title, add a comment, press **Approve**. | "A human decision record, with before/after edits, written to the audit log." |
| 12 | 3:00 | Press **Create investigation**. Show the `INV-…` reference. | "Mock adapter, idempotent: replaying returns the same reference." |
| 13 | 3:15 | Open **Evaluations**, then **System**. | "Golden cases, including the false positives it still finds. LLM traces with latency, tokens, cost only if configured, and errors." |

## If something goes wrong

| Symptom | Recovery |
|---|---|
| The brief is `invalid` (live model) | Show the issue list. "The guardrail worked." Then use **Briefs** or run the analysis again. |
| The brief shows `failed` (`LLM_TIMEOUT`, …) | The deterministic facts are already saved. Show the failed trace on **System** as an observability moment. |
| No Run analysis button | `ENVIRONMENT` is not development, demo or test. Fix `.env` and restart the backend. |
| "This brief already has a proposal" | The link goes to the existing action. Each brief allows one proposal. |
| Need to start over | `uv run python -m app.scripts.demo reset`, then reload the page. |
