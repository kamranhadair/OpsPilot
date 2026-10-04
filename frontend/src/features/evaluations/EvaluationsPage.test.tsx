import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { evalCase, evaluationReport } from '../../../tests/fixtures/api'
import { api, pending, resetApi } from '../../../tests/mockClient'
import { renderAt } from '../../../tests/renderAt'
import { ApiError } from '../../api/client'
import type { EvaluationReport } from '../../types/api'

function available(overrides: Partial<EvaluationReport> = {}) {
  api.getLatestEvaluation.mockResolvedValue({
    state: 'available',
    report: evaluationReport(overrides),
    message: null,
  })
}

async function renderReport(overrides: Partial<EvaluationReport> = {}) {
  available(overrides)
  renderAt('/evaluations')
  await screen.findByText('Overall status')
}

describe('EvaluationsPage', () => {
  beforeEach(resetApi)

  it('shows a loading state', () => {
    api.getLatestEvaluation.mockReturnValue(pending())
    renderAt('/evaluations')
    expect(screen.getByText('Loading evaluation report…')).toBeInTheDocument()
  })

  it('shows a generic error with retry', async () => {
    api.getLatestEvaluation.mockRejectedValueOnce(new ApiError('down', 503, 'HTTP_503'))
    api.getLatestEvaluation.mockResolvedValueOnce({
      state: 'not_run',
      report: null,
      message: 'No report.',
    })
    renderAt('/evaluations')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load the evaluation report',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('No evaluation report yet')).toBeInTheDocument()
  })

  it('shows the invalid-report error code', async () => {
    api.getLatestEvaluation.mockRejectedValue(
      new ApiError('The stored evaluation report could not be parsed.', 500, 'EVAL_REPORT_INVALID'),
    )
    renderAt('/evaluations')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The stored evaluation report is invalid')
    expect(alert).toHaveTextContent('EVAL_REPORT_INVALID')
    expect(alert).toHaveTextContent('could not be parsed')
  })

  it('shows the not-run empty state with the CLI hint', async () => {
    api.getLatestEvaluation.mockResolvedValue({
      state: 'not_run',
      report: null,
      message: 'No evaluation report has been generated yet.',
    })
    renderAt('/evaluations')

    expect(await screen.findByText('No evaluation report yet')).toBeInTheDocument()
    expect(screen.getByText('No evaluation report has been generated yet.')).toBeInTheDocument()
    expect(screen.getByText('python -m app.evals.run --suite all')).toBeInTheDocument()
  })

  it('shows the report header, seed info and synthetic-data note', async () => {
    await renderReport()

    expect(screen.getByText('Overall status').parentElement).toHaveTextContent('FAIL')
    expect(screen.getByText('Partial failure')).toBeInTheDocument()
    expect(screen.getByText('f053e710-5ba3-44b9-a692-2d963eef1d2d')).toBeInTheDocument()
    expect(screen.getByText(/04 Oct 2026, 05:50 UTC/)).toBeInTheDocument()
    expect(screen.getByText(/· matches/)).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Report notes' })).getByText(
      /Small synthetic demo dataset/,
    )).toBeInTheDocument()
    // Seed matches, so no warning banner.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows report ratios as given, with a null rate as n/a', async () => {
    await renderReport()

    const fixture = screen.getByRole('listitem', { name: 'Metric fixture pass rate' })
    expect(fixture).toHaveTextContent('100.0%')
    expect(fixture).toHaveTextContent('6/6')

    const recall = screen.getByRole('listitem', { name: 'Planted anomaly recall' })
    expect(recall).toHaveTextContent('n/a')
    expect(recall).toHaveTextContent('0/0')
    expect(recall).not.toHaveTextContent('0.0%')
    expect(recall).not.toHaveTextContent('100.0%')

    const fp = screen.getByRole('listitem', {
      name: 'High/critical false positives on normal cases',
    })
    expect(fp).toHaveTextContent('4.2%')
    expect(fp).toHaveTextContent('1/24')

    const guard = screen.getByRole('listitem', { name: 'Runtime causation guard' })
    expect(within(guard).getByText('Pass').nextElementSibling).toHaveTextContent('3')
    expect(within(guard).getByText('Not run').nextElementSibling).toHaveTextContent('0')
  })

  it('shows the category table with backend pass rates', async () => {
    await renderReport()

    const table = screen.getByRole('table', { name: 'Evaluation results by category' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(3)
    expect(within(rows[0]!).getByRole('rowheader')).toHaveTextContent('Metric Correctness')
    expect(rows[0]).toHaveTextContent('100.0%')
    expect(within(rows[1]!).getByRole('rowheader')).toHaveTextContent('Anomaly Detection')
    expect(rows[1]).toHaveTextContent('n/a')
    expect(within(rows[2]!).getByRole('rowheader')).toHaveTextContent('Approval Boundary')
    expect(rows[2]).toHaveTextContent('0.0%')
  })

  it('shows failed and errored case details, and lists not-run cases separately', async () => {
    await renderReport()

    const failed = screen.getByRole('region', { name: /Failed and errored cases \(2\)/ })
    const errored = within(failed).getByRole('listitem', {
      name: 'approval.execute_pending_blocked',
    })
    expect(errored).toHaveTextContent('ERROR')
    expect(errored).toHaveTextContent('Execute without approval is blocked')
    expect(errored).toHaveTextContent('Approval Boundary')
    expect(errored).toHaveTextContent('blocked')
    expect(errored).toHaveTextContent('No observation recorded')
    expect(errored).toHaveTextContent('investigation_steps_json')

    const fail = within(failed).getByRole('listitem', { name: 'contributor.billing_top_k' })
    expect(fail).toHaveTextContent('FAIL')
    expect(fail).toHaveTextContent('category=billing within top 3')
    expect(fail).toHaveTextContent('category=billing ranked 5')
    expect(fail).toHaveTextContent('Expected segment ranked outside the top 3.')
    // Passing cases are not listed as failures.
    expect(
      within(failed).queryByRole('listitem', { name: 'metric.volume_doubles' }),
    ).not.toBeInTheDocument()

    const notRun = screen.getByRole('region', { name: /Cases not run \(1\)/ })
    const skipped = within(notRun).getByRole('listitem', {
      name: 'anomaly.planted_billing_spike',
    })
    expect(skipped).toHaveTextContent('NOT RUN')
    expect(skipped).toHaveTextContent('Demo seed missing; dataset case skipped.')
    expect(skipped).not.toHaveTextContent('PASS')
  })

  it('labels the model-based section and shows NOT RUN with its reason', async () => {
    await renderReport()

    const model = screen.getByRole('region', { name: 'Model-based (non-deterministic)' })
    expect(model).toHaveTextContent('NOT RUN')
    expect(model).toHaveTextContent('disabled: EVAL_MODEL_ENABLED is not true')
    expect(within(model).queryByText('Model')).not.toBeInTheDocument()
  })

  it('shows a completed model-based section with model name and cases', async () => {
    await renderReport({
      model_based: {
        label: 'model_based',
        status: 'completed',
        reason: null,
        model_name: 'gpt-test-mini',
        prompt_version: 'citation-judge-v1',
        cases: [
          evalCase({
            case_id: 'judge.claim_1',
            title: 'Claim 1 is supported by its evidence',
            category: 'citation_validity',
            status: 'pass',
            expected: 'supported',
            observed: 'supported',
          }),
        ],
      },
    })

    const model = screen.getByRole('region', { name: 'Model-based (non-deterministic)' })
    expect(model).toHaveTextContent('COMPLETED')
    expect(model).toHaveTextContent('gpt-test-mini')
    expect(model).toHaveTextContent('citation-judge-v1')
    expect(within(model).getByRole('listitem', { name: 'judge.claim_1' })).toHaveTextContent(
      'Claim 1 is supported by its evidence',
    )
  })

  it('shows replay days including a no-data day', async () => {
    await renderReport()

    const replay = screen.getByRole('region', { name: 'Replay summary' })
    expect(replay).toHaveTextContent('Read-only replay')
    const rows = within(
      within(replay).getByRole('table', { name: 'Daily replay of anomaly detection' }),
    )
      .getAllByRole('row')
      .slice(1)
    expect(rows).toHaveLength(2)

    expect(within(rows[0]!).getByRole('rowheader')).toHaveTextContent('27 Sept')
    expect(rows[0]).toHaveTextContent('NO DATA')
    expect(rows[0]).toHaveTextContent('No tickets in the window.')

    expect(within(rows[1]!).getByRole('rowheader')).toHaveTextContent('28 Sept')
    expect(rows[1]).toHaveTextContent('OK')
    expect(within(rows[1]!).getAllByRole('cell')[1]).toHaveTextContent('2')
    const anomalies = within(rows[1]!).getAllByRole('listitem')
    expect(anomalies[0]).toHaveTextContent('SLA breach rate · overall · high')
    expect(anomalies[1]).toHaveTextContent('SLA breach rate · Category: Billing · high')
    expect(anomalies[2]).toHaveTextContent('Ticket volume · Category: Integration · medium')
  })

  it('warns when the demo seed is missing or mismatched', async () => {
    await renderReport({
      overall_status: 'incomplete',
      partial_failure: false,
      seed: {
        expected_version: '1',
        case_version: '1',
        observed_state: 'empty',
        observed_version: null,
        matches: false,
      },
    })

    expect(screen.getByText('Overall status').parentElement).toHaveTextContent('INCOMPLETE')
    const banner = screen.getByRole('alert')
    expect(banner).toHaveTextContent('Demo seed missing or mismatched')
    expect(banner).toHaveTextContent('Dataset cases did not run')
    expect(banner).toHaveTextContent('Empty')
  })
})
