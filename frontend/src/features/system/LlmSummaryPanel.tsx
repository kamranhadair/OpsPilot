import type { ReactNode } from 'react'

import type { ResourceState } from '../../api/useApiResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import {
  formatFraction,
  formatLatencyMs,
  formatTokens,
  formatUsd,
  formatUtc,
  humanize,
} from '../../lib/format'
import type { LLMSummary, SummaryPeriod, SystemSummaryOut } from '../../types/api'

const PERIODS: { value: SummaryPeriod; label: string }[] = [
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: 'all', label: 'All time' },
]

function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-lg font-semibold text-slate-900">{value}</dd>
      {note && <dd className="mt-0.5 text-xs text-slate-500">{note}</dd>}
    </div>
  )
}

function costValue(llm: LLMSummary): string {
  if (!llm.cost_configured && llm.estimated_cost_usd === null) return 'not configured'
  return formatUsd(llm.estimated_cost_usd)
}

function Summary({ summary }: { summary: SystemSummaryOut }) {
  const { llm } = summary
  const window =
    summary.window_start === null
      ? `All time to ${formatUtc(summary.window_end)}`
      : `${formatUtc(summary.window_start)} – ${formatUtc(summary.window_end)}`

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">Window: {window}</p>
      {llm.total_calls === 0 ? (
        <EmptyPanel title="No LLM calls in this period">
          Traces are recorded when briefs or action proposals are generated.
        </EmptyPanel>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat
              label="LLM calls"
              value={llm.total_calls.toLocaleString('en-US')}
              note={`${llm.success_count.toLocaleString('en-US')} succeeded · ${llm.error_count.toLocaleString('en-US')} failed`}
            />
            <Stat label="Error rate" value={formatFraction(llm.error_rate)} />
            <Stat
              label="Tokens (input / output)"
              value={`${formatTokens(llm.input_tokens_total)} / ${formatTokens(llm.output_tokens_total)}`}
              note={
                llm.calls_missing_usage > 0
                  ? `${llm.calls_missing_usage} calls with usage not reported`
                  : undefined
              }
            />
            <Stat
              label="Estimated cost"
              value={costValue(llm)}
              note={
                llm.cost_configured && llm.calls_missing_cost > 0
                  ? `${llm.calls_missing_cost} calls with cost not reported`
                  : undefined
              }
            />
          </dl>
          <div>
            <h4 className="text-sm font-semibold text-slate-700">Latency</h4>
            {llm.latency_ms === null ? (
              <p className="mt-1 text-sm text-slate-500">No latency recorded.</p>
            ) : (
              <dl aria-label="Latency" className="mt-2 grid grid-cols-4 gap-3 text-sm">
                {(['avg', 'p50', 'p95', 'max'] as const).map((key) => (
                  <div key={key}>
                    <dt className="text-slate-500">{key === 'avg' ? 'Average' : key}</dt>
                    <dd className="font-medium text-slate-900">
                      {formatLatencyMs(llm.latency_ms?.[key] ?? null)}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
          {llm.by_operation.length > 0 && (
            <table className="w-full text-left text-sm">
              <caption className="pb-2 text-left text-sm font-semibold text-slate-700">
                By operation
              </caption>
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="py-2 pr-4 font-medium">Operation</th>
                  <th className="py-2 pr-4 font-medium">Calls</th>
                  <th className="py-2 pr-4 font-medium">Errors</th>
                  <th className="py-2 pr-4 font-medium">Error rate</th>
                  <th className="py-2 pr-4 font-medium">Avg latency</th>
                  <th className="py-2 pr-4 font-medium">Tokens in / out</th>
                  <th className="py-2 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {llm.by_operation.map((op) => (
                  <tr key={op.operation}>
                    <td className="py-2 pr-4">{humanize(op.operation)}</td>
                    <td className="py-2 pr-4">{op.total_calls}</td>
                    <td className="py-2 pr-4">{op.error_count}</td>
                    <td className="py-2 pr-4">{formatFraction(op.error_rate)}</td>
                    <td className="py-2 pr-4">{formatLatencyMs(op.avg_latency_ms)}</td>
                    <td className="py-2 pr-4">
                      {formatTokens(op.input_tokens_total)} / {formatTokens(op.output_tokens_total)}
                    </td>
                    <td className="py-2">{formatUsd(op.estimated_cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

/** Backend-aggregated LLM call health for the selected period; values are only formatted. */
export function LlmSummaryPanel({
  state,
  reload,
  period,
  onPeriodChange,
}: {
  state: ResourceState<SystemSummaryOut>
  reload: () => void
  period: SummaryPeriod
  onPeriodChange: (period: SummaryPeriod) => void
}) {
  return (
    <section
      aria-labelledby="llm-summary-heading"
      className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h3 id="llm-summary-heading" className="text-base font-semibold">
          LLM calls
        </h3>
        <label className="text-sm text-slate-600">
          Period{' '}
          <select
            value={period}
            onChange={(event) => onPeriodChange(event.target.value as SummaryPeriod)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
          >
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="mt-4">
        {state.kind === 'loading' && <LoadingPanel label="Loading LLM call summary…" />}
        {state.kind === 'error' && (
          <ErrorPanel
            title="Could not load the LLM call summary"
            error={state.error}
            onRetry={reload}
          />
        )}
        {state.kind === 'success' && <Summary summary={state.data} />}
      </div>
    </section>
  )
}
