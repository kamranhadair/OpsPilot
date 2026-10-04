/**
 * Demo-only "Run analysis" control for the dashboard (Spec 15).
 * Hidden outside demo environments; shows only what the backend run returned.
 */

import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, getDemoStatus, runDemoAnalysis } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import { SeverityBadge } from '../../components/SeverityBadge'
import { formatUtc } from '../../lib/format'
import type { AnalysisBriefOut, AnalysisRunResponse } from '../../types/api'

type RunState =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'error'; error: ApiError }
  | { kind: 'done'; result: AnalysisRunResponse }

function scope(dimensions: Record<string, string>): string {
  const parts = Object.entries(dimensions).map(([key, value]) => `${key}: ${value}`)
  return parts.length > 0 ? parts.join(', ') : 'overall'
}

function BriefOutcome({ brief }: { brief: AnalysisBriefOut }) {
  if (brief.state === 'generated' && brief.brief_id !== null) {
    return (
      <p>
        Brief {brief.status ?? 'unknown'}:{' '}
        <Link to={`/briefs/${brief.brief_id}`} className="text-sky-700 hover:underline">
          open brief #{brief.brief_id}
        </Link>
      </p>
    )
  }
  if (brief.state === 'not_configured') {
    return (
      <p className="text-slate-600">
        AI brief not generated: the LLM is not configured (OPENAI_API_KEY / OPENAI_MODEL).
        Deterministic metrics, anomalies and contributors are still available.
      </p>
    )
  }
  return (
    <p className="text-red-700">
      AI brief failed ({brief.error_code ?? 'unknown error'}). Deterministic results were kept.
    </p>
  )
}

function RunResult({ result }: { result: AnalysisRunResponse }) {
  const top = result.anomalies[0]
  return (
    <div role="status" aria-label="Analysis result" className="mt-4 space-y-2 text-sm">
      <p>
        Analysed the window ending {formatUtc(result.window_end)}:{' '}
        {result.anomalies.length} anomaly(ies), {result.evidence.allowed_evidence_ids.length}{' '}
        evidence item(s).
      </p>
      {top ? (
        <p className="flex flex-wrap items-center gap-2">
          <span>Most severe:</span>
          <SeverityBadge severity={top.severity} />
          <Link to={`/anomalies/${top.evidence_id}`} className="text-sky-700 hover:underline">
            {top.display_name} ({scope(top.dimensions)})
          </Link>
        </p>
      ) : (
        <p className="text-slate-600">No anomalies were detected for this window.</p>
      )}
      <BriefOutcome brief={result.brief} />
    </div>
  )
}

export function RunAnalysisPanel({ onAnalysed }: { onAnalysed: () => void }) {
  const { state } = useApiResource(getDemoStatus)
  const [run, setRun] = useState<RunState>({ kind: 'idle' })

  const start = useCallback(async () => {
    setRun({ kind: 'running' })
    try {
      const result = await runDemoAnalysis()
      setRun({ kind: 'done', result })
      onAnalysed()
    } catch (error) {
      setRun({
        kind: 'error',
        error:
          error instanceof ApiError
            ? error
            : new ApiError('Unexpected client error.', 0, 'CLIENT_ERROR'),
      })
    }
  }, [onAnalysed])

  if (state.kind === 'loading') return <LoadingPanel label="Checking demo status…" />
  if (state.kind === 'error') {
    if (state.error.code === 'DEMO_DISABLED') return null
    return <ErrorPanel title="Demo status unavailable" error={state.error} />
  }
  if (!state.data.dataset_seeded) {
    return (
      <EmptyPanel title="Demo dataset not seeded">
        Reset and seed it with{' '}
        <code className="font-mono text-xs">python -m app.scripts.demo reset</code>.
      </EmptyPanel>
    )
  }

  return (
    <section
      aria-labelledby="demo-analysis-heading"
      className="rounded-lg border border-sky-200 bg-sky-50 p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 id="demo-analysis-heading" className="text-sm font-semibold">
            Demo analysis
          </h3>
          <p className="text-xs text-slate-600">
            Computes metrics, anomalies, contributors and the evidence bundle for the final
            window, then a validated brief when the LLM is configured. It never proposes or
            executes actions.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void start()}
          disabled={run.kind === 'running'}
          className="rounded bg-sky-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-800 disabled:opacity-60"
        >
          {run.kind === 'running' ? 'Running analysis…' : 'Run analysis'}
        </button>
      </div>
      {run.kind === 'error' && (
        <div className="mt-4">
          <ErrorPanel title="Analysis failed" error={run.error} />
        </div>
      )}
      {run.kind === 'done' && <RunResult result={run.result} />}
    </section>
  )
}
