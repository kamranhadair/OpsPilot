---
status: implemented
step: 03
title: Synthetic Data Generator
owner: analytics-engineer
depends_on: [02]
---

# Spec 03 — Synthetic Data Generator

## Overview

Create a deterministic synthetic support dataset that behaves like a real B2B SaaS support operation and contains one deliberately planted late-period Billing anomaly. This dataset is the common source for the dashboard, analytics, evaluations, and final demo.

## Business Goal

Make the project reproducible without requiring Zendesk or real customer data, while still providing enough structure and noise to test operational analytics realistically.

## Depends On

- Spec 02 — Database and Domain Model

## Scope

Generate and persist:

- customers;
- support teams;
- 45 days of support tickets;
- normal daily/weekly variation;
- realistic response/resolution/SLA behavior;
- one Billing API deployment timeline event;
- a controlled anomalous period concentrated in EMEA Enterprise Billing traffic.

## Out of Scope

- metric computation;
- anomaly detection;
- AI generation;
- real external data imports.

## Data Window

Use a fixed reproducible demo window ending **2026-10-03 UTC**. The generator must not depend on today's wall-clock date.

Suggested start: 2026-08-20 UTC.

Use a fixed random seed stored as a named constant. Re-running from an empty database must produce the same logical dataset.

## Canonical Entities

Create representative customers across all region/tier combinations. Use obviously fictional names such as `Northstar Labs`, `Acme Cloud Demo`, or generated names that cannot be mistaken for actual customers.

Create support teams for:

- Billing Support;
- Technical Support;
- Integration Support;
- Account Support.

## Normal Behavior

Target approximately 800–1,000 tickets per normal week. Include:

- weekday/weekend volume differences;
- priority distribution dominated by P3/P4;
- higher SLA targets for lower priorities;
- category/product affinities;
- realistic but noisy first-response and resolution times;
- mostly neutral/positive sentiment with a negative tail;
- low but non-zero escalation rate.

## Planted Incident

Record a timeline event on **2026-10-01** for a Billing API deployment.

Beginning after the event and clearly visible in the final analysis window, plant these properties:

- Billing ticket volume materially above its preceding baseline (target >60% increase);
- EMEA Enterprise accounts responsible for the majority of the excess Billing volume (target >=65% of positive delta);
- Billing SLA breach rate worsening from roughly 8% baseline to roughly 16% in the anomalous window;
- escalations and negative sentiment increasing meaningfully;
- non-Billing queues retaining mostly normal variation.

The generator controls the scenario but must not write anomaly records itself.

## Architecture

Create a generator service with a small CLI entry point. Separate:

- deterministic entity creation;
- normal ticket generation;
- anomaly injection;
- incident/timeline creation;
- persistence.

Prefer explicit configuration dataclasses/Pydantic models over hidden magic constants.

## Backend Files

Create at minimum:

- `backend/app/services/demo_data/config.py`
- `backend/app/services/demo_data/generator.py`
- `backend/app/scripts/seed_demo.py`
- `backend/tests/demo_data/test_generator.py`

## CLI

Support:

```bash
python -m app.scripts.seed_demo
python -m app.scripts.seed_demo --reset
```

Without `--reset`, repeated execution must not duplicate demo records. `--reset` may delete only known synthetic/demo data and must clearly refuse to run in a production environment.

## New Dependencies

Use Python standard library randomness unless an existing dependency is clearly needed. Do not add Faker solely for cosmetic names.

## Implementation Rules

- Fixed seed and fixed date window.
- No current-time-derived fixture dates.
- No real names, emails, customer IDs, or support ticket text.
- Keep the anomalous signal strong enough for deterministic evaluation but include noise so the charts are not perfectly artificial.
- Store the deployment as an `incidents` evidence record (`EVT-*`).
- Generator must not precompute metrics, anomalies, contributors, briefs, or actions.

## Error and Edge Cases

- database already contains the same seed version;
- `--reset` attempted outside demo/development;
- interrupted seed transaction;
- generated ticket references collide.

## Testing Requirements

Tests must verify deterministic invariants, including:

- same seed -> same record counts and selected aggregate checksums;
- all region/tier/category values represented;
- anomalous Billing window materially exceeds baseline;
- EMEA Enterprise dominates excess Billing traffic;
- Billing SLA breach rate worsens materially;
- non-Billing volume does not receive the same planted spike;
- repeated non-reset seed is idempotent.

## Definition of Done

- [ ] A clean database can be seeded with one command.
- [ ] Seed is deterministic and idempotent.
- [ ] Dataset covers the fixed 45-day demo window.
- [ ] Billing API deployment event exists.
- [ ] Planted Billing anomaly satisfies documented invariants.
- [ ] No anomaly/metric/brief records are generated by the seed.
- [ ] `--reset` is blocked outside demo/development.
- [ ] Generator tests pass.
