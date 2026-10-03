---
status: implemented
step: 02
title: Database and Domain Model
owner: backend-engineer
depends_on: [01]
---

# Spec 02 — Database and Domain Model

## Overview

Create the PostgreSQL domain schema required by the full OpsPilot V1 workflow. This spec establishes stable persistence boundaries early so later specs can add behavior without inventing fields ad hoc.

## Business Goal

Persist operational data, computed evidence, AI outputs, approvals, execution results, traces, and audit events in a way that supports a complete and inspectable demo.

## Depends On

- Spec 01 — Foundation and Development Environment

## Scope

Create SQLAlchemy models, Alembic migration(s), enums, repository primitives, indexes, and basic model tests for:

- `customers`
- `support_teams`
- `tickets`
- `incidents`
- `metric_snapshots`
- `anomalies`
- `anomaly_contributors`
- `briefs`
- `brief_claims`
- `proposed_actions`
- `approvals`
- `action_executions`
- `llm_traces`
- `audit_logs`

## Out of Scope

- seed generation;
- metric formulas;
- anomaly logic;
- AI calls;
- frontend UI.

## Domain Model

### `customers`

Required fields:

- integer primary key;
- stable `customer_ref` unique string;
- `name`;
- `tier`: `starter | business | enterprise`;
- `region`: `emea | north_america | apac`;
- `active` boolean;
- UTC timestamps.

### `support_teams`

- integer primary key;
- unique `team_key`;
- display `name`;
- UTC timestamps.

### `tickets`

Required operational fields:

- integer primary key;
- unique `ticket_ref`;
- `customer_id` FK;
- `support_team_id` FK;
- `created_at`, `resolved_at` nullable;
- `priority`: `p1 | p2 | p3 | p4`;
- `status`: `open | pending | solved | closed`;
- `channel`: `email | web | api | chat`;
- `category`: `billing | technical | integration | account`;
- `product`: `billing_api | invoicing | subscriptions | core_platform`;
- `first_response_minutes` nullable;
- `resolution_minutes` nullable;
- `sla_target_minutes`;
- `sla_breached` boolean;
- `sentiment_score` numeric in `[-1, 1]`;
- `escalated` boolean;
- optional short synthetic `subject` for drilldown only.

### `incidents`

- integer primary key;
- unique evidence ID with `EVT-` prefix;
- `event_type` such as `deployment` or `incident`;
- `title`;
- `occurred_at`;
- optional `product`;
- `metadata_json` JSONB;
- UTC timestamps.

### `metric_snapshots`

- integer primary key;
- unique evidence ID with `MTR-` prefix;
- `metric_key`;
- `window_start`, `window_end`;
- `baseline_start`, `baseline_end`;
- `dimensions_json` JSONB;
- `value` numeric;
- `baseline_value` nullable numeric;
- `change_pct` nullable numeric;
- `sample_size` integer;
- `provenance_json` JSONB;
- `computed_at`.

### `anomalies`

- integer primary key;
- unique evidence ID with `ANOM-` prefix;
- FK to metric snapshot;
- `detector_key`;
- `severity`: `low | medium | high | critical`;
- `score` nullable numeric;
- `threshold_json` JSONB;
- `status`: `active | acknowledged | resolved`;
- `detected_at`.

### `anomaly_contributors`

- integer primary key;
- unique evidence ID with `SEG-` prefix;
- FK to anomaly;
- `dimension_key`;
- `segment_value`;
- `current_value` numeric;
- `baseline_value` numeric;
- `delta_value` numeric;
- `contribution_pct` numeric;
- `rank` integer;
- `provenance_json` JSONB.

### `briefs`

- integer primary key;
- `analysis_window_start`, `analysis_window_end`;
- `headline`;
- `summary`;
- `status`: `draft | valid | invalid`;
- `model_name`;
- `validation_errors_json` JSONB;
- UTC timestamps.

### `brief_claims`

