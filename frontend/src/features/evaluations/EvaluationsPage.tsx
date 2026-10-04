import { getLatestEvaluation } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import type { EvaluationLatestResponse, EvaluationReport } from '../../types/api'
import { CaseDetails } from './CaseList'
import { CategoryTable } from './CategoryTable'
import { DeterministicSummary } from './DeterministicSummary'
import { ModelBasedSection } from './ModelBasedSection'
import { ReplaySummary } from './ReplaySummary'
import { ReportHeader } from './ReportHeader'

const RUN_COMMAND = 'python -m app.evals.run --suite all'

function Report({ report }: { report: EvaluationReport }) {
  return (
    <div className="space-y-8">
      <ReportHeader report={report} />
      {report.notes.length > 0 && (
        <ul aria-label="Report notes" className="space-y-1 text-sm text-slate-600">
          {report.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      <div className="space-y-8">
        <DeterministicSummary ratios={report.ratios} counts={report.counts} />
        <CategoryTable categories={report.categories} />
        <CaseDetails cases={report.cases} />
        <ReplaySummary replay={report.replay} />
      </div>
      <ModelBasedSection section={report.model_based} />
    </div>
  )
}

function Latest({ data }: { data: EvaluationLatestResponse }) {
  if (data.state === 'not_run') {
    return (
      <EmptyPanel title="No evaluation report yet">
        {data.message && <p>{data.message}</p>}
        <p className="mt-1">
          Run the evaluation suite from the backend:{' '}
          <code className="font-mono text-xs">{RUN_COMMAND}</code>
        </p>
      </EmptyPanel>
    )
  }
  return <Report report={data.report} />
}

/** `/evaluations`: the latest stored evaluation report, exactly as the runner wrote it. */
export function EvaluationsPage() {
  const { state, reload } = useApiResource(getLatestEvaluation)

  return (
    <section aria-labelledby="evaluations-heading" className="space-y-4">
      <h2 id="evaluations-heading" className="text-lg font-semibold">
        Evaluations
      </h2>
      {state.kind === 'loading' && <LoadingPanel label="Loading evaluation report…" />}
      {state.kind === 'error' && (
        <ErrorPanel
          title={
            state.error.code === 'EVAL_REPORT_INVALID'
              ? 'The stored evaluation report is invalid'
              : 'Could not load the evaluation report'
          }
          error={state.error}
          onRetry={reload}
        />
      )}
      {state.kind === 'success' && <Latest data={state.data} />}
    </section>
  )
}
