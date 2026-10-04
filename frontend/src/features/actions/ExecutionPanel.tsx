import { formatUtc, humanize } from '../../lib/format'
import type { ActionDetailOut, ApprovalOut, ExecutionOut } from '../../types/api'
import type { ActionMutation } from './mutations'

function Decision({ approval }: { approval: ApprovalOut }) {
  const approved = approval.decision === 'approved'
  return (
    <div
      className={`rounded-md border p-3 text-sm ${
        approved ? 'border-sky-200 bg-sky-50' : 'border-slate-300 bg-slate-50'
      }`}
    >
      <p className="font-medium text-slate-900">
        {approved ? 'Approved' : 'Rejected'} by {approval.reviewer}
      </p>
      <p className="text-xs text-slate-500">{formatUtc(approval.decided_at)}</p>
      {approval.comment && <p className="mt-1 text-slate-700">“{approval.comment}”</p>}
      {approved && (
        <p className="mt-1 text-xs text-slate-600">
          {approval.edited_fields.length > 0
            ? `Human edits before approval: ${approval.edited_fields.map(humanize).join(', ')}`
            : 'Approved without edits.'}
        </p>
      )}
      {!approved && (
        <p className="mt-1 text-xs text-slate-600">
          Rejected actions are never executed.
        </p>
      )}
    </div>
  )
}

function Execution({ execution }: { execution: ExecutionOut }) {
  if (execution.status === 'succeeded') {
    return (
      <div role="status" className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm">
        <p className="text-xs font-medium uppercase tracking-wide text-emerald-800">
          Mock investigation created
        </p>
        <p className="mt-1 font-mono text-2xl font-semibold text-emerald-900">
          {execution.external_ref ?? 'No reference returned'}
        </p>
        <p className="mt-1 text-xs text-slate-600">
          Created by the {execution.adapter_key} adapter
          {execution.finished_at ? ` at ${formatUtc(execution.finished_at)}` : ''}. This is a
          mock reference; no external system was contacted.
        </p>
      </div>
    )
  }
  if (execution.status === 'failed') {
    return (
      <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm">
        <p className="font-medium text-red-800">Execution failed</p>
        <p className="mt-1 text-slate-700">
          {execution.error_message ?? 'The adapter reported a failure without detail.'}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          {execution.adapter_key} adapter · started {formatUtc(execution.started_at)}
        </p>
      </div>
    )
  }
  return (
    <p role="status" className="rounded-md border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
      Execution in progress via the {execution.adapter_key} adapter (started{' '}
      {formatUtc(execution.started_at)}).
    </p>
  )
}

/**
 * The recorded human decision, the execution outcome, and the execute control. The
 * control appears only when the backend lists `execute` in `allowed_operations`.
 */
export function ExecutionPanel({
  action,
  busy,
  onExecute,
}: {
  action: ActionDetailOut
  busy: ActionMutation | null
  onExecute: () => void
}) {
  const canExecute = action.allowed_operations.includes('execute')
  if (!action.approval && !action.execution && !canExecute) return null

  return (
    <section
      aria-labelledby="action-outcome-heading"
      className="space-y-3 rounded-lg border border-slate-200 bg-white p-4"
    >
      <h3 id="action-outcome-heading" className="font-medium text-slate-800">
        Decision and execution
      </h3>
      {action.approval && <Decision approval={action.approval} />}
      {action.execution && <Execution execution={action.execution} />}
      {canExecute && (
        <div className="space-y-1">
          <button
            type="button"
            onClick={onExecute}
            disabled={busy !== null}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {busy === 'execute' || busy === 'approve_execute'
              ? 'Creating investigation…'
              : 'Create investigation'}
          </button>
          <p className="text-xs text-slate-500">
            Opens a mock investigation through the configured adapter. No real ticketing
            system is contacted in V1.
          </p>
        </div>
      )}
    </section>
  )
}
