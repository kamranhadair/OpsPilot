import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { anomaly, anomalyDetail, contributors } from '../../../tests/fixtures/api'
import { api, pending, resetApi } from '../../../tests/mockClient'
import { renderAt } from '../../../tests/renderAt'
import { ApiError } from '../../api/client'

const page = (items = [anomaly()], total = items.length, offset = 0) => ({
  items,
  total,
  limit: 25,
  offset,
})

describe('AnomalyExplorerPage', () => {
  beforeEach(resetApi)

  it('defaults to active anomalies and shows a loading state', () => {
    api.listAnomalies.mockReturnValue(pending())
    renderAt('/anomalies')
    expect(screen.getByText('Loading anomalies…')).toBeInTheDocument()
    expect(api.listAnomalies).toHaveBeenCalledWith({
      severity: undefined,
      status: 'active',
      limit: 25,
      offset: 0,
    })
  })

  it('renders severity, metric, context, change and detected window', async () => {
    api.listAnomalies.mockResolvedValue(page())
    renderAt('/anomalies')

    const table = await screen.findByRole('table', { name: 'Detected anomalies' })
    const row = within(table).getAllByRole('row')[1]!
    expect(within(row).getByText('high')).toBeInTheDocument()
    expect(within(row).getByRole('link', { name: 'Ticket volume' })).toHaveAttribute(
      'href',
      '/anomalies/ANOM-000007',
    )
    expect(within(row).getByText('Category: Billing')).toBeInTheDocument()
    expect(row).toHaveTextContent('168 vs 80')
    expect(within(row).getByText('+110.0%')).toBeInTheDocument()
    expect(within(row).getByText('03 Oct 2026, 00:00 UTC')).toBeInTheDocument()
    expect(within(row).getByText('ANOM-000007')).toBeInTheDocument()
  })

  it('shows the severity the API assigned, even when the numbers look different', async () => {
    // A huge change labelled "low": the UI must not re-derive severity from the score.
    api.listAnomalies.mockResolvedValue(page([anomaly({ severity: 'low', score: 900 })]))
    renderAt('/anomalies')
    const row = (await screen.findAllByRole('row'))[1]!
    expect(within(row).getByText('low')).toBeInTheDocument()
    expect(within(row).queryByText('high')).not.toBeInTheDocument()
  })

  it('passes the severity filter to the API', async () => {
    api.listAnomalies.mockResolvedValue(page())
    renderAt('/anomalies')
    await screen.findByRole('table', { name: 'Detected anomalies' })

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Severity' }), 'high')
    expect(api.listAnomalies).toHaveBeenLastCalledWith({
      severity: 'high',
      status: 'active',
      limit: 25,
      offset: 0,
    })

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'all')
    expect(api.listAnomalies).toHaveBeenLastCalledWith({
      severity: 'high',
      status: undefined,
      limit: 25,
      offset: 0,
    })
  })

  it('pages through results using the API total', async () => {
    api.listAnomalies.mockResolvedValue(page([anomaly()], 30))
    renderAt('/anomalies')
    await screen.findByText('Showing 1–1 of 30')
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(api.listAnomalies).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 25 }))
  })

  it('navigates to the drilldown when an anomaly is clicked', async () => {
    api.listAnomalies.mockResolvedValue(page())
    api.getAnomaly.mockResolvedValue(anomalyDetail())
    api.getContributors.mockResolvedValue(contributors())
    renderAt('/anomalies')

    await userEvent.click(await screen.findByRole('link', { name: 'Ticket volume' }))
    expect(await screen.findByRole('heading', { name: 'Detector explanation' })).toBeInTheDocument()
  })

  it('shows an empty state when nothing matches', async () => {
    api.listAnomalies.mockResolvedValue(page([]))
    renderAt('/anomalies')
    expect(await screen.findByText('No anomalies match these filters')).toBeInTheDocument()
  })

  it('shows an error state when the request fails', async () => {
    api.listAnomalies.mockRejectedValue(
      new ApiError('Could not reach the OpsPilot API.', 0, 'NETWORK_UNREACHABLE'),
    )
    renderAt('/anomalies')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Anomalies unavailable')
    expect(alert).toHaveTextContent('NETWORK_UNREACHABLE')
  })
})
