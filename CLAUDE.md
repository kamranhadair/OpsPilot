# OpsPilot — Repository Instructions for Claude Code

OpsPilot is an AI Support Operations Command Center for a fictional B2B SaaS company. It turns support operations data into deterministic metrics, detected anomalies, contributor analysis, evidence-backed AI briefs, and human-approved operational actions.

This file is the repository constitution. Read it before any implementation or review work. If a feature spec conflicts with this file, stop and report the conflict instead of silently choosing one interpretation.

## Product goal

A support operations manager should be able to answer three questions from one system:

1. What changed?
2. Why does it matter?
3. What should somebody do next?

The system must make those answers auditable. Facts are computed by code. The model may narrate or propose, but it must not become the source of truth for operational metrics.

## Locked V1 scope

V1 is a complete vertical slice:

`synthetic support data -> metrics -> anomaly detection -> contributor analysis -> evidence bundle -> AI brief -> claim validation/provenance -> action proposal -> human approval -> mock investigation execution -> evaluations/observability`

V1 deliberately does **not** include real Zendesk, Jira, or Slack connectivity; multi-tenant architecture; production RBAC; Redis/Celery; Kafka; Kubernetes; LangGraph; embeddings/RAG; fine-tuning; forecasting; or a free-form chatbot.

Do not implement an out-of-scope capability unless a later approved spec explicitly adds it.

## Locked technology stack

- Frontend: React + TypeScript + Vite + Tailwind CSS
- Charts: Recharts
- Backend: Python + FastAPI + Pydantic
- Database: PostgreSQL
- ORM: SQLAlchemy 2.x
- Migrations: Alembic
- Analytics: SQL + Python
- AI provider: OpenAI API through one application-owned client boundary
- Backend tests: Pytest
- Frontend tests: Vitest + Testing Library
- Browser tests: Playwright
- Containers: Docker Compose

Do not replace a locked technology without explicit user approval.

## Core architecture rules

### 1. Compute facts in deterministic code

Authoritative values such as ticket volume, backlog, response time, SLA breach rate, escalation rate, percentage change, baselines, anomaly severity, and contributor percentages are computed in SQL/Python.

The LLM must never be asked to calculate an authoritative business metric from raw operational rows.

### 2. The model receives evidence, not a data lake

Model calls receive a typed Evidence Bundle containing computed metrics, detected anomalies, contributor facts, and related timeline events. Do not send raw ticket corpora or arbitrary database rows to the model.

### 3. Every factual AI claim needs evidence

Every factual claim in an operations brief must reference one or more existing evidence IDs. Unknown evidence IDs make the brief invalid. Invalid briefs must not be presented as validated operational truth.

### 4. Correlation is not causation

A deployment followed by a support spike does not prove that the deployment caused the spike. V1 may say that events "coincided," "occurred near," or "warrant investigation." It must not assert causation unless a future evidence type explicitly supports causal analysis.

### 5. AI proposes; humans approve

The LLM may draft an investigation action. It cannot approve or execute the action. Execution must be rejected by the backend unless the action has a recorded human approval.

### 6. Business logic stays out of React

The frontend may format values for presentation. It must not calculate anomaly severity, business thresholds, SLA policy, contributor ranking, action eligibility, or approval state transitions.

### 7. Thin API routes

Prefer:

`route -> service -> repository / engine`

Do not put analytics, orchestration, or persistence logic directly into FastAPI route handlers.

### 8. Stable typed contracts

Use Pydantic response/request models for API boundaries and TypeScript types for frontend API contracts. Avoid untyped dictionaries crossing public application boundaries when a schema is known.

## Target repository shape

The specs may add files incrementally, but the intended shape is:

```text
OpsPilot/
├── CLAUDE.md
├── .claude/
│   ├── specs/
│   ├── agents/
│   ├── commands/
│   └── launch.json
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── integrations/
│   │   ├── evals/
│   │   └── scripts/
│   ├── alembic/
│   └── tests/
├── frontend/
│   ├── src/
│   └── tests/
├── docker-compose.yml
└── README.md
```

## Spec-driven workflow

Implementation is driven by `.claude/specs/*.md`.

Every implementation task must:

