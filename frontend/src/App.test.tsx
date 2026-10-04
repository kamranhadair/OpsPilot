import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { anomaly, anomalyDetail, contributors, overview } from '../tests/fixtures/api'
import { api, resetApi } from '../tests/mockClient'
import { renderAt } from '../tests/renderAt'

describe('App routes', () => {
  beforeEach(() => {
    resetApi()
    api.getDashboardOverview.mockResolvedValue(overview())
    api.listAnomalies.mockResolvedValue({ items: [anomaly()], total: 1, limit: 25, offset: 0 })
    api.getAnomaly.mockResolvedValue(anomalyDetail())
    api.getContributors.mockResolvedValue(contributors())
  })

  it('renders the shell with primary navigation on every route', async () => {
    renderAt('/')

    expect(screen.getByRole('heading', { level: 1, name: 'OpsPilot' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getByRole('link', { name: 'Dashboard' })).toHaveAttribute('href', '/')
    expect(within(nav).getByRole('link', { name: 'Anomalies' })).toHaveAttribute(
      'href',
      '/anomalies',
    )
    expect(within(nav).getByRole('link', { name: 'Briefs' })).toHaveAttribute('href', '/briefs')
    expect(within(nav).getByRole('link', { name: 'Actions' })).toHaveAttribute('href', '/actions')
    expect(within(nav).getByRole('link', { name: 'Evaluations' })).toHaveAttribute(
      'href',
      '/evaluations',
    )
    expect(within(nav).getByRole('link', { name: 'System' })).toHaveAttribute('href', '/system')
  })

  it('/ renders the operations overview', async () => {
    renderAt('/')
    expect(
      await screen.findByRole('heading', { name: 'Operations overview' }),
    ).toBeInTheDocument()
  })

  it('/anomalies renders the anomaly explorer', async () => {
    renderAt('/anomalies')
    expect(await screen.findByRole('heading', { name: 'Anomaly explorer' })).toBeInTheDocument()
  })

  it('/anomalies/:evidenceId renders the drilldown for that anomaly', async () => {
    renderAt('/anomalies/ANOM-000007')
    expect(await screen.findByRole('heading', { name: 'Ticket volume' })).toBeInTheDocument()
    expect(api.getAnomaly).toHaveBeenCalledWith('ANOM-000007')
  })

  it('/evaluations renders the evaluation report page', async () => {
    api.getLatestEvaluation.mockResolvedValue({
      state: 'not_run',
      report: null,
      message: 'No evaluation report has been generated yet.',
    })
    renderAt('/evaluations')
    expect(screen.getByRole('heading', { level: 2, name: 'Evaluations' })).toBeInTheDocument()
    expect(await screen.findByText('No evaluation report yet')).toBeInTheDocument()
    expect(api.getLatestEvaluation).toHaveBeenCalledTimes(1)
  })

  it('unknown routes show a not-found page', () => {
    renderAt('/nope')
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})
