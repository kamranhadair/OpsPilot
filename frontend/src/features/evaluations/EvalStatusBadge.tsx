/** Text-first status labels for evaluation results; colour only reinforces the text. */

const STYLES: Record<string, string> = {
  pass: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200',
  completed: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200',
  ok: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200',
  fail: 'bg-red-100 text-red-800 ring-1 ring-red-200',
  error: 'bg-red-700 text-white',
  incomplete: 'bg-amber-100 text-amber-800 ring-1 ring-amber-200',
  not_run: 'bg-slate-200 text-slate-700 ring-1 ring-slate-300',
  no_data: 'bg-slate-200 text-slate-700 ring-1 ring-slate-300',
}

const LABELS: Record<string, string> = {
  not_run: 'NOT RUN',
  no_data: 'NO DATA',
}

export function EvalStatusBadge({ status }: { status: string }) {
  const style = STYLES[status] ?? 'bg-slate-100 text-slate-700 ring-1 ring-slate-200'
  return (
    <span
      className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${style}`}
    >
      {LABELS[status] ?? status.toUpperCase()}
    </span>
  )
}