1. Read this `CLAUDE.md`.
2. Read the requested spec completely.
3. Read every dependency listed by that spec.
4. Inspect the existing implementation before editing.
5. Implement only the requested scope.
6. Add or update tests.
7. Run relevant checks.
8. Check every Definition of Done item.
9. Report deviations, failures, and assumptions.

Do not implement future specs early merely because doing so seems convenient.

### Spec status

Allowed status values are:

- `planned`
- `in_progress`
- `implemented`
- `verified`

`/implement-spec` may move `planned -> in_progress -> implemented` after its own checks pass. It must never mark a spec `verified`.

Only `/review-spec` may mark a spec `verified`, and only when every applicable Definition of Done item is demonstrated.

## Dependency discipline

If a required dependency spec is not at least `implemented`, stop and report the unmet dependency. Do not work around missing prerequisite architecture.

Do not add a package, service, database, queue, framework, or external integration unless the active spec requires it.

## Database rules

- PostgreSQL is the system of record.
- Use SQLAlchemy 2.x and Alembic; do not create tables ad hoc at application startup.
- All timestamps are UTC and timezone-aware.
- Use parameterized ORM/SQL constructs; never interpolate untrusted values into SQL strings.
- Add indexes deliberately for the read paths defined by the specs.
- Migrations must have an upgrade and downgrade path unless the spec explicitly documents why a downgrade is unsafe.
- Demo seed operations must be deterministic and idempotent.

## Analytics rules

- Metric definitions live in a central registry, not scattered across routes/components.
- A metric snapshot must include provenance sufficient to explain the source window, dimensions/filters, sample size, and computation time.
- Percentage change with a zero baseline must be represented explicitly; never divide by zero or silently invent infinity.
- Anomaly severity is deterministic.
- Contributor analysis must use documented formulas and preserve the evidence used to produce rankings.

## AI rules

- All model output used by the application must be structured and validated with Pydantic.
- The model name comes from configuration, not hard-coded business code.
- Never expose API keys or secrets in prompts, logs, fixtures, or frontend bundles.
- Never invent evidence IDs.
- Never treat an LLM response as valid merely because it parsed.
- Do not silently fall back to fake AI output when the API key is absent. Return an explicit not-configured state.
- Model calls must be mockable in tests.
- Retries must be bounded.

## Action and approval rules

- V1 supports one executable action type: `open_investigation`.
- Action types are allow-listed in code.
- An action must reference evidence from a validated brief/evidence bundle.
- A human approval record is mandatory before execution.
- Approval and execution are separate backend state transitions.
- Execution must be idempotent.
- Every state transition is written to the audit log.

## API conventions

- Prefix application endpoints with `/api`.
- Return typed error bodies with a stable machine-readable code where practical.
- Use appropriate HTTP status codes; do not encode failures as `200 OK`.
- Validate pagination/filter inputs.
- Keep demo-only endpoints or capabilities disabled outside demo/development configuration.

## Frontend conventions

- Use feature-oriented folders rather than one giant components directory.
- API access goes through a small typed client layer.
- Every data view needs loading, error, empty, and success states.
- Evidence IDs shown in briefs must be interactable and open provenance details once Spec 10 is implemented.
- Do not hide invalid/unknown states with fabricated placeholder values.

## Testing and quality gates

Backend:

- Pytest for unit/integration tests
- Ruff for linting/format checks
- Mypy for static typing of the application package

Frontend:

- ESLint
- TypeScript `tsc --noEmit`
- Vitest + Testing Library

End to end:

- Playwright for the final vertical-slice demo

A feature is not implemented if its relevant tests are missing or failing.

## Security and privacy defaults

- Never commit `.env` files or secrets.
- Provide `.env.example` with placeholders only.
- Do not log raw API keys, authorization headers, or entire ticket bodies.
- V1 uses synthetic data only. Do not introduce real customer or personal data.
- Do not claim V1 is production-ready simply because it is production-like.

## Git policy

Do not commit, push, create branches, rewrite history, or open pull requests unless the user explicitly asks. You may inspect git history/status when useful.

## When to stop and ask/report

Stop rather than guessing when:

- a spec conflicts with this file;
- a dependency is missing;
- a requested change expands V1 scope materially;
- a destructive migration is required unexpectedly;
- the implementation would weaken the approval boundary;
- the implementation would make the LLM the source of truth for a metric;
- credentials or an unavailable external system are required.

Prefer a smaller, explainable implementation over additional framework complexity.
