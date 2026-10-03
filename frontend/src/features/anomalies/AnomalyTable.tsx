import { Link } from 'react-router-dom'

import { EvidenceId } from '../../components/EvidenceId'
import { SeverityBadge } from '../../components/SeverityBadge'
import {
  formatDimensions,
  formatMetricValue,
  formatScore,
  formatUtc,
} from '../../lib/format'
import type { AnomalyOut } from '../../types/api'

/** Anomalies in the order the API returned them (newest window, then most severe). */
export function AnomalyTable({ anomalies, caption }: { anomalies: AnomalyOut[]; caption: string }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="px-3 py-2">Severity</th>
            <th scope="col" className="px-3 py-2">Metric</th>
            <th scope="col" className="px-3 py-2">Context</th>
            <th scope="col" className="px-3 py-2 text-right">Current vs baseline</th>
            <th scope="col" className="px-3 py-2 text-right">Change</th>
            <th scope="col" className="px-3 py-2">Window end</th>
            <th scope="col" className="px-3 py-2">Evidence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {anomalies.map((anomaly) => (
            <tr key={anomaly.evidence_id} className="hover:bg-slate-50">
              <td className="px-3 py-2">
                <SeverityBadge severity={anomaly.severity} />
              </td>
              <td className="px-3 py-2 font-medium">
                <Link
                  to={`/anomalies/${anomaly.evidence_id}`}
                  className="text-sky-800 hover:underline"
                >
                  {anomaly.display_name}
                </Link>
              </td>
              <td className="px-3 py-2 text-slate-600">
                {formatDimensions(anomaly.dimensions)}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {formatMetricValue(anomaly.value, anomaly.unit)}
                <span className="text-slate-400"> vs </span>
                {anomaly.baseline_value === null
                  ? 'No baseline'
                  : formatMetricValue(anomaly.baseline_value, anomaly.unit)}
              </td>
              <td className="px-3 py-2 text-right font-medium tabular-nums">
                {formatScore(anomaly.score, anomaly.score_comparison)}
              </td>
              <td className="px-3 py-2 whitespace-nowrap text-slate-600">
                {formatUtc(anomaly.window_end)}
              </td>
              <td className="px-3 py-2">
                <EvidenceId id={anomaly.evidence_id} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
