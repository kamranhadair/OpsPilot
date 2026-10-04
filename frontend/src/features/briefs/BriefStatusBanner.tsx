import type { BriefStatus, ValidationIssue } from '../../types/api'
import { IssueList } from './IssueList'

/** Validation state comes from the backend; the banner only presents it. */
export function BriefStatusBanner({
  status,
  issues,
}: {
  status: BriefStatus
  issues: ValidationIssue[]
}) {
  if (status === 'valid') {
    return (
      <p
        role="status"
        className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-800"
      >
        Validated against evidence: every claim cites resolvable evidence from this brief&apos;s
        Evidence Bundle.
      </p>
    )
  }
  if (status === 'invalid') {
    return (
      <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm">
        <p className="font-semibold text-red-800">
          Failed validation — not validated operational truth
        </p>
        <p className="mt-1 text-slate-700">
          This brief is kept for review only. Do not act on its claims.
        </p>
        <IssueList issues={issues} />
      </div>
    )
  }
  return (
    <p
      role="status"
      className="rounded-lg border border-slate-300 bg-slate-100 p-3 text-sm font-medium text-slate-700"
    >
      Not validated: this brief has not been checked against its evidence.
    </p>
  )
}
