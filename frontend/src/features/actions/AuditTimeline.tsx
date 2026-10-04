import { formatUtc, humanize } from '../../lib/format'
import type { AuditEventOut } from '../../types/api'

const ACTOR_LABELS: Record<AuditEventOut['actor_type'], string> = {
  human: 'Human',
  system: 'System',
  ai: 'AI',
}

/** `action.execution_succeeded` -> `Execution Succeeded`. Formatting only. */
function eventLabel(eventType: string): string {
  const name = eventType.startsWith('action.') ? eventType.slice('action.'.length) : eventType
  return humanize(name.replaceAll('.', '_'))
}

/** The backend's audit trail for one action, in the order returned (oldest first). */
export function AuditTimeline({ events }: { events: AuditEventOut[] }) {
  return (
    <section aria-labelledby="audit-heading" className="space-y-2">
      <h3 id="audit-heading" className="font-medium text-slate-800">
        Audit timeline
      </h3>
      {events.length === 0 ? (
        <p className="text-sm text-slate-500">No audit events recorded.</p>
      ) : (
        <ol aria-label="Audit events" className="space-y-2 border-l border-slate-200 pl-4">
          {events.map((event) => (
            <li key={event.id} className="text-sm">
              <p className="font-medium text-slate-800">{eventLabel(event.event_type)}</p>
              <p className="text-xs text-slate-500">
                <span className="rounded bg-slate-100 px-1 py-0.5 font-medium text-slate-700">
                  {ACTOR_LABELS[event.actor_type]}
                </span>{' '}
                {event.actor_id ?? 'unidentified'} · {formatUtc(event.created_at)} ·{' '}
                <span className="font-mono">{event.event_type}</span>
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
