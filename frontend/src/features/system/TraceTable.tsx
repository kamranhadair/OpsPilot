import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'

import { listLlmTraces } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import { formatLatencyMs, formatTokens, formatUsd, formatUtc, humanize } from '../../lib/format'
import type { LLMTraceListOut } from '../../types/api'
import { SystemStatusBadge } from './SystemStatusBadge'

const TRACE_PAGE_SIZE = 25

function Rows({ data }: { data: LLMTraceListOut }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="py-2 pr-4 font-medium">Time</th>
            <th className="py-2 pr-4 font-medium">Operation</th>
            <th className="py-2 pr-4 font-medium">Model</th>
            <th className="py-2 pr-4 font-medium">Status</th>
            <th className="py-2 pr-4 font-medium">Latency</th>
            <th className="py-2 pr-4 font-medium">Input tokens</th>
            <th className="py-2 pr-4 font-medium">Output tokens</th>
            <th className="py-2 pr-4 font-medium">Cost</th>
            <th className="py-2 pr-4 font-medium">Error</th>
            <th className="py-2 font-medium">Context</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data.items.map((trace) => (
            <tr key={trace.id} className="align-top">
              <td className="py-2 pr-4 whitespace-nowrap text-slate-600">
                {formatUtc(trace.created_at)}
              </td>
              <td className="py-2 pr-4">{humanize(trace.operation)}</td>
              <td className="py-2 pr-4 font-mono text-xs">{trace.model_name}</td>
              <td className="py-2 pr-4">
                <SystemStatusBadge status={trace.status} />
              </td>
              <td className="py-2 pr-4 whitespace-nowrap">{formatLatencyMs(trace.latency_ms)}</td>
              <td className="py-2 pr-4">{formatTokens(trace.input_tokens)}</td>
              <td className="py-2 pr-4">{formatTokens(trace.output_tokens)}</td>
              <td className="py-2 pr-4">{formatUsd(trace.estimated_cost_usd)}</td>
              <td className="py-2 pr-4">
                {trace.error_code !== null && (
                  <span className="block font-mono text-xs text-red-700">{trace.error_code}</span>
                )}
                {trace.error_message !== null && (
                  <span className="block text-xs text-slate-600">{trace.error_message}</span>
                )}
              </td>
              <td className="py-2 whitespace-nowrap">
                {trace.brief_id !== null && (
                  <Link to={`/briefs/${trace.brief_id}`} className="block text-sky-700 underline">
                    Brief #{trace.brief_id}
                  </Link>
                )}
                {trace.action_id !== null && (
                  <Link
                    to={`/actions/${trace.action_id}`}
                    className="block text-sky-700 underline"
                  >
                    Action #{trace.action_id}
                  </Link>
                )}
                {trace.request_id !== null && (
                  <span className="block font-mono text-xs text-slate-500">
                    {trace.request_id}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Recent LLM trace metadata, paginated by the backend. */
export function TraceTable() {
  const [offset, setOffset] = useState(0)
  const load = useCallback(
    () => listLlmTraces({ limit: TRACE_PAGE_SIZE, offset }),
    [offset],
  )
  const { state, reload } = useApiResource(load)

  return (
    <section
      aria-labelledby="traces-heading"
      className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
    >
      <h3 id="traces-heading" className="text-base font-semibold">
        Recent LLM traces
      </h3>
      <div className="mt-4">
        {state.kind === 'loading' && <LoadingPanel label="Loading LLM traces…" />}
        {state.kind === 'error' && (
          <ErrorPanel title="Could not load LLM traces" error={state.error} onRetry={reload} />
        )}
        {state.kind === 'success' && state.data.items.length === 0 && (
          <EmptyPanel title="No LLM traces recorded">
            {state.data.offset > 0
              ? 'There are no traces on this page.'
              : 'Traces appear after a brief or action proposal is generated.'}
          </EmptyPanel>
        )}
        {state.kind === 'success' && state.data.items.length > 0 && <Rows data={state.data} />}
        {state.kind === 'success' && (
          <nav
            aria-label="Trace pages"
            className="mt-3 flex items-center justify-between text-sm text-slate-600"
          >
            <span>
              {state.data.items.length > 0
                ? `Showing ${state.data.offset + 1}–${state.data.offset + state.data.items.length} of ${state.data.total}`
                : `${state.data.total} traces`}
            </span>
            <span className="flex gap-2">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - TRACE_PAGE_SIZE))}
                className="rounded-md border border-slate-300 px-3 py-1 hover:bg-slate-50 disabled:opacity-50"
              >
                Prev
              </button>
              <button
                type="button"
                disabled={state.data.offset + state.data.items.length >= state.data.total}
                onClick={() => setOffset(offset + TRACE_PAGE_SIZE)}
                className="rounded-md border border-slate-300 px-3 py-1 hover:bg-slate-50 disabled:opacity-50"
              >
                Next
              </button>
            </span>
          </nav>
        )}
      </div>
    </section>
  )
}
