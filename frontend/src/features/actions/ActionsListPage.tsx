import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'

import { listActions } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import { formatUtc, humanize } from '../../lib/format'
import type { ActionListOut, ActionStatus } from '../../types/api'
import { ActionStatusBadge } from './ActionStatusBadge'

const STATUS_FILTERS: ActionStatus[] = [
  'pending_approval',
  'proposed',
  'approved',
  'rejected',
  'executing',
  'succeeded',
  'failed',
]

function ActionTable({ data }: { data: ActionListOut }) {
  if (data.items.length === 0) {
    return (
      <EmptyPanel title="No proposed actions">
        Proposals appear here after one is drafted from a validated brief.
      </EmptyPanel>
    )
  }
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-xs uppercase tracking-wide text-slate-500">
        <tr>
          <th className="py-2 pr-4 font-medium">Action</th>
          <th className="py-2 pr-4 font-medium">Status</th>
          <th className="py-2 pr-4 font-medium">Source brief</th>
          <th className="py-2 font-medium">Proposed</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {data.items.map((action) => (
          <tr key={action.id}>
            <td className="py-2 pr-4">
              <Link to={`/actions/${action.id}`} className="text-sky-700 underline">
                {action.title}
              </Link>
              <span className="block text-xs text-slate-500">{humanize(action.action_type)}</span>
            </td>
            <td className="py-2 pr-4">
              <ActionStatusBadge status={action.status} />
            </td>
            <td className="py-2 pr-4">
              <Link to={`/briefs/${action.source_brief.id}`} className="text-sky-700 underline">
                Brief #{action.source_brief.id}
              </Link>
            </td>
            <td className="py-2 text-slate-600">{formatUtc(action.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** `/actions`: proposals, pending approvals first (ordering is the backend's). */
export function ActionsListPage() {
  const [status, setStatus] = useState<ActionStatus | ''>('')
  const load = useCallback(() => listActions(status ? { status } : {}), [status])
  const { state, reload } = useApiResource(load)

  return (
    <section aria-labelledby="actions-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="actions-heading" className="text-lg font-semibold">
          Proposed actions
        </h2>
        <label className="text-sm text-slate-600">
          Status{' '}
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as ActionStatus | '')}
            className="ml-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
          >
            <option value="">All</option>
            {STATUS_FILTERS.map((value) => (
              <option key={value} value={value}>
                {humanize(value)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {state.kind === 'loading' && <LoadingPanel label="Loading actions…" />}
      {state.kind === 'error' && (
        <ErrorPanel title="Could not load actions" error={state.error} onRetry={reload} />
      )}
      {state.kind === 'success' && <ActionTable data={state.data} />}
    </section>
  )
}
