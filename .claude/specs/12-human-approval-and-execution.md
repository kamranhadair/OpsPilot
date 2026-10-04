---
status: implemented
step: 12
title: Human Approval and Execution
owner: backend-engineer
depends_on: [11]
---

# Spec 12 — Human Approval and Execution

## Overview

Implement the human-in-the-loop boundary for proposed investigations and execute approved actions through a mock integration adapter. This is the control layer that prevents the AI from acting autonomously.

## Business Goal

Demonstrate a complete operational action loop in which a human can review/edit/reject a proposal and execution is impossible without recorded approval.

## Depends On

- Spec 11 — Action Proposal

## Scope

- approval/rejection endpoints;
- optional human edits to action title/description/investigation details;
- explicit execution endpoint;
- `MockInvestigationAdapter`;
- action state machine enforcement;
- audit log for each transition;
- frontend approval controls and execution outcome.

## Out of Scope

- real Jira/Slack integration;
- production authentication/RBAC;
- AI self-approval;
- background job queue.

## State Machine

Allowed path:

```text
proposed
  -> pending_approval
      -> approved -> executing -> succeeded | failed
      -> rejected
```

No other state transition is valid unless explicitly documented in this spec.

## Human Identity in V1

Because production authentication is out of scope, approval requests must still contain a demo reviewer identity string (for example `Operations Manager`) and record it in `approvals`/audit log. Do not pretend this is production-grade identity assurance.

## API Changes

### `POST /api/actions/{action_id}/approve`

Request may include:

- reviewer;
- comment;
- approved edited title/description payload.

Creates approval record and moves action to `approved`.

### `POST /api/actions/{action_id}/reject`

Creates rejection record and moves action to `rejected`.

### `POST /api/actions/{action_id}/execute`

Backend checks:

1. action exists;
2. action status is approved (or safe idempotent succeeded replay);
3. human approval record exists;
4. action type is allow-listed;
5. correct adapter is selected.

Then executes via adapter and records `action_executions`.

## Integration Boundary

Define an interface/protocol such as:

```text
InvestigationAdapter.create_investigation(action_payload) -> ExecutionResult
```

Implement `MockInvestigationAdapter` that returns a deterministic external reference such as `INV-0001` and stores no external side effects.

The action service must not know Jira-specific APIs.

## Idempotency

Executing an already-succeeded action must not create a second mock investigation. Return the existing successful execution or a stable idempotent response.

Concurrent/double approval should not create duplicate approval decisions.

## Frontend Changes

Action detail supports:

- edit proposal fields before approval;
- Approve;
- Reject;
- after approval, Execute / "Approve & Create" UX may call approval then execution sequentially but must preserve two backend transitions;
- display external mock reference and audit timeline.

## Architecture

Suggested:

- `backend/app/services/actions/state_machine.py`
- `backend/app/services/actions/approval_service.py`
- `backend/app/services/actions/execution_service.py`
- `backend/app/integrations/investigations/base.py`
- `backend/app/integrations/investigations/mock.py`
- action routes/UI updates

## Database Changes

Use `approvals`, `action_executions`, `audit_logs`. Add uniqueness constraints if needed to guarantee one terminal human decision/execution semantics.

## New Dependencies

No new dependency.

## Implementation Rules

- AI/system actor cannot create an approval record.
- Execution must fail closed without approval.
- Human edits are recorded, not silently overwrite history.
- Every transition appends an audit event.
- Adapter errors produce `failed` execution with safe error detail.
- Never treat frontend-disabled buttons as the security boundary; backend enforces state.

## Error and Edge Cases

- approve rejected action;
- reject approved action;
- execute pending action;
- execute twice;
- adapter failure;
- missing reviewer;
- stale UI submits a transition after another user/process changed state.

## Testing Requirements

- pending action cannot execute (`409` or appropriate typed error);
- approval creates human decision record;
- rejection blocks execution;
- approved action executes once;
- second execution is idempotent;
- adapter failure recorded;
- audit events exist in correct order;
- UI approval/rejection/execution flow tests.

## Definition of Done

- [ ] Backend state machine enforces allowed transitions.
- [ ] Human approval is mandatory before execution.
- [ ] AI/system cannot approve itself.
- [ ] Mock adapter returns a visible investigation reference.
- [ ] Execution is idempotent.
- [ ] Human edits and decisions are audited.
- [ ] UI supports review, approve/edit/reject, and execution outcome.
- [ ] Approval boundary tests pass.
