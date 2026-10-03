import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { EvidenceId } from '../../components/EvidenceId'
import { formatFamily, formatMetricValue, humanize } from '../../lib/format'
import type { ContributorAnalysisResponse, ContributorGroupOut } from '../../types/api'

/** The canonical concentration view is shown first; other families keep API order. */
const LEAD_FAMILY = 'region+customer_tier'

const PCT = new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const pct = (value: number) => `${PCT.format(value)}%`

function ContributorGroup({ group, lead }: { group: ContributorGroupOut; lead: boolean }) {
  const headingId = `contributors-${group.family_key}`
  const title = formatFamily(group.dimensions)
  const data = group.contributors.map((c) => ({ label: c.label, share: c.contribution_pct }))

  return (
    <section
      aria-labelledby={headingId}
      className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm ${lead ? 'xl:col-span-2' : ''}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 id={headingId} className="text-sm font-semibold text-slate-800">
          {title}
        </h4>
        <span className="text-xs text-slate-500">
          {group.method === 'rate_excess' ? 'Share of excess events' : 'Share of positive change'}
        </span>
      </div>

      <div
        role="img"
        aria-label={`${title}: share of observed change by segment`}
        className="mt-3"
        style={{ height: Math.max(80, data.length * 32) }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
            <XAxis type="number" domain={[0, 100]} tickFormatter={pct} tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(value) => [pct(Number(value)), 'Share']} />
            <Bar dataKey="share" name="Share of change" fill="#334155" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{title} contributors</caption>
        <thead className="text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="px-2 py-1">Rank</th>
            <th scope="col" className="px-2 py-1">Segment</th>
            <th scope="col" className="px-2 py-1 text-right">Current</th>
            <th scope="col" className="px-2 py-1 text-right">
              {group.method === 'rate_excess' ? 'Expected' : 'Baseline'}
            </th>
            <th scope="col" className="px-2 py-1 text-right">Share</th>
            <th scope="col" className="px-2 py-1">Evidence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {group.contributors.map((c) => (
            <tr key={c.evidence_id}>
              <td className="px-2 py-1 tabular-nums">{c.rank}</td>
              <td className="px-2 py-1">
                <span className="font-medium">{c.label}</span>
                {c.flags.map((flag) => (
                  <span
                    key={flag}
                    className="ml-2 rounded bg-slate-100 px-1.5 text-xs text-slate-600"
                  >
                    {humanize(flag)}
                  </span>
                ))}
                <p className="text-xs text-slate-500">{c.statement}</p>
              </td>
              <td className="px-2 py-1 text-right whitespace-nowrap tabular-nums">{formatMetricValue(c.current_value, 'count')}</td>
              <td className="px-2 py-1 text-right whitespace-nowrap tabular-nums">{formatMetricValue(c.baseline_value, 'count')}</td>
              <td className="px-2 py-1 text-right font-medium whitespace-nowrap tabular-nums">{pct(c.contribution_pct)}</td>
              <td className="px-2 py-1 whitespace-nowrap">
                <EvidenceId id={c.evidence_id} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Other segments: {pct(group.other_contribution_pct)}
        {group.suppressed_contribution_pct > 0 &&
          ` (includes ${pct(group.suppressed_contribution_pct)} below minimum sample size)`}
      </p>
    </section>
  )
}

export function ContributorBreakdown({ analysis }: { analysis: ContributorAnalysisResponse }) {
  if (analysis.groups.length === 0) {
    return <p className="text-sm text-slate-600">No positive contributors were found.</p>
  }
  const groups = [
    ...analysis.groups.filter((g) => g.family_key === LEAD_FAMILY),
    ...analysis.groups.filter((g) => g.family_key !== LEAD_FAMILY),
  ]
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      {groups.map((group) => (
        <ContributorGroup
          key={group.family_key}
          group={group}
          lead={group.family_key === LEAD_FAMILY}
        />
      ))}
    </div>
  )
}
