import { SeverityBadge } from '../../components/SeverityBadge'
import { formatDimensions, formatUtcDate } from '../../lib/format'
import type { EvalReplayAnomaly, EvalReplaySummary } from '../../types/api'
import { EvalStatusBadge } from './EvalStatusBadge'

function slice(filters: Record<string, string>): string {
  return Object.keys(filters).length === 0 ? 'overall' : formatDimensions(filters)
}

function AnomalyList({ anomalies }: { anomalies: EvalReplayAnomaly[] }) {
  if (anomalies.length === 0) return <span className="text-slate-500">No anomalies</span>
  return (
    <ul className="space-y-0.5">
      {anomalies.map((anomaly, index) => (
        <li key={`${anomaly.metric_key}-${index}`}>
          {anomaly.display_name} · {slice(anomaly.filters)} ·{' '}
          <SeverityBadge severity={anomaly.severity} />
        </li>
      ))}
    </ul>
  )
}

export function ReplaySummary({ replay }: { replay: EvalReplaySummary | null }) {
  return (
    <section aria-labelledby="eval-replay-heading" className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h3 id="eval-replay-heading" className="text-base font-semibold">
          Replay summary
        </h3>
        {replay && <EvalStatusBadge status={replay.status} />}
      </div>
      {replay === null ? (
        <p className="text-sm text-slate-600">This suite did not include a replay.</p>
      ) : (
        <>
          <p className="text-sm text-slate-600">
            {replay.note} Days requested: {replay.days_requested}.
          </p>
          {replay.reason && (
            <p className="text-sm">
              <span className="font-medium text-slate-700">Reason: </span>
              {replay.reason}
            </p>
          )}
          {replay.days.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white p-4">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Daily replay of anomaly detection</caption>
                <thead className="text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Day (UTC)</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 pr-4 text-right font-medium">High/critical</th>
                    <th className="py-2 font-medium">Anomalies</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 align-top">
                  {replay.days.map((day) => (
                    <tr key={day.window_start}>
                      <th scope="row" className="py-2 pr-4 font-normal whitespace-nowrap">
                        {formatUtcDate(day.window_start)}
                      </th>
                      <td className="py-2 pr-4">
                        <EvalStatusBadge status={day.status} />
                      </td>
                      <td className="py-2 pr-4 text-right">{day.high_or_critical_count}</td>
                      <td className="py-2">
                        {day.status === 'no_data' ? (
                          <span className="text-slate-600">{day.detail ?? 'No data'}</span>
                        ) : (
                          <AnomalyList anomalies={day.anomalies} />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}