- integer primary key;
- FK to brief;
- `ordinal`;
- `claim_type`: `observation | inference`;
- `text`;
- `evidence_ids_json` JSONB array of strings;
- `validation_status`: `pending | valid | invalid`;
- `validation_errors_json` JSONB.

### `proposed_actions`

- integer primary key;
- FK to validated brief;
- `action_type` (V1 allow-list contains `open_investigation` only);
- `title`;
- `description`;
- `rationale`;
- `evidence_ids_json` JSONB;
- `status`: `proposed | pending_approval | approved | rejected | executing | succeeded | failed`;
- UTC timestamps.

### `approvals`

- integer primary key;
- FK to action;
- `decision`: `approved | rejected`;
- `reviewer` string;
- optional `comment`;
- optional `edited_payload_json`;
- `decided_at`.

### `action_executions`

- integer primary key;
- FK to action;
- `adapter_key`;
- optional `external_ref`;
- `status`: `executing | succeeded | failed`;
- `request_json`, `response_json` JSONB;
- optional `error_message`;
- start/end timestamps.

### `llm_traces`

- integer primary key;
- optional FK to brief;
- `operation`;
- `model_name`;
- `latency_ms`;
- nullable `input_tokens`, `output_tokens`, `estimated_cost_usd`;
- `status`: `success | error`;
- optional `error_code`, `error_message`;
- `created_at`.

### `audit_logs`

Append-only record with:

- integer primary key;
- `actor_type`: `human | system | ai`;
- optional `actor_id`;
- `event_type`;
- `entity_type`;
- `entity_id` string;
- `payload_json` JSONB;
- `created_at`.

## Architecture

Models belong in `backend/app/models/`. Keep repository helpers in `backend/app/repositories/`; routes must not build raw SQL.

Provide a shared evidence-ID allocator/service that creates unique prefixed IDs. Do not derive externally visible evidence IDs from database primary keys in the frontend.

## Database Changes

Create one initial domain migration if practical. Add indexes at minimum for:

- ticket `created_at`;
- ticket `category` + `created_at`;
- ticket `product` + `created_at`;
- ticket `customer_id` + `created_at`;
- ticket `support_team_id` + `created_at`;
- ticket `sla_breached` + `created_at`;
- metric `metric_key` + `window_end`;
- anomaly `status` + `detected_at`;
- unique evidence IDs.

## Backend Files

Create/update:

- `backend/app/db/base.py`
- `backend/app/models/*.py`
- `backend/app/repositories/*.py` as required for basic persistence
- `backend/alembic/versions/<revision>_domain_model.py`
- model/repository tests

## New Dependencies

No new runtime dependency beyond Spec 01.

## Implementation Rules

- All timestamps are timezone-aware UTC.
- JSON fields use PostgreSQL JSONB.
- Use named Python enums or constrained strings consistently; do not scatter magic status literals.
- Foreign keys must have explicit on-delete behavior.
- Audit logs are append-only through application code.
- Do not store raw OpenAI requests containing secrets.
- Synthetic ticket subjects must never contain real customer data.

## Error and Edge Cases

- duplicate evidence IDs;
- duplicate customer/ticket refs;
- impossible sentiment values;
- resolved time before created time;
- orphan contributor/action records;
- action status outside defined state set.

## Testing Requirements

- migration upgrades a clean database;
- migration downgrades cleanly;
- key uniqueness/foreign-key constraints are tested;
- enum/check constraints reject invalid states where implemented;
- repository round-trip tests cover JSONB evidence arrays/provenance.

## Definition of Done

- [ ] All listed tables exist through Alembic.
- [ ] Core indexes and unique constraints exist.
- [ ] Evidence IDs are unique and prefixed by evidence type.
- [ ] SQLAlchemy models use 2.x typed mappings.
- [ ] No application startup `create_all()` bypass exists.
- [ ] Upgrade/downgrade migration test passes.
- [ ] Model/repository tests pass.
- [ ] Ruff and Mypy pass for new backend code.
