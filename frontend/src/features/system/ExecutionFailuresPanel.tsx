import { Link } from 'react-router-dom'

import type { ResourceState } from '../../api/useApiResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import { formatUtc } from '../../lib/format'
import type { ExecutionSummary } from '../../types/api'

function Failures({ executions }: { executions: ExecutionSummary }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">
        {executions.total} executions · {executions.succeeded} succeeded · {executions.failed}{' '}
        failed
      </p>
      {executions.recent_failures.length === 0 ? (
        <EmptyPanel title="No execution failures" />
      ) : (
        <ul aria-label="Recent execution failures" className="divide-y divide-slate-100 text-sm">
          {executions.recent_failures.map((failure) => (
            <li key={failure.execution_id} className="py-2">
              <div className="flex flex-wrap items-baseline gap-x-3">
                <Link to={`/actions/${failure.action_id}`} className="text-sky-700 underline">
                  Action #{failure.action_id}
                </Link>
                <span className="font-mono text-xs text-red-700">
                  {failure.error_code ?? 'error code not reported'}
                </span>
                <span className="text-xs text-slate-500">
                  {failure.adapter_key} · execution #{failure.execution_id} · started{' '}
                  {formatUtc(failure.started_at)}
                  {failure.finished_at !== null && ` · finished ${formatUtc(failure.finished_at)}`}
                </span>
              </div>
              {failure.error_message && (
                <p className="mt-0.5 text-slate-700">{failure.error_message}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Recent action execution failures from the backend summary for the selected period. */
export function ExecutionFailuresPanel({
  state,
  reload,
}: {
  state: ResourceState<{ executions: ExecutionSummary }>
  reload: () => void
}) {
  return (
    <section
      aria-labelledby="execution-failures-heading"
      className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
    >
      <h3 id="execution-failures-heading" className="text-base font-semibold">
        Action execution failures
      </h3>
      <div className="mt-4">
        {state.kind === 'loading' && <LoadingPanel label="Loading execution summary…" />}
        {state.kind === 'error' && (
          <ErrorPanel
            title="Could not load the execution summary"
            error={state.error}
            onRetry={reload}
          />
        )}
        {state.kind === 'success' && <Failures executions={state.data.executions} />}
      </div>
    </section>
  )
}
