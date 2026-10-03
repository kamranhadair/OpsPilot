---
description: Plan an OpsPilot spec without editing code
argument-hint: [spec-number-or-name]
allowed-tools: Read, Grep, Glob
---

# Plan Spec

Plan implementation for `$ARGUMENTS` without modifying repository files.

## Procedure

1. Read `CLAUDE.md` completely.
2. Resolve the target file under `.claude/specs/` from the supplied number/name.
3. Read the entire target spec and every `depends_on` spec.
4. Inspect relevant existing code/files with Read/Grep/Glob.
5. Verify dependency statuses. If a required dependency is not at least `implemented`, stop and report it.
6. Identify:
   - required behavior;
   - files likely created/changed;
   - database/API changes;
   - tests required;
   - quality checks;
   - risks/edge cases;
   - explicit out-of-scope items to avoid.
7. Check whether the plan conflicts with `CLAUDE.md`. If yes, stop and surface the conflict.

## Output

Return:

### Spec
Target spec path, status, owner, dependencies.

### Implementation plan
Ordered steps with responsible layer/agent suggestions.

### File plan
Files to create/change and why.

### Test plan
Concrete tests mapped to Definition of Done.

### Risks / decisions
Only real ambiguities or blockers.

### Scope guard
List the important things this implementation must **not** build yet.

Do not edit code, specs, status, or configuration in this command.
