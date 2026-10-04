import { formatFraction, humanize } from '../../lib/format'
import type { EvalCategorySummary } from '../../types/api'

export function CategoryTable({ categories }: { categories: EvalCategorySummary[] }) {
  return (
    <section aria-labelledby="eval-categories-heading" className="space-y-3">
      <h3 id="eval-categories-heading" className="text-base font-semibold">
        Pass/fail by category
      </h3>
      {categories.length === 0 ? (
        <p className="text-sm text-slate-600">No categories were evaluated in this run.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white p-4">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Evaluation results by category</caption>
            <thead className="text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="py-2 pr-4 font-medium">Category</th>
                <th className="py-2 pr-4 text-right font-medium">Total</th>
                <th className="py-2 pr-4 text-right font-medium">Passed</th>
                <th className="py-2 pr-4 text-right font-medium">Failed</th>
                <th className="py-2 pr-4 text-right font-medium">Errored</th>
                <th className="py-2 pr-4 text-right font-medium">Not run</th>
                <th className="py-2 text-right font-medium">Pass rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {categories.map((row) => (
                <tr key={row.category}>
                  <th scope="row" className="py-2 pr-4 font-normal">
                    {humanize(row.category)}
                  </th>
                  <td className="py-2 pr-4 text-right">{row.total}</td>
                  <td className="py-2 pr-4 text-right">{row.passed}</td>
                  <td className="py-2 pr-4 text-right">{row.failed}</td>
                  <td className="py-2 pr-4 text-right">{row.errored}</td>
                  <td className="py-2 pr-4 text-right">{row.not_run}</td>
                  <td className="py-2 text-right font-medium">{formatFraction(row.pass_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
