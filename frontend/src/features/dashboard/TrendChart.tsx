import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { formatMetricValue, formatUtcDate } from '../../lib/format'
import type { DashboardTrend } from '../../types/api'

/** Daily overall values and their 7-day baselines, exactly as persisted by the backend. */
export function TrendChart({ trend }: { trend: DashboardTrend }) {
  const { definition, points } = trend
  const headingId = `trend-${definition.key}`
  const format = (value: number) => formatMetricValue(value, definition.unit)
  const data = points.map((point) => ({
    label: formatUtcDate(point.window_end),
    value: point.value,
    baseline: point.baseline_value,
  }))

  return (
    <section
      aria-labelledby={headingId}
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <h3 id={headingId} className="text-sm font-semibold text-slate-800">
        {definition.display_name} trend
      </h3>
      {points.length < 2 ? (
        <p className="mt-3 text-sm text-slate-500">
          Not enough history to draw a trend ({points.length} daily{' '}
          {points.length === 1 ? 'window' : 'windows'} computed).
        </p>
      ) : (
        <>
          <div
            role="img"
            aria-label={`${definition.display_name} by day with 7-day baseline, ${points.length} daily windows`}
            className="mt-3 h-56"
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="#64748b" />
                <YAxis tick={{ fontSize: 11 }} stroke="#64748b" tickFormatter={format} width={56} />
                <Tooltip formatter={(value) => format(Number(value))} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line
                  type="monotone"
                  dataKey="value"
                  name={definition.display_name}
                  stroke="#0f172a"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="baseline"
                  name="7-day baseline"
                  stroke="#94a3b8"
                  strokeDasharray="4 4"
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <table className="sr-only">
            <caption>{definition.display_name} daily values</caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">Value</th>
                <th scope="col">Baseline</th>
                <th scope="col">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {points.map((point) => (
                <tr key={point.evidence_id}>
                  <td>{formatUtcDate(point.window_end)}</td>
                  <td>{format(point.value)}</td>
                  <td>{point.baseline_value === null ? 'No baseline' : format(point.baseline_value)}</td>
                  <td>{point.evidence_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}
