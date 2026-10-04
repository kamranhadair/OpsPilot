import type { ValidationIssue } from '../../types/api'

function where(issue: ValidationIssue): string | null {
  if (issue.claim_ordinal !== null && issue.claim_ordinal !== undefined) {
    return `Claim ${issue.claim_ordinal + 1}`
  }
  if (issue.field) return issue.field === 'headline' ? 'Headline' : 'Summary'
  return null
}

export function IssueList({ issues }: { issues: ValidationIssue[] }) {
  if (issues.length === 0) return null
  return (
    <ul aria-label="Validation errors" className="mt-2 space-y-1">
      {issues.map((issue, index) => {
        const location = where(issue)
        return (
          <li key={index} className="text-slate-800">
            <code className="mr-2 font-mono text-xs text-red-700">{issue.code}</code>
            {location && <span className="mr-1 font-medium">{location}:</span>}
            {issue.message}
          </li>
        )
      })}
    </ul>
  )
}
