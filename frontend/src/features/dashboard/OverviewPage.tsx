import { Link } from 'react-router-dom'

import { getDashboardOverview } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import { formatUtc } from '../../lib/format'
import type { DashboardOverviewResponse } from '../../types/api'
import { AnomalyTable } from '../anomalies/AnomalyTable'
import { HealthPanel } from '../system/HealthPanel'
import { MetricCard } from './MetricCard'
import { TrendChart } from './TrendChart'

function Overview({ data }: { data: DashboardOverviewResponse }) {
  if (data.window_end === null) {
    return (
      <EmptyPanel title="No metrics computed yet">
        Compute metric snapshots first, for example{' '}
        <code className="font-mono text-xs">
          python -m app.scripts.compute_metric_history --detect
        </code>
        .
      </EmptyPanel>
    )
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-600">
        Latest 24h window ending {formatUtc(data.window_end)}, compared with the
        preceding 7-day baseline.
      </p>

      <section aria-labelledby="metric-cards-heading">
        <h2 id="metric-cards-heading" className="sr-only">
          Current metrics
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {data.cards.map((card) => (
            <MetricCard key={card.evidence_id} snapshot={card} />
          ))}
        </div>
        {data.missing_metric_keys.length > 0 && (
          <p className="mt-2 text-xs text-slate-500">
            Not computed for this window: {data.missing_metric_keys.join(', ')}
          </p>
        )}
      </section>

      <section aria-labelledby="trends-heading">
        <h2 id="trends-heading" className="mb-3 text-base font-semibold">
          Trends
        </h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {data.trends.map((trend) => (
            <TrendChart key={trend.definition.key} trend={trend} />
          ))}
        </div>
      </section>

      <section aria-labelledby="active-anomalies-heading">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 id="active-anomalies-heading" className="text-base font-semibold">
            Active anomalies ({data.active_anomaly_total})
          </h2>
          <Link to="/anomalies" className="text-sm text-sky-700 hover:underline">
            Open anomaly explorer
          </Link>
        </div>
        {data.active_anomalies.length === 0 ? (
          <EmptyPanel title="No active anomalies">
            Detection has not flagged anything for the computed windows.
          </EmptyPanel>
        ) : (
          <AnomalyTable anomalies={data.active_anomalies} caption="Active anomalies" />
        )}
      </section>
    </div>
  )
}

export function OverviewPage() {
  const { state, reload } = useApiResource(getDashboardOverview)

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Operations overview</h2>
      {state.kind === 'loading' && <LoadingPanel label="Loading operations overview…" />}
      {state.kind === 'error' && (
        <ErrorPanel title="Overview unavailable" error={state.error} onRetry={reload} />
      )}
      {state.kind === 'success' && <Overview data={state.data} />}
      <HealthPanel />
    </div>
  )
}
