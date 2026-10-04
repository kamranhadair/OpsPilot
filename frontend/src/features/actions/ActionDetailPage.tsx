import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  ApiError,
  NETWORK_ERROR_CODE,
  approveAction,
  executeAction,
  getAction,
  rejectAction,
} from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { EvidenceId } from '../../components/EvidenceId'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import { formatUtc, humanize } from '../../lib/format'
import type {
  ActionDetailOut,
  ApproveActionRequest,
  RejectActionRequest,
} from '../../types/api'
import { ProvenanceDrawer } from '../evidence/ProvenanceDrawer'
import { ActionStatusBadge } from './ActionStatusBadge'
import { AuditTimeline } from './AuditTimeline'
import { ExecutionPanel } from './ExecutionPanel'
import type { ActionMutation } from './mutations'
import { ReviewPanel } from './ReviewPanel'

function AwaitingApproval() {
  return (
    <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm">
      <p className="font-medium text-amber-900">Awaiting human approval</p>
      <p className="mt-1 text-amber-900">
        This investigation was drafted by AI and has not been approved or executed. Nothing
        has been opened in any external system. It can only be executed after a human
        reviewer records an approval below.
      </p>
    </div>
  )
}

/** Errors that mean the displayed state is stale; the page reloads the action. */
const RELOAD_CODES = new Set(['ACTION_INVALID_TRANSITION', 'ACTION_EXECUTION_FAILED'])

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError('Unexpected client error.', 0, NETWORK_ERROR_CODE, { cause: error })
}

