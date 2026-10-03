---
description: Audit OpsPilot architecture and FDE boundaries
allowed-tools: Read, Grep, Glob
---

# Review Architecture

Perform a read-only architecture audit of the current OpsPilot repository using the `architect` agent where available.

## Required context

Read:

- `CLAUDE.md`;
- Spec 00;
- all specs whose status is `implemented` or `verified`;
- enough code to validate the actual architecture.

## Check specifically

- LLM calculating authoritative metrics;
- severity/business thresholds leaking into React;
- analytics logic embedded in API routes;
- raw ticket data entering the brief model;
- evidence IDs not validated;
- unsupported causation accepted;
- action approval/execution bypasses;
- external provider calls scattered outside adapters;
- future-spec functionality implemented early;
- unnecessary infrastructure/dependencies;
- migration/data-model inconsistencies;
- idempotency gaps in seed/analysis/action execution.

## Output

Return:

1. architecture map of the implemented flow;
2. blocking findings;
3. important findings;
4. advisory simplifications;
5. scope drift;
6. final result: `ARCHITECTURE OK` or `CHANGES REQUIRED`.

Do not edit files.
