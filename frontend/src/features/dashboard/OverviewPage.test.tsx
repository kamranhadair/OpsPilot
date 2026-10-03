import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { anomalyDetail, contributors, overview } from '../../../tests/fixtures/api'
import { api, pending, resetApi } from '../../../tests/mockClient'
import { renderAt } from '../../../tests/renderAt'
import { ApiError } from '../../api/client'

describe('OverviewPage', () => {
  beforeEach(resetApi)

  it('shows a loading state while the overview is in flight', () => {
    api.getDashboardOverview.mockReturnValue(pending())
    renderAt('/')
    expect(screen.getByText('Loading operations overview…')).toBeInTheDocument()
  })

  it('renders metric cards with the API values and baselines', async () => {
    api.getDashboardOverview.mockResolvedValue(overview())
    renderAt('/')

    const volume = await screen.findByRole('region', { name: 'Ticket volume' })
    expect(within(volume).getByText('412')).toBeInTheDocument()
    expect(within(volume).getByText('301.5')).toBeInTheDocument()
    expect(within(volume).getByText('+36.7%')).toBeInTheDocument()
    expect(within(volume).getByText('MTR-000101')).toBeInTheDocument()

    const sla = screen.getByRole('region', { name: 'SLA breach rate' })
    expect(within(sla).getByText('12.4%')).toBeInTheDocument()
    // Rate change is the backend's percentage-point difference, not recomputed.
    expect(within(sla).getByText('+4.3 pp')).toBeInTheDocument()

    expect(screen.getByRole('region', { name: 'Open backlog' })).toBeInTheDocument()
    const escalation = screen.getByRole('region', { name: 'Escalation rate' })
    expect(within(escalation).getAllByText('No baseline')).toHaveLength(2)
    expect(within(escalation).getByText(/below minimum sample size/i)).toBeInTheDocument()
  })

  it('renders cards in the order the API returned them', async () => {
    api.getDashboardOverview.mockResolvedValue(overview())
    renderAt('/')
    await screen.findByRole('region', { name: 'Ticket volume' })
    const cards = within(screen.getByRole('region', { name: 'Current metrics' }))
      .getAllByRole('heading', { level: 3 })
      .map((h) => h.textContent)
    expect(cards).toEqual(['Ticket volume', 'Open backlog', 'SLA breach rate', 'Escalation rate'])
  })

  it('draws trends from the API series and flags too-short history', async () => {
    api.getDashboardOverview.mockResolvedValue(overview())
    renderAt('/')

    const volume = await screen.findByRole('region', { name: 'Ticket volume trend' })
    expect(within(volume).getByRole('img', { name: /3 daily windows/ })).toBeInTheDocument()
    const table = within(volume).getByRole('table', { name: 'Ticket volume daily values' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getAllByRole('cell')[1]?.textContent)).toEqual([
      '298',
      '305',
      '412',
    ])
    expect(within(table).getByText('MTR-000202')).toBeInTheDocument()

    const sla = screen.getByRole('region', { name: 'SLA breach rate trend' })
    expect(within(sla).getByText(/not enough history/i)).toBeInTheDocument()
    expect(within(sla).queryByRole('img')).not.toBeInTheDocument()
  })

  it('lists active anomalies and navigates to the drilldown on click', async () => {
    api.getDashboardOverview.mockResolvedValue(overview())
    api.getAnomaly.mockResolvedValue(anomalyDetail())
    api.getContributors.mockResolvedValue(contributors())
    renderAt('/')

    const panel = await screen.findByRole('region', { name: 'Active anomalies (2)' })
    const rows = within(panel).getAllByRole('row').slice(1)
    expect(within(rows[0]!).getByText('high')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('Category: Billing')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('+110.0%')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('+7.9 pp')).toBeInTheDocument()

    await userEvent.click(within(rows[0]!).getByRole('link', { name: 'Ticket volume' }))
    expect(await screen.findByRole('heading', { name: 'Detector explanation' })).toBeInTheDocument()
    expect(api.getAnomaly).toHaveBeenCalledWith('ANOM-000007')
  })

  it('shows an explicit empty state when no metrics are computed', async () => {
    api.getDashboardOverview.mockResolvedValue(
      overview({
        window_end: null,
        cards: [],
        trends: [],
        active_anomalies: [],
        active_anomaly_total: 0,
      }),
    )
    renderAt('/')
    expect(await screen.findByText('No metrics computed yet')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Ticket volume' })).not.toBeInTheDocument()
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  })

  it('shows an empty state when there are no active anomalies', async () => {
    api.getDashboardOverview.mockResolvedValue(
      overview({ active_anomalies: [], active_anomaly_total: 0 }),
    )
    renderAt('/')
    expect(await screen.findByText('No active anomalies')).toBeInTheDocument()
  })

  it('shows an error with retry when the backend is unreachable', async () => {
    api.getDashboardOverview
      .mockRejectedValueOnce(
        new ApiError('Could not reach the OpsPilot API.', 0, 'NETWORK_UNREACHABLE'),
      )
      .mockResolvedValueOnce(overview())
    renderAt('/')

    const alert = await screen.findByText('Overview unavailable')
    expect(alert.closest('[role="alert"]')).toHaveTextContent('NETWORK_UNREACHABLE')
    expect(screen.queryByRole('region', { name: 'Ticket volume' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('region', { name: 'Ticket volume' })).toBeInTheDocument()
  })
})
