# OpsPilot

**AI Support Operations Command Center** — a vertical slice that turns support operations data into deterministic metrics, detected anomalies, contributor analysis, evidence-backed AI briefs, and human-approved operational actions.

OpsPilot answers three questions from one system, auditably:

1. What changed?
2. Why does it matter?
3. What should somebody do next?

Facts are computed by code. The model narrates and proposes; it is never the source of truth for an operational metric, and it never approves its own action.

> **Status:** Spec 01 (Foundation and Development Environment) is implemented. The application currently exposes a health endpoint and an app shell. Metrics, anomaly detection, AI briefs, and actions arrive in Specs 02–15.

> V1 uses **synthetic data only** and is production-*like*, not production-ready.

## Prerequisites

| Tool | Version used |
|---|---|
| Python | 3.12+ |
| [uv](https://docs.astral.sh/uv/) | 0.10+ |
| Node.js | 22+ |
| Docker + Compose | Compose v2 |

## Quick start

```bash
# 1. Configure the environment (placeholders are fine for local development)
cp .env.example .env

# 2. Start PostgreSQL
docker compose up -d db

# 3. Start the backend (http://localhost:8000)
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# 4. Start the frontend (http://localhost:5173) in a second terminal
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The shell renders and the **Backend health** panel reports API and database status.

Verify the API directly:

```bash
curl http://localhost:8000/api/health
# {"status":"ok","service":"opspilot-api","database":"ok"}
```

Interactive API docs: <http://localhost:8000/docs>.

## Configuration

A single `.env` at the repository root serves Docker Compose, the backend (via pydantic-settings), and the frontend (via Vite). Copy it from `.env.example`, which contains **placeholders only** — never commit a real `.env`.

| Variable | Purpose |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Credentials for the Compose database |
| `POSTGRES_PORT` | Host port the database is published on (default `5432`) |
| `DATABASE_URL` | SQLAlchemy URL used by the backend and Alembic |
| `ENVIRONMENT` | `development` / `demo` / `test` / `production` |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API |
| `LOG_LEVEL` / `LOG_FORMAT` | Log filtering and `json` (default) or `text` output |
| `OPENAI_INPUT_COST_PER_1M` / `OPENAI_OUTPUT_COST_PER_1M` | Optional USD prices for cost estimates; unset means "not configured" |
| `VITE_API_BASE_URL` | API base URL baked into the frontend bundle |

`DATABASE_URL` points at `localhost:5432` because the backend runs on the host while PostgreSQL runs in Docker. If you later run the backend inside Compose, change the host to the service name `db`.

## Ports

| Service | Port | Notes |
|---|---|---|
| Backend (FastAPI/uvicorn) | `8000` | `uv run uvicorn app.main:app --port <port>` |
| Frontend (Vite) | `5173` | `strictPort` is on, so Vite fails loudly instead of silently moving |
| PostgreSQL | `5432` | Override with `POSTGRES_PORT` in `.env` |

**On a port conflict**, change the port deliberately rather than letting a tool pick another one:

- Backend: pass `--port`, then update `VITE_API_BASE_URL`.
- Frontend: run `npm run dev -- --port <port>`, then add that origin to `CORS_ORIGINS`.
- Database: set `POSTGRES_PORT` and update the port in `DATABASE_URL`.

Find what holds a port with `ss -ltnp | grep :8000`.

## Demo data

A deterministic synthetic support dataset (45 days ending 2026-10-03 UTC, ~5,800 tickets, one Billing API deployment event, and a planted EMEA Enterprise Billing anomaly) is seeded with one command. Apply migrations first (`uv run alembic upgrade head`), then from `backend/`:

```bash
uv run python -m app.scripts.seed_demo           # seed; re-running is a no-op
uv run python -m app.scripts.seed_demo --reset   # delete demo rows, then reseed
```

- The seed uses a fixed random seed and window, never the wall clock, so a clean database always receives the same logical dataset (see `SEED_VERSION` in `app/services/demo_data/config.py`).
- It writes only raw operational data and one `EVT-*` event. Metrics, anomalies, contributors, and briefs are computed by later stages, never seeded.
- Demo rows are identified by `DEMO-CUST-*` / `DEMO-TCK-*` refs and the event's seed marker; `--reset` removes only those. Both commands refuse to run unless `ENVIRONMENT` is `development`, `demo`, or `test` (exit code 2).

## Evaluations

The evaluation harness (Spec 13) measures the system against versioned cases in `backend/app/evals/cases/`. From `backend/`, after migrating and seeding:

```bash
uv run python -m app.evals.run --suite all            # default: deterministic + AI guardrails
uv run python -m app.evals.run --suite deterministic  # metrics, anomalies, false positives,
                                                      # contributors, approval boundary, replay
uv run python -m app.evals.run --suite ai             # citations, causal wording, action grounding
uv run python -m app.evals.run --replay-days 7 --no-markdown
```

- Writes `backend/evals/reports/latest.json` (plus `latest.md`). Reports are gitignored. The UI shows the latest report at `/evaluations` via `GET /api/evaluations/latest`, which returns `state: "not_run"` until a report exists.
- Deterministic and AI-guardrail suites never call a model or the network. They read the database inside one transaction that is always rolled back, so the canonical seed is never changed. The only trace is gaps in the `briefs`/`proposed_actions` id sequences left by the rolled-back approval-boundary fixtures.
- Golden cases are tied to the demo `SEED_VERSION`. If the database is unseeded or seeded with another version, they report `not_run` (never pass).
- The optional model-based citation judge runs only with `EVAL_MODEL_ENABLED=true` **and** `OPENAI_API_KEY`/`OPENAI_MODEL` set. Otherwise it reports `NOT RUN`. Its results are listed separately and never count toward deterministic pass rates.
- Exit codes: `0` everything ran and passed, `1` a case failed or errored, `2` refused (non-demo `ENVIRONMENT`), `3` incomplete (some cases did not run).
- The dataset is small and synthetic: results show expected behaviour on planted scenarios and fixtures, not statistically significant performance.

## Observability

Spec 14 uses the standard library only; there is no external monitoring stack.

- **Logs**: JSON on stdout (`LOG_FORMAT=text` for local reading, `LOG_LEVEL` to filter). Every line carries the request ID. API keys, bearer tokens, connection-string passwords and secret-named fields are masked in the formatter. Logs hold identifiers, counts and sizes, never prompts, model output, evidence payloads or ticket bodies.
- **Request IDs**: every response has an `X-Request-ID` header. A plain caller-supplied value (`[A-Za-z0-9._-]{1,64}`) is reused; anything else is replaced. Each request logs `http.request` with method, path (no query string), status and duration.
- **Pipeline stages**: metric computation, anomaly detection, contributor computation, evidence assembly, brief generation and validation, and action execution each log one `pipeline.stage` event with `status`, `duration_ms` and, on failure, the error class and code.
- **LLM traces**: brief generation and action proposals store a row in `llm_traces` with operation, model, latency, tokens (null when the provider reports none), status, a redacted error code and message, and the related brief, action and request IDs. The optional evaluation judge logs the same metadata without storing it, because evaluation runs are always rolled back. If a trace can't be stored, the request still succeeds and `llm_trace.persist_failed` is logged.
- **Cost**: estimated only when both `OPENAI_INPUT_COST_PER_1M` and `OPENAI_OUTPUT_COST_PER_1M` are set (USD per million tokens). Otherwise `estimated_cost_usd` is null and the UI says "not configured". Each estimate uses the prices set when the call was recorded.
- **System API** (only when `ENVIRONMENT` is `development`, `demo` or `test`; otherwise 404 `SYSTEM_ENDPOINTS_DISABLED`):
  - `GET /api/system/health`: database, migration revision, LLM, cost and evaluation readiness. Returns 503 `DATABASE_UNAVAILABLE` when the database is down. Never echoes secrets.
  - `GET /api/system/llm-traces?operation&status&since&until&limit&offset`: paginated, newest first, `limit` ≤ 100.
  - `GET /api/system/summary?period=24h|7d|30d|all`: calls, error rate, latency avg/p50/p95/max, token and cost totals per operation, and execution outcomes with recent failures.
- **UI**: `/system` shows all of the above.

## Quality gates

Backend (from `backend/`):

```bash
uv run pytest             # tests
uv run ruff check .       # lint
uv run ruff format --check .
uv run mypy               # static typing of the app package
uv run alembic current    # migration state (requires a running database)
```

Frontend (from `frontend/`):

```bash
npm run test       # Vitest, non-watch
npm run lint       # ESLint
npm run typecheck  # tsc --noEmit
npm run build      # production build
```

Infrastructure (from the repository root):

```bash
docker compose config
```

Backend tests override the database dependency, so the health tests need no database. Database tests (migrations, constraints, repositories) run only when `TEST_DATABASE_URL` points at a dedicated database whose name ends in `_test` (see `.env.example`); otherwise they are skipped. The destructive downgrade test refuses to run against `DATABASE_URL` or any non-`_test` database.

## Project layout

```text
OpsPilot/
├── CLAUDE.md               # repository constitution — read before implementation work
├── .claude/specs/          # the specs that drive implementation
├── backend/
│   ├── app/
│   │   ├── api/            # routers and thin routes
│   │   ├── core/           # configuration
│   │   ├── db/             # engine, session, declarative base
│   │   ├── schemas/        # Pydantic API contracts
│   │   └── services/       # use-case logic
│   ├── alembic/            # migrations (no domain tables yet)
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/            # the single typed HTTP boundary
│       └── types/          # TypeScript mirrors of the API contracts
└── docker-compose.yml      # PostgreSQL service
```

## Architecture rules that matter here

- Authoritative metrics are computed in SQL/Python, never by the LLM.
- Routes stay thin: `route -> service -> repository/engine`.
- Alembic owns the schema. There is no `create_all()` in application startup.
- API endpoints are prefixed with `/api` and return typed bodies with stable error codes — failures are never dressed up as `200 OK`.
- Business logic stays out of React; the frontend formats, it does not calculate.
- Every data view needs loading, error, empty, and success states, and must never show a fabricated placeholder value in place of an unknown one.

The full set is in [`CLAUDE.md`](./CLAUDE.md).

## Troubleshooting

**`GET /api/health` returns `503 DATABASE_UNAVAILABLE`** — the database is unreachable. Check `docker compose ps` (the `db` service should be `healthy`) and confirm `DATABASE_URL` matches `POSTGRES_*` in `.env`. This response is correct behaviour, not a bug: the service reports database failure instead of claiming health.

**The health panel shows "Backend unavailable" with `NETWORK_UNREACHABLE`** — the frontend cannot reach the backend. Confirm uvicorn is running and that `VITE_API_BASE_URL` matches its address. Restart `npm run dev` after changing any `VITE_*` variable, as Vite reads them at startup.

**Browser console shows a CORS error** — add the frontend origin to `CORS_ORIGINS` in `.env` and restart the backend.

**`uv run alembic current` prints no revision** — expected. Spec 01 configures Alembic but defines no migrations; Spec 02 adds the domain schema.
# OpsPilot
