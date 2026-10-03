import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, computeContributors, getAnomaly, getContributors } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { EvidenceId } from '../../components/EvidenceId'
import { SeverityBadge } from '../../components/SeverityBadge'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import {
  formatChange,
  formatDimensions,
  formatMetricValue,
  formatThresholdValue,
  formatUtc,
  humanize,
} from '../../lib/format'
import type { AnomalyDetailOut, ContributorAnalysisResponse } from '../../types/api'
import { ContributorBreakdown } from './ContributorBreakdown'

const NOT_FOUND_CODES = new Set(['ANOMALY_NOT_FOUND', 'INVALID_EVIDENCE_ID'])

type ContributorState =
  | { kind: 'loading' }
  | { kind: 'not_computed' }
  | { kind: 'computing' }
  | { kind: 'unsupported'; message: string }
  | { kind: 'error'; error: ApiError }
  | { kind: 'success'; data: ContributorAnalysisResponse }

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError('Unexpected client error.', 0, 'CLIENT_ERROR', { cause: error })
}

function toContributorState(error: unknown): ContributorState {
  const apiError = asApiError(error)
  if (apiError.code === 'CONTRIBUTORS_NOT_COMPUTED') return { kind: 'not_computed' }
  if (apiError.code === 'SEGMENTATION_NOT_SUPPORTED') {
    return { kind: 'unsupported', message: apiError.message }
  }
  return { kind: 'error', error: apiError }
}

function Contributors({ evidenceId }: { evidenceId: string }) {
  const [state, setState] = useState<ContributorState>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    setState({ kind: 'loading' })
    getContributors(evidenceId).then(
      (data) => current && setState({ kind: 'success', data }),
      (error: unknown) => current && setState(toContributorState(error)),
    )
    return () => {
      current = false
    }
  }, [evidenceId, attempt])

  const compute = useCallback(() => {
    setState({ kind: 'computing' })
    computeContributors(evidenceId).then(
      (data) => setState({ kind: 'success', data }),
      (error: unknown) => setState(toContributorState(error)),
    )
  }, [evidenceId])

  return (
    <section aria-labelledby="contributors-heading" className="space-y-3">
      <div>
        <h3 id="contributors-heading" className="text-base font-semibold">
          Contributor breakdown
        </h3>
        <p className="text-xs text-slate-500">
          Where the observed change is concentrated. Shares describe the change, not its cause.
        </p>
      </div>
      {state.kind === 'loading' && <LoadingPanel label="Loading contributor analysis…" />}
      {state.kind === 'computing' && <LoadingPanel label="Computing contributor analysis…" />}
      {state.kind === 'not_computed' && (
        <EmptyPanel title="Contributor analysis not computed yet">
          <p>Run the deterministic contributor analysis for this anomaly.</p>
          <button
            type="button"
            onClick={compute}
            className="mt-3 rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
          >
            Compute contributors
          </button>
        </EmptyPanel>
      )}
      {state.kind === 'unsupported' && (
        <EmptyPanel title="Contributor analysis unavailable for this metric">
          {state.message}
        </EmptyPanel>
      )}
      {state.kind === 'error' && (
        <ErrorPanel
          title="Contributor analysis unavailable"
          error={state.error}
          onRetry={() => setAttempt((n) => n + 1)}
        />
      )}
      {state.kind === 'success' && <ContributorBreakdown analysis={state.data} />}
    </section>
  )
}

function Detail({ anomaly }: { anomaly: AnomalyDetailOut }) {
  const { snapshot, threshold } = anomaly
  const show = (value: number) => formatThresholdValue(value, threshold.comparison)
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <SeverityBadge severity={anomaly.severity} />
          <h2 className="text-lg font-semibold">{anomaly.display_name}</h2>
          <span className="text-sm text-slate-600">{formatDimensions(anomaly.dimensions)}</span>
        </div>
        <p className="text-sm text-slate-600">
          Window {formatUtc(anomaly.window_start)} – {formatUtc(anomaly.window_end)} · status{' '}
          {humanize(anomaly.status)} · <EvidenceId id={anomaly.evidence_id} />
        </p>
      </header>

      <section
        aria-labelledby="current-vs-baseline-heading"
        className="grid grid-cols-1 gap-4 md:grid-cols-3"
      >
        <h3 id="current-vs-baseline-heading" className="sr-only">
          Current vs baseline
        </h3>
        <dl className="contents">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <dt className="text-xs uppercase tracking-wide text-slate-500">Current window</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">
              {formatMetricValue(snapshot.value, snapshot.unit)}
            </dd>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <dt className="text-xs uppercase tracking-wide text-slate-500">7-day baseline</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">
              {snapshot.baseline_value === null
                ? 'No baseline'
                : formatMetricValue(snapshot.baseline_value, snapshot.unit)}
            </dd>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <dt className="text-xs uppercase tracking-wide text-slate-500">Change</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{formatChange(snapshot)}</dd>
          </div>
        </dl>
      </section>
      <p className="text-xs text-slate-500">
        Metric snapshot <EvidenceId id={snapshot.evidence_id} /> · {snapshot.sample_size} records
      </p>

      <section
        aria-labelledby="detector-heading"
        className="rounded-lg border border-slate-200 bg-white p-4"
      >
        <h3 id="detector-heading" className="text-base font-semibold">
          Detector explanation
        </h3>
        <p className="mt-2 text-sm">{anomaly.explanation}</p>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm md:grid-cols-4">
          <dt className="text-slate-500">Rule</dt>
          <dd className="font-mono text-xs">{threshold.detector_key}</dd>
          <dt className="text-slate-500">Observed</dt>
          <dd className="tabular-nums">
            {show(threshold.observed)}
          </dd>
          <dt className="text-slate-500">Medium threshold</dt>
          <dd className="tabular-nums">
            {show(threshold.medium_threshold)}
          </dd>
          <dt className="text-slate-500">High threshold</dt>
          <dd className="tabular-nums">
            {show(threshold.high_threshold)}
          </dd>
        </dl>
        {threshold.guards.length > 0 && (
          <ul className="mt-3 space-y-0.5 text-xs text-slate-600">
            {threshold.guards.map((guard) => (
              <li key={guard.name}>
                {guard.passed ? 'Passed' : 'Failed'}: {humanize(guard.name)} (required{' '}
                {formatMetricValue(guard.required, 'count')}, actual{' '}
                {formatMetricValue(guard.actual, 'count')})
              </li>
            ))}
          </ul>
        )}
      </section>

      <Contributors evidenceId={anomaly.evidence_id} />
    </div>
  )
}

export function AnomalyDrilldownPage() {
  const { evidenceId = '' } = useParams()
  const load = useCallback(() => getAnomaly(evidenceId), [evidenceId])
  const { state, reload } = useApiResource(load)

  return (
    <div className="space-y-4">
      <Link to="/anomalies" className="text-sm text-sky-700 hover:underline">
        ← All anomalies
      </Link>
      {state.kind === 'loading' && <LoadingPanel label="Loading anomaly…" />}
      {state.kind === 'error' &&
        (NOT_FOUND_CODES.has(state.error.code) ? (
          <EmptyPanel title="Anomaly not found">
            No anomaly exists with evidence ID <EvidenceId id={evidenceId} />.
          </EmptyPanel>
        ) : (
          <ErrorPanel title="Anomaly unavailable" error={state.error} onRetry={reload} />
        ))}
      {state.kind === 'success' && <Detail anomaly={state.data} />}
    </div>
  )
}
