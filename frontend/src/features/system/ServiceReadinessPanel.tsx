import type { ReactNode } from 'react'

import { getSystemHealth } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import { formatUtc } from '../../lib/format'
import type { SystemHealthResponse } from '../../types/api'
import { SystemStatusBadge } from './SystemStatusBadge'

function Item({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className="mt-0.5 font-medium text-slate-900">{children}</dd>
    </div>
  )
}

/** The backend's readiness report, shown as returned. */
function Readiness({ health }: { health: SystemHealthResponse }) {
  return (
    <dl className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
      <Item label="Overall">
        <SystemStatusBadge status={health.status} />
      </Item>
      <Item label="Service">{health.service}</Item>
      <Item label="Environment">{health.environment}</Item>
      <Item label="Checked">{formatUtc(health.checked_at)}</Item>
      <Item label="Database">
        <SystemStatusBadge status={health.database.status} />
      </Item>
      <Item label="Migration revision">
        {health.database.migration_revision === null ? (
          <span className="text-slate-500">unknown</span>
        ) : (
          <span className="font-mono text-xs">{health.database.migration_revision}</span>
        )}
      </Item>
      <Item label="LLM provider">
        <SystemStatusBadge status={health.llm.configured ? 'configured' : 'not_configured'} />
        {health.llm.model !== null && (
          <span className="ml-2 font-mono text-xs text-slate-600">{health.llm.model}</span>
        )}
      </Item>
      <Item label="Cost estimation">
        <SystemStatusBadge
          status={health.cost_estimation.configured ? 'configured' : 'not_configured'}
        />
      </Item>
      <Item label="Model-based evaluation">
        <SystemStatusBadge status={health.evaluation.model_enabled ? 'enabled' : 'disabled'} />
      </Item>
      <Item label="Latest evaluation report">
        <SystemStatusBadge status={health.evaluation.latest_report} />
      </Item>
    </dl>
  )
}

export function ServiceReadinessPanel() {
  const { state, reload } = useApiResource(getSystemHealth)

  return (
    <section
      aria-labelledby="readiness-heading"
      className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="flex items-center justify-between gap-4">
        <h3 id="readiness-heading" className="text-base font-semibold">
          Service readiness
        </h3>
        <button
          type="button"
          onClick={reload}
          className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50"
        >
          Re-check
        </button>
      </div>
      <div className="mt-4 space-y-4">
        {state.kind === 'loading' && <LoadingPanel label="Checking service readiness…" />}
        {state.kind === 'error' && (
          <>
            <ErrorPanel
              title={
                state.error.code === 'DATABASE_UNAVAILABLE'
                  ? 'Database unavailable'
                  : state.error.code === 'SYSTEM_ENDPOINTS_DISABLED'
                    ? 'System endpoints are disabled in this environment'
                    : 'Could not load service readiness'
              }
              error={state.error}
              onRetry={reload}
            />
            {state.error.body?.health && <Readiness health={state.error.body.health} />}
          </>
        )}
        {state.kind === 'success' && <Readiness health={state.data} />}
      </div>
    </section>
  )
}
