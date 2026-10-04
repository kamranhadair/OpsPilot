/** Text-first status labels for system readiness and traces; colour only reinforces the text. */

const STYLES: Record<string, string> = {
  ok: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200',
  success: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200',
  available: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200',
  configured: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200',
  enabled: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200',
  degraded: 'bg-amber-100 text-amber-800 ring-1 ring-amber-200',
  invalid: 'bg-amber-100 text-amber-800 ring-1 ring-amber-200',
  error: 'bg-red-700 text-white',
  not_configured: 'bg-slate-200 text-slate-700 ring-1 ring-slate-300',
  disabled: 'bg-slate-200 text-slate-700 ring-1 ring-slate-300',
  not_run: 'bg-slate-200 text-slate-700 ring-1 ring-slate-300',
}

const LABELS: Record<string, string> = {
  not_configured: 'NOT CONFIGURED',
  not_run: 'NOT RUN',
}

export function SystemStatusBadge({ status }: { status: string }) {
  const style = STYLES[status] ?? 'bg-slate-100 text-slate-700 ring-1 ring-slate-200'
  return (
    <span
      className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${style}`}
    >
      {LABELS[status] ?? status.toUpperCase()}
    </span>
  )
}
