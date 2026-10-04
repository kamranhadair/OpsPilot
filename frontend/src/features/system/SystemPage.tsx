import { useCallback, useState } from 'react'

import { getSystemSummary } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import type { SummaryPeriod } from '../../types/api'
import { ExecutionFailuresPanel } from './ExecutionFailuresPanel'
import { LlmSummaryPanel } from './LlmSummaryPanel'
import { ServiceReadinessPanel } from './ServiceReadinessPanel'
import { TraceTable } from './TraceTable'

/** `/system`: readiness, LLM call health, traces and execution failures, as the backend reports them. */
export function SystemPage() {
  const [period, setPeriod] = useState<SummaryPeriod>('7d')
  const loadSummary = useCallback(() => getSystemSummary(period), [period])
  const summary = useApiResource(loadSummary)

  return (
    <section aria-labelledby="system-heading" className="space-y-6">
      <h2 id="system-heading" className="text-lg font-semibold">
        System
      </h2>
      <ServiceReadinessPanel />
      <LlmSummaryPanel
        state={summary.state}
        reload={summary.reload}
        period={period}
        onPeriodChange={setPeriod}
      />
      <ExecutionFailuresPanel state={summary.state} reload={summary.reload} />
      <TraceTable />
    </section>
  )
}
