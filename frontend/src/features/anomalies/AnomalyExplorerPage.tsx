import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

import { listAnomalies } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import type { AnomalySeverity, AnomalyStatus } from '../../types/api'
import { AnomalyTable } from './AnomalyTable'

const PAGE_SIZE = 25
const SEVERITIES: AnomalySeverity[] = ['critical', 'high', 'medium', 'low']
const STATUSES: AnomalyStatus[] = ['active', 'acknowledged', 'resolved']

function oneOf<T extends string>(value: string | null, allowed: readonly T[]): T | undefined {
  return allowed.find((item) => item === value)
}

export function AnomalyExplorerPage() {
  const [params, setParams] = useSearchParams()
  const severity = oneOf(params.get('severity'), SEVERITIES)
  // Default to active anomalies; "all" removes the status filter.
  const statusParam = params.get('status')
  const status = statusParam === 'all' ? undefined : (oneOf(statusParam, STATUSES) ?? 'active')
  const offset = Math.max(0, Number.parseInt(params.get('offset') ?? '0', 10) || 0)

  const load = useCallback(
    () => listAnomalies({ severity, status, limit: PAGE_SIZE, offset }),
    [severity, status, offset],
  )
  const { state, reload } = useApiResource(load)

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'offset') next.delete('offset')
    setParams(next)
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Anomaly explorer</h2>

      <form
        aria-label="Anomaly filters"
        className="flex flex-wrap items-end gap-4 text-sm"
        onSubmit={(event) => event.preventDefault()}
      >
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate-600">Severity</span>
          <select
            value={severity ?? ''}
            onChange={(event) => update('severity', event.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1"
          >
            <option value="">All severities</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate-600">Status</span>
          <select
            value={status ?? 'all'}
            onChange={(event) => update('status', event.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
            <option value="all">All statuses</option>
          </select>
        </label>
      </form>

      {state.kind === 'loading' && <LoadingPanel label="Loading anomalies…" />}
      {state.kind === 'error' && (
        <ErrorPanel title="Anomalies unavailable" error={state.error} onRetry={reload} />
      )}
      {state.kind === 'success' &&
        (state.data.items.length === 0 ? (
          <EmptyPanel title="No anomalies match these filters">
            Run anomaly detection, or widen the filters.
          </EmptyPanel>
        ) : (
          <>
            <AnomalyTable anomalies={state.data.items} caption="Detected anomalies" />
            <nav aria-label="Pagination" className="flex items-center justify-between text-sm">
              <p className="text-slate-600">
                Showing {state.data.offset + 1}–{state.data.offset + state.data.items.length} of{' '}
                {state.data.total}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={state.data.offset === 0}
                  onClick={() => update('offset', String(Math.max(0, offset - PAGE_SIZE)))}
                  className="rounded-md border border-slate-300 bg-white px-3 py-1 disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={state.data.offset + state.data.items.length >= state.data.total}
                  onClick={() => update('offset', String(offset + PAGE_SIZE))}
                  className="rounded-md border border-slate-300 bg-white px-3 py-1 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </nav>
          </>
        ))}
    </div>
  )
}
