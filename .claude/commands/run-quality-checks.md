---
description: Run OpsPilot repository quality gates
---

# Run Quality Checks

Run the applicable repository quality gates without changing product behavior.

## Backend

When backend exists, run the configured equivalents of:

1. Pytest
2. Ruff check
3. Ruff format check if configured
4. Mypy for the application package
5. Alembic migration sanity/current-head check when database migrations exist

Use project-defined commands/scripts from `pyproject.toml`/README rather than inventing incompatible flags.

## Frontend

When frontend exists, run configured equivalents of:

1. Vitest in non-watch mode
2. ESLint
3. TypeScript `tsc --noEmit` / project `typecheck` script
4. production build if the spec/change warrants it

## Infrastructure

When Compose exists:

- run `docker compose config` or equivalent syntax validation.

## Rules

- Do not rewrite code automatically just to make checks pass unless the user specifically asked for fixes.
- Do not hide pre-existing failures; distinguish them from new failures when possible.
- If a tool/script is not yet present because an earlier spec has not implemented it, report `NOT AVAILABLE`, not pass.

## Output

Provide a compact table:

| Check | Status | Notes |
|---|---|---|

Then list failing commands/errors with enough detail to act on them.
