import { useCallback, useEffect, useRef, type ReactNode } from 'react'

import { getEvidence } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { EvidenceId } from '../../components/EvidenceId'
import { ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import { formatDimensions, formatEvidenceValue, formatUtc, humanize } from '../../lib/format'
import type { EvidenceDetailOut, EvidenceWindow } from '../../types/api'

const MISSING_CODES = new Set(['EVIDENCE_NOT_FOUND', 'INVALID_EVIDENCE_ID'])

const TYPE_LABELS: Record<EvidenceDetailOut['evidence_type'], string> = {
  MTR: 'Metric snapshot',
  ANOM: 'Detected anomaly',
  SEG: 'Contributing segment',
  EVT: 'Timeline event',
}

function windowText(window: EvidenceWindow | null): string {
  return window ? `${formatUtc(window.start)} → ${formatUtc(window.end)}` : 'Not applicable'
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-2 py-1">
      <dt className="text-slate-500">{label}</dt>
      <dd className="col-span-2 text-slate-900">{children}</dd>
    </div>
  )
}

function EvidenceDetail({ detail }: { detail: EvidenceDetailOut }) {
  const { provenance } = detail
  return (
    <div className="space-y-5 text-sm">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">
          {TYPE_LABELS[detail.evidence_type]}
        </p>
        <p className="mt-1 font-medium text-slate-900">{detail.label}</p>
      </div>

      {detail.contextual_disclaimer && (
        <p
          role="note"
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-amber-900"
        >
          {detail.contextual_disclaimer}
        </p>
      )}

      <section aria-label="Values">
        <h3 className="font-medium text-slate-800">Values</h3>
        <dl className="mt-1 divide-y divide-slate-100">
          {detail.values.map((item) => (
            <Row key={item.key} label={item.label}>
              {formatEvidenceValue(item)}
              {item.note && <span className="block text-xs text-slate-500">{item.note}</span>}
            </Row>
          ))}
        </dl>
      </section>

      <section aria-label="Scope and sample">
        <h3 className="font-medium text-slate-800">Scope and sample</h3>
        <dl className="mt-1 divide-y divide-slate-100">
          {provenance.evidence_type === 'EVT' ? (
            <Row label="Occurred at">{formatUtc(provenance.occurred_at)}</Row>
          ) : (
            <>
              <Row label="Analysis window">{windowText(detail.window)}</Row>
              <Row label="Baseline window">{windowText(detail.baseline_window)}</Row>
            </>
          )}
          <Row label="Dimensions">{formatDimensions(detail.dimensions)}</Row>
          <Row label="Sample size">
            {detail.sample_size === null ? 'Not applicable' : detail.sample_size}
            {detail.sample_sufficient === false && (
              <span className="ml-2 text-xs text-amber-700">Below minimum sample</span>
            )}
          </Row>
        </dl>
      </section>

      <section aria-label="Method">
        <h3 className="font-medium text-slate-800">Method</h3>
        <dl className="mt-1 divide-y divide-slate-100">
          <Row label="Kind">{humanize(detail.method.kind)}</Row>
          <Row label="Name">
            <code className="font-mono text-xs">{detail.method.name}</code>
            {detail.method.version && (
              <span className="ml-2 text-xs text-slate-500">v{detail.method.version}</span>
            )}
          </Row>
          {detail.method.formula && (
            <Row label="Formula">
              <code className="font-mono text-xs">{detail.method.formula}</code>
            </Row>
          )}
          {detail.method.description && (
            <Row label="Explanation">{detail.method.description}</Row>
          )}
          {provenance.evidence_type === 'SEG' && (
            <Row label="Statement">{provenance.statement}</Row>
          )}
        </dl>
      </section>

      {detail.related_evidence_ids.length > 0 && (
        <p className="text-slate-600">
          Related evidence:{' '}
          {detail.related_evidence_ids.map((id) => (
            <span key={id} className="mr-1">
              <EvidenceId id={id} />
            </span>
          ))}
        </p>
      )}

      <details>
        <summary className="cursor-pointer text-slate-700">Full provenance record</summary>
        <pre
          aria-label="Provenance record"
          className="mt-2 max-h-80 overflow-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-100"
        >
          {JSON.stringify(provenance, null, 2)}
        </pre>
      </details>
    </div>
  )
}

/** Side drawer showing backend-resolved provenance for one evidence ID. */
export function ProvenanceDrawer({
  evidenceId,
  onClose,
}: {
  evidenceId: string
  onClose: () => void
}) {
  const load = useCallback(() => getEvidence(evidenceId), [evidenceId])
  const { state, reload } = useApiResource(load)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous?.focus()
    }
  }, [onClose])

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30" aria-hidden="true" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="provenance-heading"
        className="relative h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-xl"
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id="provenance-heading" className="text-lg font-semibold">
            Evidence <span className="font-mono">{evidenceId}</span>
          </h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-700 hover:bg-slate-50"
          >
            Close
          </button>
        </div>
        {state.kind === 'loading' && <LoadingPanel label="Loading evidence…" />}
        {state.kind === 'error' &&
          (MISSING_CODES.has(state.error.code) ? (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm">
              <p className="font-medium text-red-800">Evidence no longer available</p>
              <p className="mt-1 text-slate-700">{state.error.message}</p>
              <p className="mt-1 font-mono text-xs text-slate-500">{state.error.code}</p>
            </div>
          ) : (
            <ErrorPanel title="Could not load evidence" error={state.error} onRetry={reload} />
          ))}
        {state.kind === 'success' && <EvidenceDetail detail={state.data} />}
      </aside>
    </div>
  )
}
