import type { AnomalySeverity } from '../types/api'

/** Colour for a backend-assigned severity. The severity itself is never derived here. */
const STYLES: Record<AnomalySeverity, string> = {
  critical: 'bg-red-700 text-white',
  high: 'bg-red-100 text-red-800 ring-1 ring-red-200',
  medium: 'bg-amber-100 text-amber-800 ring-1 ring-amber-200',
  low: 'bg-slate-100 text-slate-700 ring-1 ring-slate-200',
}

export function SeverityBadge({ severity }: { severity: AnomalySeverity }) {
  return (
    <span
      className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${STYLES[severity]}`}
    >
      {severity}
    </span>
  )
}
