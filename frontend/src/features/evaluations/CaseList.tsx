import { humanize } from '../../lib/format'
import type { EvalCaseResult } from '../../types/api'
import { EvalStatusBadge } from './EvalStatusBadge'

/** One case with its expectation, observation and reason, as recorded by the runner. */
export function CaseCard({ result }: { result: EvalCaseResult }) {
  return (
    <li
      aria-label={result.case_id}
      className="rounded-lg border border-slate-200 bg-white p-4 text-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        <EvalStatusBadge status={result.status} />
        <span className="font-medium text-slate-900">{result.title}</span>
      </div>
      <p className="mt-1 font-mono text-xs text-slate-500">
        {result.case_id} · {humanize(result.category)}
      </p>
      <dl className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-[8rem_1fr]">
        <dt className="text-xs uppercase tracking-wide text-slate-500">Expected</dt>
        <dd className="break-words font-mono text-xs">{result.expected}</dd>
        <dt className="text-xs uppercase tracking-wide text-slate-500">Observed</dt>
        <dd className="break-words font-mono text-xs">
          {result.observed ?? <span className="text-slate-500">No observation recorded</span>}
        </dd>
        {result.failure_reason && (
          <>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Reason</dt>
            <dd className="whitespace-pre-wrap break-words font-mono text-xs text-red-800">
              {result.failure_reason}
            </dd>
          </>
        )}
        {result.tally && (
          <>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Tally</dt>
            <dd className="text-xs">
              {result.tally.flagged} flagged of {result.tally.checked} checked
            </dd>
          </>
        )}
        {result.evidence.length > 0 && (
          <>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Evidence</dt>
            <dd className="font-mono text-xs">{result.evidence.join(', ')}</dd>
          </>
        )}
      </dl>
    </li>
  )
}

/**
 * Failed/errored cases, then cases that did not run. The split follows the
 * statuses the runner assigned; a not-run case is never presented as passed.
 */
export function CaseDetails({ cases }: { cases: EvalCaseResult[] }) {
  const failing = cases.filter((c) => c.status === 'fail' || c.status === 'error')
  const notRun = cases.filter((c) => c.status === 'not_run')

  return (
    <div className="space-y-6">
      <section aria-labelledby="eval-failed-heading" className="space-y-3">
        <h3 id="eval-failed-heading" className="text-base font-semibold">
          Failed and errored cases ({failing.length})
        </h3>
        {failing.length === 0 ? (
          <p className="text-sm text-slate-600">No deterministic case failed or errored.</p>
        ) : (
          <ul className="space-y-3">
            {failing.map((result) => (
              <CaseCard key={result.case_id} result={result} />
            ))}
          </ul>
        )}
      </section>

      {notRun.length > 0 && (
        <section aria-labelledby="eval-not-run-heading" className="space-y-3">
          <h3 id="eval-not-run-heading" className="text-base font-semibold">
            Cases not run ({notRun.length})
          </h3>
          <p className="text-sm text-slate-600">
            These cases were skipped and are not counted as passed.
          </p>
          <ul className="space-y-3">
            {notRun.map((result) => (
              <CaseCard key={result.case_id} result={result} />
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
