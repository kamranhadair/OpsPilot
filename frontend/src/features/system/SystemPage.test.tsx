import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  executionFailure,
  llmSummary,
  llmTrace,
  llmTraceList,
  systemHealth,
  systemSummary,
} from '../../../tests/fixtures/api'
import { api, pending, resetApi } from '../../../tests/mockClient'
import { renderAt } from '../../../tests/renderAt'
import { ApiError } from '../../api/client'

function section(name: string): HTMLElement {
  return screen.getByRole('region', { name })
}

describe('SystemPage', () => {
  beforeEach(resetApi)

  it('is linked from the primary navigation and routed at /system', async () => {
    renderAt('/system')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getByRole('link', { name: 'System' })).toHaveAttribute('href', '/system')
    expect(screen.getByRole('heading', { level: 2, name: 'System' })).toBeInTheDocument()
    expect(await screen.findByText('opspilot-api')).toBeInTheDocument()
  })

  it('shows loading states for every data view', () => {
    api.getSystemHealth.mockReturnValue(pending())
    api.getSystemSummary.mockReturnValue(pending())
    api.listLlmTraces.mockReturnValue(pending())
    renderAt('/system')

    expect(screen.getByText('Checking service readiness…')).toBeInTheDocument()
    expect(screen.getByText('Loading LLM call summary…')).toBeInTheDocument()
    expect(screen.getByText('Loading execution summary…')).toBeInTheDocument()
    expect(screen.getByText('Loading LLM traces…')).toBeInTheDocument()
  })

  it('shows readiness exactly as reported by the backend', async () => {
    api.getSystemHealth.mockResolvedValue(
      systemHealth({ status: 'degraded', llm: { configured: false, model: null } }),
    )
    renderAt('/system')

    const panel = section('Service readiness')
    expect(await within(panel).findByText('DEGRADED')).toBeInTheDocument()
    expect(within(panel).getByText('development')).toBeInTheDocument()
    expect(within(panel).getByText('0009_llm_trace_context')).toBeInTheDocument()
    expect(within(panel).getByText('LLM provider').nextSibling).toHaveTextContent(
      'NOT CONFIGURED',
    )
    expect(within(panel).getByText('Cost estimation').nextSibling).toHaveTextContent(
      'NOT CONFIGURED',
    )
  })

  it('shows DATABASE_UNAVAILABLE with the health body from the 503', async () => {
    api.getSystemHealth.mockRejectedValue(
      new ApiError('The database is unreachable.', 503, 'DATABASE_UNAVAILABLE', {
        body: {
          code: 'DATABASE_UNAVAILABLE',
          message: 'The database is unreachable.',
          health: systemHealth({
            status: 'error',
            database: { status: 'error', migration_revision: null },
          }),
        },
      }),
    )
    renderAt('/system')

    const panel = section('Service readiness')
    const alert = await within(panel).findByRole('alert')
    expect(alert).toHaveTextContent('Database unavailable')
    expect(alert).toHaveTextContent('DATABASE_UNAVAILABLE')
    expect(within(panel).getByText('Database').nextSibling).toHaveTextContent('ERROR')
    expect(within(panel).getByText('unknown')).toBeInTheDocument()
  })

  it('shows a summary error with retry that reloads', async () => {
    api.getSystemSummary.mockRejectedValueOnce(new ApiError('down', 500, 'HTTP_500'))
    renderAt('/system')

    const panel = section('LLM calls')
    expect(await within(panel).findByRole('alert')).toHaveTextContent(
      'Could not load the LLM call summary',
    )
    expect(
      within(section('Action execution failures')).getByRole('alert'),
    ).toHaveTextContent('Could not load the execution summary')

    await userEvent.click(within(panel).getByRole('button', { name: 'Retry' }))
    expect(await within(panel).findByText('LLM calls', { selector: 'dt' })).toBeInTheDocument()
    expect(api.getSystemSummary).toHaveBeenCalledTimes(2)
  })

  it('shows a trace error with retry', async () => {
    api.listLlmTraces.mockRejectedValueOnce(new ApiError('down', 500, 'HTTP_500'))
    renderAt('/system')

    const panel = section('Recent LLM traces')
    expect(await within(panel).findByRole('alert')).toHaveTextContent('Could not load LLM traces')
    await userEvent.click(within(panel).getByRole('button', { name: 'Retry' }))
    expect(await within(panel).findByText('No LLM traces recorded')).toBeInTheDocument()
  })

  it('renders backend summary values without recomputing them', async () => {
    renderAt('/system')
    const panel = section('LLM calls')

    expect(await within(panel).findByText('12')).toBeInTheDocument()
    expect(within(panel).getByText('10 succeeded · 2 failed')).toBeInTheDocument()
    expect(within(panel).getByText('Error rate', { selector: 'dt' }).nextSibling).toHaveTextContent('16.7%')
    const latency = within(panel).getByLabelText('Latency')
    expect(latency).toHaveTextContent('1.52 s')
    expect(latency).toHaveTextContent('1.40 s')
    expect(latency).toHaveTextContent('3.10 s')
    expect(latency).toHaveTextContent('4.20 s')
    expect(within(panel).getByText('31,200 / 6,420')).toBeInTheDocument()
    expect(within(panel).getByText('2 calls with usage not reported')).toBeInTheDocument()
    expect(within(panel).getByText('Brief Generation')).toBeInTheDocument()
    expect(within(panel).getByText('12.5%')).toBeInTheDocument()
  })

  it('shows cost as not configured when no rates are set', async () => {
    renderAt('/system')
    const panel = section('LLM calls')
    expect(await within(panel).findByText('Estimated cost')).toBeInTheDocument()
    expect(within(panel).getByText('Estimated cost').nextSibling).toHaveTextContent(
      'not configured',
    )
  })

  it('shows a configured cost as returned', async () => {
    api.getSystemSummary.mockResolvedValue(
      systemSummary({
        llm: llmSummary({ cost_configured: true, estimated_cost_usd: 0.0421, calls_missing_cost: 2 }),
      }),
    )
    renderAt('/system')
    const panel = section('LLM calls')
    expect(await within(panel).findByText('$0.0421')).toBeInTheDocument()
    expect(within(panel).getByText('2 calls with cost not reported')).toBeInTheDocument()
  })

  it('shows an empty summary when there were no calls', async () => {
    api.getSystemSummary.mockResolvedValue(
      systemSummary({
        llm: llmSummary({
          total_calls: 0,
          success_count: 0,
          error_count: 0,
          error_rate: null,
          latency_ms: null,
          by_operation: [],
        }),
      }),
    )
    renderAt('/system')
    expect(
      await within(section('LLM calls')).findByText('No LLM calls in this period'),
    ).toBeInTheDocument()
  })

  it('reloads the summary when the period changes', async () => {
    renderAt('/system')
    await within(section('LLM calls')).findByText('Error rate', { selector: 'dt' })
    expect(api.getSystemSummary).toHaveBeenLastCalledWith('7d')

    await userEvent.selectOptions(screen.getByLabelText('Period'), '24h')
    expect(api.getSystemSummary).toHaveBeenLastCalledWith('24h')
  })

  it('shows the empty trace state', async () => {
    renderAt('/system')
    expect(
      await within(section('Recent LLM traces')).findByText('No LLM traces recorded'),
    ).toBeInTheDocument()
    expect(api.listLlmTraces).toHaveBeenCalledWith({ limit: 25, offset: 0 })
  })

  it('renders trace rows with links, status and missing values', async () => {
    api.listLlmTraces.mockResolvedValue(
      llmTraceList({
        total: 2,
        items: [
          llmTrace(),
          llmTrace({
            id: 2,
            operation: 'action_proposal',
            status: 'error',
            input_tokens: null,
            output_tokens: null,
            estimated_cost_usd: null,
            error_code: 'LLM_TIMEOUT',
            error_message: 'The model call timed out.',
            brief_id: null,
            action_id: 5,
          }),
        ],
      }),
    )
    renderAt('/system')

    const panel = section('Recent LLM traces')
    const rows = await within(panel).findAllByRole('row')
    expect(rows).toHaveLength(3)
    const [, ok, failed] = rows

    expect(within(ok).getByText('SUCCESS')).toBeInTheDocument()
    expect(within(ok).getByText('3,120')).toBeInTheDocument()
    expect(within(ok).getByText('1.84 s')).toBeInTheDocument()
    expect(within(ok).getByText('—')).toBeInTheDocument()
    expect(within(ok).getByRole('link', { name: 'Brief #7' })).toHaveAttribute('href', '/briefs/7')

    expect(within(failed).getByText('ERROR')).toBeInTheDocument()
    expect(within(failed).getAllByText('not reported')).toHaveLength(2)
    expect(within(failed).getByText('LLM_TIMEOUT')).toBeInTheDocument()
    expect(within(failed).getByText('The model call timed out.')).toBeInTheDocument()
    expect(within(failed).getByRole('link', { name: 'Action #5' })).toHaveAttribute(
      'href',
      '/actions/5',
    )
    expect(within(panel).getByText('Showing 1–2 of 2')).toBeInTheDocument()
    expect(within(panel).getByRole('button', { name: 'Next' })).toBeDisabled()
    expect(within(panel).getByRole('button', { name: 'Prev' })).toBeDisabled()
  })

  it('pages traces by offset', async () => {
    const page = Array.from({ length: 25 }, (_, i) => llmTrace({ id: i + 1 }))
    api.listLlmTraces.mockResolvedValueOnce(llmTraceList({ items: page, total: 30 }))
    api.listLlmTraces.mockResolvedValueOnce(
      llmTraceList({ items: [llmTrace({ id: 26 })], total: 30, offset: 25 }),
    )
    renderAt('/system')

    const panel = section('Recent LLM traces')
    expect(await within(panel).findByText('Showing 1–25 of 30')).toBeInTheDocument()
    await userEvent.click(within(panel).getByRole('button', { name: 'Next' }))

    expect(api.listLlmTraces).toHaveBeenLastCalledWith({ limit: 25, offset: 25 })
    expect(await within(panel).findByText('Showing 26–26 of 30')).toBeInTheDocument()
    expect(within(panel).getByRole('button', { name: 'Prev' })).toBeEnabled()
  })

  it('lists recent execution failures', async () => {
    api.getSystemSummary.mockResolvedValue(
      systemSummary({
        executions: { total: 4, succeeded: 3, failed: 1, recent_failures: [executionFailure()] },
      }),
    )
    renderAt('/system')

    const panel = section('Action execution failures')
    const list = await within(panel).findByRole('list', { name: 'Recent execution failures' })
    expect(within(panel).getByText('4 executions · 3 succeeded · 1 failed')).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: 'Action #5' })).toHaveAttribute(
      'href',
      '/actions/5',
    )
    expect(within(list).getByText('ADAPTER_FAILED')).toBeInTheDocument()
    expect(within(list).getByText('Mock investigation adapter failed.')).toBeInTheDocument()
  })

  it('shows the empty execution failure state', async () => {
    renderAt('/system')
    expect(
      await within(section('Action execution failures')).findByText('No execution failures'),
    ).toBeInTheDocument()
  })
})
