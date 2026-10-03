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
