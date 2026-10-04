import { humanize } from '../../lib/format'
import type { ActionStatus } from '../../types/api'

/** Presentation only: the status always comes from the backend. */
const STYLES: Record<ActionStatus, string> = {
  proposed: 'bg-slate-100 text-slate-700',
  pending_approval: 'bg-amber-100 text-amber-900',
  approved: 'bg-sky-100 text-sky-800',
  rejected: 'bg-slate-200 text-slate-700',
  executing: 'bg-sky-100 text-sky-800',
  succeeded: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-red-100 text-red-800',
}

export function ActionStatusBadge({ status }: { status: ActionStatus }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {humanize(status)}
    </span>
  )
}
