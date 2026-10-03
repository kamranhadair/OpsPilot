---
description: Verify one OpsPilot spec against its implementation
argument-hint: [spec-number-or-name]
---

# Review Spec

Review `$ARGUMENTS` independently against the repository.

## Procedure

1. Read `CLAUDE.md`.
2. Resolve/read target spec and dependencies.
3. Inspect actual implementation; do not rely on a previous agent's summary.
4. Use the `reviewer` agent for an independent read-only review when available.
5. Run relevant tests/checks if safe and reasonably scoped.
6. Evaluate every Definition of Done item using evidence from code/tests/runtime outputs.
7. Check for out-of-scope implementation and architecture boundary violations.

## Result categories

For each requirement/DoD item use:

- `PASS`
- `PARTIAL`
- `MISSING`
- `NOT APPLICABLE`

Do not fix implementation failures as part of this command. Review first; fixes happen through the responsible implementation workflow.

## Status handling

Only if every applicable Definition of Done item passes and there are no blocking `CLAUDE.md` violations:

- update the target spec to `status: verified`.

Otherwise leave the existing status unchanged and explain why it is not verified.

## Output

### Review result
`VERIFIED` or `NOT VERIFIED`.

### Definition of Done matrix
One line per checkbox with evidence.

### Findings
Blocking/important issues with file references and recommended owner.

### Scope/architecture check
Note any future-spec work or boundary violations.

### Checks run
Commands/tests and results.

Do not commit or push.
