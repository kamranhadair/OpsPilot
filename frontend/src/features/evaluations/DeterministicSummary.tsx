import { formatFraction } from '../../lib/format'
import type { EvalCountMetric, EvalRatioMetric } from '../../types/api'

/** Ratios and counts exactly as the report states them; nothing is recomputed here. */
export function DeterministicSummary({
  ratios,
  counts,
}: {
  ratios: EvalRatioMetric[]
  counts: EvalCountMetric[]
}) {
  return (
    <section aria-labelledby="eval-summary-heading" className="space-y-3">
      <h3 id="eval-summary-heading" className="text-base font-semibold">
        Deterministic summary
      </h3>
      {ratios.length === 0 && counts.length === 0 ? (
        <p className="text-sm text-slate-600">The report contains no summary metrics.</p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ratios.map((ratio) => (
            <li
              key={ratio.key}
              aria-label={ratio.label}
              className="rounded-lg border border-slate-200 bg-white p-4"
            >
              <p className="text-sm font-medium text-slate-700">{ratio.label}</p>
              <p className="mt-1 text-2xl font-semibold">{formatFraction(ratio.value)}</p>
              <p className="text-xs text-slate-500">
                {ratio.numerator}/{ratio.denominator}
                {ratio.value === null && ' · nothing measured'}
              </p>
              <p className="mt-2 text-xs text-slate-600">{ratio.description}</p>
            </li>
          ))}
          {counts.map((count) => (
            <li
              key={count.key}
              aria-label={count.label}
              className="rounded-lg border border-slate-200 bg-white p-4"
            >
              <p className="text-sm font-medium text-slate-700">{count.label}</p>
              <dl className="mt-1 grid grid-cols-4 gap-2 text-center text-sm">
                <div>
                  <dt className="text-xs text-slate-500">Pass</dt>
                  <dd className="font-semibold">{count.passed}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Fail</dt>
                  <dd className="font-semibold">{count.failed}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Error</dt>
                  <dd className="font-semibold">{count.errored}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Not run</dt>
                  <dd className="font-semibold">{count.not_run}</dd>
                </div>
              </dl>
              <p className="mt-2 text-xs text-slate-600">{count.description}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
