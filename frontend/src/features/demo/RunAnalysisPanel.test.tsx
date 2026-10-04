import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { analysisRun, demoStatus, overview } from '../../../tests/fixtures/api'
import { api, pending, resetApi } from '../../../tests/mockClient'
import { renderAt } from '../../../tests/renderAt'
import { ApiError } from '../../api/client'

describe('RunAnalysisPanel', () => {
  beforeEach(() => {
    resetApi()
    api.getDashboardOverview.mockResolvedValue(overview())
  })

  it('is hidden outside demo environments', async () => {
    renderAt('/')
    await screen.findByRole('region', { name: 'Ticket volume' })
    expect(screen.queryByRole('button', { name: 'Run analysis' })).not.toBeInTheDocument()
    expect(screen.queryByText('Checking demo status…')).not.toBeInTheDocument()
  })

  it('shows a loading state while the status is in flight', () => {
    api.getDemoStatus.mockReturnValue(pending())
    renderAt('/')
    expect(screen.getByText('Checking demo status…')).toBeInTheDocument()
  })

  it('shows a status error other than DEMO_DISABLED', async () => {
    api.getDemoStatus.mockRejectedValue(new ApiError('Boom', 500, 'HTTP_500'))
    renderAt('/')
    expect(await screen.findByText('Demo status unavailable')).toBeInTheDocument()
  })

  it('tells the user to reset when the dataset is not seeded', async () => {
    api.getDemoStatus.mockResolvedValue(demoStatus({ dataset_seeded: false }))
    renderAt('/')
    expect(await screen.findByText('Demo dataset not seeded')).toBeInTheDocument()
    expect(screen.getByText('python -m app.scripts.demo reset')).toBeInTheDocument()
  })

  it('runs the analysis, links the result and reloads the dashboard', async () => {
    api.getDemoStatus.mockResolvedValue(demoStatus())
    api.runDemoAnalysis.mockResolvedValue(analysisRun())
    renderAt('/')

    await userEvent.click(await screen.findByRole('button', { name: 'Run analysis' }))

    const result = await screen.findByRole('status', { name: 'Analysis result' })
    expect(within(result).getByText('high')).toBeInTheDocument()
    expect(
      within(result).getByRole('link', { name: 'Ticket volume (category: billing)' }),
    ).toHaveAttribute('href', '/anomalies/ANOM-000003')
    expect(within(result).getByRole('link', { name: 'open brief #7' })).toHaveAttribute(
      'href',
      '/briefs/7',
    )
    expect(api.runDemoAnalysis).toHaveBeenCalledTimes(1)
    expect(api.getDashboardOverview).toHaveBeenCalledTimes(2)
  })

  it('disables the button while the run is in flight', async () => {
    api.getDemoStatus.mockResolvedValue(demoStatus())
    api.runDemoAnalysis.mockReturnValue(pending())
    renderAt('/')

    await userEvent.click(await screen.findByRole('button', { name: 'Run analysis' }))
    expect(screen.getByRole('button', { name: 'Running analysis…' })).toBeDisabled()
  })

  it('states explicitly when the AI brief is not configured', async () => {
    api.getDemoStatus.mockResolvedValue(demoStatus({ llm_configured: false }))
    api.runDemoAnalysis.mockResolvedValue(
      analysisRun({
        brief: {
          state: 'not_configured',
          brief_id: null,
          status: null,
          error_code: 'LLM_NOT_CONFIGURED',
          message: 'not configured',
        },
      }),
    )
    renderAt('/')

    await userEvent.click(await screen.findByRole('button', { name: 'Run analysis' }))
    expect(await screen.findByText(/the LLM is not configured/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /open brief/ })).not.toBeInTheDocument()
  })

  it('shows a failed run with its error code', async () => {
    api.getDemoStatus.mockResolvedValue(demoStatus())
    api.runDemoAnalysis.mockRejectedValue(
      new ApiError('No ticket data.', 409, 'NO_SOURCE_DATA'),
    )
    renderAt('/')

    await userEvent.click(await screen.findByRole('button', { name: 'Run analysis' }))
    expect(await screen.findByText('Analysis failed')).toBeInTheDocument()
    expect(screen.getByText('NO_SOURCE_DATA')).toBeInTheDocument()
  })
})
