---
status: implemented
step: 01
title: Foundation and Development Environment
owner: backend-engineer
depends_on: [00]
---

# Spec 01 — Foundation and Development Environment

## Overview

Create the runnable full-stack skeleton for OpsPilot. This step establishes project layout, local configuration, PostgreSQL, backend/frontend development servers, test tooling, lint/type-check tooling, and a health endpoint. It does not create business tables or analytics logic.

## Business Goal

Make the repository reproducible for another engineer: one documented setup should start the database, backend, and frontend and provide a reliable foundation for every later spec.

## Depends On

- Spec 00 — Project Overview

## Scope

- backend FastAPI project;
- frontend React/TypeScript/Vite project;
- Tailwind setup;
- PostgreSQL Docker Compose service;
- SQLAlchemy/Alembic configuration without domain tables yet;
- environment configuration;
- health endpoint;
- CORS for local frontend development;
- backend/frontend test scaffolding;
- lint and type-check scripts;
- root `.env.example` or documented per-service examples;
- initial README quick start.

## Out of Scope

- domain database tables;
- seed data;
- metrics/anomalies;
- OpenAI calls;
- authentication;
- production deployment infrastructure.

## User Flow

1. Developer clones repository.
2. Copies `.env.example` to `.env` and keeps placeholder/non-secret demo values.
3. Runs `docker compose up -d db`.
4. Starts FastAPI backend.
5. Starts Vite frontend.
6. Frontend renders an OpsPilot shell and confirms backend health.

## Architecture

Backend package root: `backend/app`.

Create small foundational modules:

- `app/main.py` — FastAPI application assembly only;
- `app/core/config.py` — Pydantic Settings;
- `app/db/session.py` — engine/session factory;
- `app/api/routes/health.py` — health route;
- `app/api/router.py` — API router composition.

Frontend should use a small `src/api/client.ts` abstraction rather than scattered `fetch()` calls.

## API Changes

### `GET /api/health`

Response `200`:

```json
{
  "status": "ok",
  "service": "opspilot-api",
  "database": "ok"
}
```

If the database check fails, return `503` with a stable error code rather than pretending the service is healthy.

## Database Changes

No domain tables. Configure Alembic and database connectivity only.

## Backend Files

Create at minimum:

- `backend/pyproject.toml`
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/app/__init__.py`
- `backend/app/main.py`
- `backend/app/core/config.py`
- `backend/app/db/session.py`
- `backend/app/api/router.py`
- `backend/app/api/routes/health.py`
- `backend/tests/test_health.py`

## Frontend Files

Create standard Vite React TypeScript structure plus:

- `frontend/src/api/client.ts`
- `frontend/src/App.tsx`
- `frontend/src/index.css`
- `frontend/src/App.test.tsx`

## Root Files

Create/update:

- `docker-compose.yml`
- `.env.example`
- `.gitignore`
- `README.md`

## New Dependencies

Backend runtime:

- `fastapi`
- `uvicorn`
- `pydantic-settings`
- `sqlalchemy`
- `psycopg[binary]`
- `alembic`

Backend development:

- `pytest`
- `pytest-asyncio`
- `httpx`
- `ruff`
- `mypy`

Frontend:

- React + React DOM
- TypeScript
- Vite
- Tailwind CSS
- ESLint
- Vitest
- Testing Library

Do not install Recharts until Spec 07.

## Implementation Rules

- API prefix is `/api`.
- Settings read environment variables; no secrets in source.
- Database URL must be configurable.
- Use SQLAlchemy 2.x style.
- No `Base.metadata.create_all()` in normal application startup; migrations own schema creation.
- Configure scripts for backend lint/type-check/test and frontend lint/type-check/test.
- App shell may contain placeholder navigation, but no mocked business metrics.

## Error and Edge Cases

- database unavailable at health check;
- missing required environment variables;
- frontend cannot reach backend;
- port conflicts should be documented, not silently changed.

## Testing Requirements

- backend health test for healthy database path (DB dependency may be overridden/mocked);
- backend test for unhealthy database response;
- frontend smoke test for OpsPilot shell;
- TypeScript type check passes;
- Ruff/Mypy baseline passes.

## Definition of Done

- [ ] `docker compose config` validates.
- [ ] PostgreSQL can start from Compose.
- [ ] FastAPI starts on port 8000.
- [ ] Vite starts on port 5173.
- [ ] `GET /api/health` returns the typed health response.
- [ ] Database failure produces a `503` health state.
- [ ] Backend tests pass.
- [ ] Backend Ruff and Mypy checks pass.
- [ ] Frontend tests, ESLint, and `tsc --noEmit` pass.
- [ ] `.env.example` contains placeholders only.
- [ ] README contains local setup instructions.
