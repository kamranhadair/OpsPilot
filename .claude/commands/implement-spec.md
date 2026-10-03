---
description: Implement one approved OpsPilot spec end to end
argument-hint: [spec-number-or-name]
---

# Implement Spec

Implement exactly one OpsPilot spec: `$ARGUMENTS`.

## Mandatory preparation

1. Read `CLAUDE.md` completely.
2. Resolve and read the target spec under `.claude/specs/`.
3. Read every dependency listed in `depends_on`.
4. If target status is `verified`, stop: it has already been verified. Ask before reworking it.
5. If any dependency is not at least `implemented`, stop and report the unmet dependency.
6. Inspect the existing implementation before creating files/abstractions.
7. If the spec conflicts with `CLAUDE.md`, stop and report the conflict.

## Status handling

- Change target spec `status: planned` to `status: in_progress` when implementation actually begins.
- Do not change a dependency's status.
- Never set `verified`.

## Implementation

Follow the target spec's owner/domain. Use the relevant project agent where available:

- architecture/cross-cutting -> `architect`
- backend/data model/API -> `backend-engineer`
- metrics/anomalies/contributors/seed -> `analytics-engineer`
- React/UI -> `frontend-engineer`
- model/evidence/prompt -> `ai-engineer`

The main session remains responsible for coordination. Do not allow agents to broaden scope.

Implement only the active spec. Do not opportunistically implement later specs.

## Tests and checks

Add/update all tests required by the spec. Run the narrowest relevant checks first, then broader checks that are reasonable for the changed area.

Expected project gates when applicable:

- backend: Pytest, Ruff, Mypy;
- frontend: Vitest, ESLint, TypeScript check;
- migrations: upgrade/downgrade or migration sanity;
- Docker config when infrastructure changes.

## Definition of Done

Walk every Definition of Done checkbox. Do not claim an item passed unless you actually verified it.

If all applicable items pass, set `status: implemented`.

If implementation or required checks remain incomplete, leave `status: in_progress` and report exactly what remains.

## Final response

Report:

- spec implemented;
- files created/changed;
- migrations/dependencies added;
- tests/checks run with results;
- Definition of Done summary;
- remaining failures/risks;
- confirmation that future-spec scope was not implemented.

Do not commit or push unless the user separately asks.
