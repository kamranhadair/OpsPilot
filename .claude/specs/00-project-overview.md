---
status: verified
step: 00
title: Project Overview
owner: architect
depends_on: []
---

# Spec 00 — OpsPilot Project Overview

## Overview

OpsPilot is an AI Support Operations Command Center for a fictional B2B SaaS company. A support operations manager uses it to understand operational changes, identify the segments contributing to those changes, receive an evidence-backed AI briefing, and review an AI-proposed investigation before any action is executed.

The project is intentionally designed as an FDE-style vertical slice rather than a chatbot. It proves data integration thinking, deterministic analytics, AI grounding, human approval boundaries, evaluation, and observability.

## Business Goal

A 25-person support organization handles roughly 800–1,000 tickets per week across Billing, Technical, Integration, and Account Support queues. Operational managers currently inspect multiple reports each morning to identify spikes, SLA risk, and customer impact.

OpsPilot should reduce that manual interpretation work while preserving auditability. The system must be able to show where every important number and AI claim came from.

## Primary User

**Support Operations Manager**

Needs to:

- see current support health quickly;
- identify unusual operational changes;
- drill into the dimensions driving an anomaly;
- read a concise morning brief;
- inspect the evidence behind a claim;
- approve, edit, or reject a proposed investigation.

## Core Questions

Every analysis cycle should help answer:

1. What changed?
2. Why does it matter?
3. What should somebody do next?

## Locked V1 Workflow

```text
Synthetic support data
        ↓
Metric computation
        ↓
Deterministic anomaly detection
        ↓
Contributor analysis
        ↓
Dashboard + drilldown
        ↓
Evidence bundle
        ↓
Structured AI operations brief
        ↓
Claim validation + provenance
        ↓
AI-proposed investigation
        ↓
Human approval / edit / reject
        ↓
Mock investigation execution
        ↓
Evaluation + observability
```

## Architecture Principles

1. **Compute in code, narrate with the model.** SQL/Python produces authoritative metrics.
2. **Evidence before language.** The LLM receives only typed, computed evidence.
3. **Ground every factual claim.** Claims cite existing evidence IDs.
4. **Do not turn correlation into causation.** Related incidents are context, not proof.
5. **Human approval is mandatory.** AI never approves its own action.
6. **Make failures inspectable.** Evaluation and observability are part of the product demo.

## Fictional Domain

The dataset represents a B2B SaaS company with:

- customer tiers: Starter, Business, Enterprise;
- regions: EMEA, North America, APAC;
- support categories: Billing, Technical, Integration, Account;
- products: Billing API, Invoicing, Subscriptions, Core Platform;
- support teams aligned to those categories.

## Canonical Demo Incident

The deterministic seed must create a known event near the end of the dataset:

- a Billing API deployment is recorded on 2026-10-01;
- ticket volume rises materially afterward;
- the increase is concentrated in EMEA Enterprise Billing traffic;
- Billing SLA breach rate worsens;
- escalations and negative sentiment also rise.

The system may state that the ticket spike **coincides with** the deployment. It may not claim that the deployment **caused** the spike.

## Success Metrics for the Demo

The final demo should demonstrate:

- correct computation of the selected operational metrics;
- detection of the planted Billing anomaly;
- contributor analysis that surfaces EMEA Enterprise as a primary contributor;
- a brief whose factual claims use valid evidence IDs;
- rejection of unsupported causal wording;
- an investigation action that cannot execute before approval;
- successful mock execution after approval;
- visible LLM/tool latency and failure/cost metadata where available;
- replay/evaluation results for the known scenario.

## Locked Technology

- React + TypeScript + Vite + Tailwind CSS
- Recharts
- FastAPI + Pydantic
- PostgreSQL + SQLAlchemy 2 + Alembic
- OpenAI API
- Pytest, Vitest, Playwright
- Docker Compose

## Out of Scope for V1

- real Zendesk/Jira/Slack connections;
- production authentication/RBAC;
- multi-tenancy;
- background queues such as Celery;
- Kafka/event streaming;
- Kubernetes;
- LangGraph;
- RAG/vector search;
- a general support chatbot;
- predictive forecasting;
- model fine-tuning.

## Definition of Done

This overview is considered verified when:

- the project domain is Support Operations;
- the V1 scope above is accepted;
- the stack above is accepted;
- the canonical demo incident and evidence/approval principles are accepted.

This design has been approved and is the baseline for Specs 01–15.
