import { formatUtc, humanize } from '../../lib/format'
import type { EvaluationReport } from '../../types/api'
import { EvalStatusBadge } from './EvalStatusBadge'

function SeedWarning({ seed }: { seed: EvaluationReport['seed'] }) {
  return (
    <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm">
      <p className="font-medium text-amber-900">Demo seed missing or mismatched</p>
      <p className="mt-1 text-slate-700">
        Observed seed state: {humanize(seed.observed_state)}, version{' '}
        {seed.observed_version ?? 'none'} (expected version {seed.expected_version}). Dataset
        cases did not run; they are listed as NOT RUN below, not as passed.
      </p>
    </div>
  )
}

export function ReportHeader({ report }: { report: EvaluationReport }) {
  const { seed } = report
  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-slate-700">Overall status</span>
          <EvalStatusBadge status={report.overall_status} />
          {report.partial_failure && (
            <span className="inline-flex rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide bg-red-50 text-red-800 ring-1 ring-red-200">
              Partial failure
            </span>
          )}
        </div>
        {report.partial_failure && (
          <p className="mt-2 text-sm text-slate-600">
            At least one case, the replay or the model judge errored during this run.
          </p>
        )}
        <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Suite</dt>
            <dd>{report.suite}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Generated</dt>
            <dd>{formatUtc(report.generated_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Run ID</dt>
            <dd className="break-all font-mono text-xs">{report.run_id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Demo seed</dt>
            <dd>
              {humanize(seed.observed_state)}, v{seed.observed_version ?? 'none'} (expected v
              {seed.expected_version}, cases v{seed.case_version})
              {seed.matches ? ' · matches' : ' · does not match'}
            </dd>
          </div>
        </dl>
      </div>
      {!seed.matches && <SeedWarning seed={seed} />}
    </div>
  )
}
