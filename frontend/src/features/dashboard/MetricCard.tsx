import { EvidenceId } from '../../components/EvidenceId'
import { formatChange, formatMetricValue } from '../../lib/format'
import type { MetricSnapshotOut } from '../../types/api'

export function MetricCard({ snapshot }: { snapshot: MetricSnapshotOut }) {
  const headingId = `metric-card-${snapshot.metric_key}`
  return (
    <section
      aria-labelledby={headingId}
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <h3 id={headingId} className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {snapshot.display_name}
      </h3>
      <p className="mt-2 text-2xl font-semibold tabular-nums">
        {formatMetricValue(snapshot.value, snapshot.unit)}
      </p>
      <dl className="mt-2 grid grid-cols-2 gap-x-2 text-xs">
        <dt className="text-slate-500">7-day baseline</dt>
        <dd className="text-right tabular-nums">
          {snapshot.baseline_value === null
            ? 'No baseline'
            : formatMetricValue(snapshot.baseline_value, snapshot.unit)}
        </dd>
        <dt className="text-slate-500">Change</dt>
        <dd className="text-right font-medium tabular-nums">{formatChange(snapshot)}</dd>
      </dl>
      {!snapshot.sample_sufficient && (
        <p className="mt-2 text-xs text-amber-700">
          Below minimum sample size ({snapshot.sample_size} records)
        </p>
      )}
      <p className="mt-3">
        <EvidenceId id={snapshot.evidence_id} />
      </p>
    </section>
  )
}