function MutationFeedback({ error }: { error: ApiError }) {
  if (error.code === 'ACTION_INVALID_TRANSITION') {
    return (
      <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm">
        <p className="font-medium text-amber-900">This action changed since you loaded it</p>
        <p className="mt-1 text-slate-700">{error.message}</p>
        <p className="mt-1 text-slate-700">The latest state has been reloaded.</p>
        <p className="mt-1 font-mono text-xs text-slate-500">{error.code}</p>
      </div>
    )
  }
  const title =
    error.code === 'ACTION_EXECUTION_FAILED'
      ? 'The investigation could not be created'
      : error.code === 'ACTION_EDIT_REJECTED'
        ? 'Your edits were not accepted'
        : 'The request was not completed'
  return (
    <div className="space-y-2">
      <ErrorPanel title={title} error={error} />
      {error.body?.issues && error.body.issues.length > 0 && (
        <ul aria-label="Edit issues" className="list-disc pl-5 text-sm text-red-800">
          {error.body.issues.map((issue, index) => (
            <li key={index}>
              <span className="font-mono text-xs">{issue.code}</span>
              {issue.field ? ` (${humanize(issue.field)})` : ''}: {issue.message}
              {issue.phrase ? ` — “${issue.phrase}”` : ''}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface ActionControls {
  busy: ActionMutation | null
  onApprove: (body: ApproveActionRequest) => void
  onReject: (body: RejectActionRequest) => void
  onApproveAndExecute: (body: ApproveActionRequest) => void
  onExecute: () => void
}

function ActionView({ action, controls }: { action: ActionDetailOut; controls: ActionControls }) {
  const showReview =
    action.allowed_operations.includes('approve') || action.allowed_operations.includes('reject')

  const [selected, setSelected] = useState<string | null>(null)
  const close = useCallback(() => setSelected(null), [])

  return (
    <article aria-labelledby="action-title" className="space-y-4">
      <header>
        <p className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span>
            Action #{action.id} · {humanize(action.action_type)} · proposed{' '}
            {formatUtc(action.created_at)}
          </span>
          <ActionStatusBadge status={action.status} />
        </p>
        <h2 id="action-title" className="mt-1 text-xl font-semibold">
          {action.title}
        </h2>
      </header>

      {action.status === 'pending_approval' && <AwaitingApproval />}

      <section aria-label="Description">
        <h3 className="font-medium text-slate-800">Description</h3>
        <p className="mt-1 text-sm text-slate-700">{action.description}</p>
      </section>
      <section aria-label="Rationale">
        <h3 className="font-medium text-slate-800">Rationale</h3>
        <p className="mt-1 text-sm text-slate-700">{action.rationale}</p>
      </section>
      <section aria-label="Suggested investigation steps">
        <h3 className="font-medium text-slate-800">Suggested investigation steps</h3>
        <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm text-slate-700">
          {action.investigation_steps.map((step, index) => (
            <li key={index}>{step}</li>
          ))}
        </ol>
      </section>
      <section aria-label="Evidence">
        <h3 className="font-medium text-slate-800">Evidence</h3>
        <p className="mt-1 flex flex-wrap items-center gap-1">
          {action.evidence_ids.map((id, index) => (
            <EvidenceId key={`${id}-${index}`} id={id} onSelect={setSelected} />
          ))}
        </p>
      </section>
      <section aria-label="Source brief" className="text-sm">
        <h3 className="font-medium text-slate-800">Source brief</h3>
        <p className="mt-1">
          <Link to={`/briefs/${action.source_brief.id}`} className="text-sky-700 underline">
            Brief #{action.source_brief.id}: {action.source_brief.headline}
          </Link>{' '}
          <span className="text-xs text-slate-500">({humanize(action.source_brief.status)})</span>
        </p>
      </section>
      {showReview && (
        <ReviewPanel
          key={`${action.id}-${action.updated_at}`}
          action={action}
          busy={controls.busy}
          onApprove={controls.onApprove}
          onReject={controls.onReject}
          onApproveAndExecute={controls.onApproveAndExecute}
        />
      )}
      <ExecutionPanel action={action} busy={controls.busy} onExecute={controls.onExecute} />
      <AuditTimeline events={action.audit_events} />
      {selected && <ProvenanceDrawer evidenceId={selected} onClose={close} />}
    </article>
  )
}

function ActionLoader({ actionId }: { actionId: number }) {
  const load = useCallback(() => getAction(actionId), [actionId])
  const { state, reload } = useApiResource(load)
  // The detail returned by the latest successful transition replaces the loaded data.
  const [latest, setLatest] = useState<ActionDetailOut | null>(null)
  const [busy, setBusy] = useState<ActionMutation | null>(null)
  const [feedback, setFeedback] = useState<ApiError | null>(null)

  /** Run backend transitions in order; stop at the first failure. */
  async function run(kind: ActionMutation, steps: Array<() => Promise<ActionDetailOut>>) {
    setBusy(kind)
    setFeedback(null)
    try {
      for (const step of steps) {
        setLatest(await step())
      }
    } catch (error) {
      const apiError = toApiError(error)
      setFeedback(apiError)
      if (RELOAD_CODES.has(apiError.code)) {
        setLatest(null)
        reload()
      }
    } finally {
      setBusy(null)
    }
  }

  const controls: ActionControls = {
    busy,
    onApprove: (body) => void run('approve', [() => approveAction(actionId, body)]),
    onReject: (body) => void run('reject', [() => rejectAction(actionId, body)]),
    // Two separate backend transitions: approval, then execution only if approval succeeded.
    onApproveAndExecute: (body) =>
      void run('approve_execute', [
        () => approveAction(actionId, body),
        () => executeAction(actionId),
      ]),
    onExecute: () => void run('execute', [() => executeAction(actionId)]),
  }

  let content
  if (state.kind === 'loading') {
    content = <LoadingPanel label="Loading action…" />
  } else if (state.kind === 'error') {
    content =
      state.error.code === 'ACTION_NOT_FOUND' ? (
        <EmptyPanel title="Action not found">{state.error.message}</EmptyPanel>
      ) : (
        <ErrorPanel title="Could not load the action" error={state.error} onRetry={reload} />
      )
  } else {
    content = <ActionView action={latest ?? state.data} controls={controls} />
  }

  return (
    <div className="space-y-4">
      {feedback && <MutationFeedback error={feedback} />}
      {content}
    </div>
  )
}

/**
 * `/actions/:actionId`: one proposal, its evidence, the human review controls, the execution
 * outcome and the audit timeline. Which controls appear is decided solely by the backend's
 * `allowed_operations`; the backend re-checks every transition.
 */
export function ActionDetailPage() {
  const { actionId } = useParams()
  const id = Number(actionId)
  return (
    <div className="space-y-4">
      <Link to="/actions" className="text-sm text-sky-700 underline">
        All proposed actions
      </Link>
      {Number.isInteger(id) && id > 0 ? (
        <ActionLoader actionId={id} />
      ) : (
        <EmptyPanel title="Action not found">{`"${actionId ?? ''}" is not an action ID.`}</EmptyPanel>
      )}
    </div>
  )
}
