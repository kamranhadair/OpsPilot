import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { anomalyDetail, contributors } from '../../../tests/fixtures/api'
import { api, pending, resetApi } from '../../../tests/mockClient'
import { renderAt } from '../../../tests/renderAt'
import { ApiError } from '../../api/client'

const notComputed = () =>
  new ApiError('No contributors are stored; compute them first.', 404, 'CONTRIBUTORS_NOT_COMPUTED')

describe('AnomalyDrilldownPage', () => {
  beforeEach(resetApi)

  it('shows a loading state while the anomaly is in flight', () => {
    api.getAnomaly.mockReturnValue(pending())
    renderAt('/anomalies/ANOM-000007')
    expect(screen.getByText('Loading anomaly…')).toBeInTheDocument()
  })

  it('renders severity, current vs baseline and the detector explanation from the API', async () => {
    api.getAnomaly.mockResolvedValue(anomalyDetail())
    api.getContributors.mockResolvedValue(contributors())
    renderAt('/anomalies/ANOM-000007')

    expect(await screen.findByRole('heading', { name: 'Ticket volume' })).toBeInTheDocument()
    expect(screen.getByText('high')).toBeInTheDocument()
    expect(screen.getByText('Category: Billing')).toBeInTheDocument()

    const values = screen.getByRole('region', { name: 'Current vs baseline' })
    expect(within(values).getByText('168')).toBeInTheDocument()
    expect(within(values).getByText('80')).toBeInTheDocument()
    expect(within(values).getByText('+110.0%')).toBeInTheDocument()

    const detector = screen.getByRole('region', { name: 'Detector explanation' })
    expect(detector).toHaveTextContent('meeting the high threshold of 50%')
    expect(detector).toHaveTextContent('pct_change.v1')
    expect(screen.getAllByText('ANOM-000007').length).toBeGreaterThan(0)
    expect(screen.getByText('MTR-000120')).toBeInTheDocument()
  })

  it('surfaces EMEA / Enterprise first in the contributor breakdown', async () => {
    api.getAnomaly.mockResolvedValue(anomalyDetail())
    api.getContributors.mockResolvedValue(contributors())
    renderAt('/anomalies/ANOM-000007')

    const breakdown = await screen.findByRole('region', { name: 'Contributor breakdown' })
    const groups = await within(breakdown).findAllByRole('heading', { level: 4 })
    // The API sends region first; the region + tier family leads the view.
    expect(groups.map((g) => g.textContent)).toEqual(['Region + Tier', 'Region'])

    const lead = within(breakdown).getByRole('table', { name: 'Region + Tier contributors' })
    const first = within(lead).getAllByRole('row')[1]!
    expect(within(first).getByText('EMEA / Enterprise')).toBeInTheDocument()
    expect(within(first).getByText('77.3%')).toBeInTheDocument()
    expect(within(first).getByText('SEG-000031')).toBeInTheDocument()
    expect(first).toHaveTextContent('accounts for 77.3% of the observed positive change')
    expect(within(breakdown).getByText('New Segment')).toBeInTheDocument()
    expect(within(breakdown).getByText('Other segments: 13.8%')).toBeInTheDocument()
  })

  it('offers to compute contributors when none are stored, then renders them', async () => {
    api.getAnomaly.mockResolvedValue(anomalyDetail())
    api.getContributors.mockRejectedValue(notComputed())
    api.computeContributors.mockResolvedValue({ ...contributors(), status: 'computed' })
    renderAt('/anomalies/ANOM-000007')

    expect(await screen.findByText('Contributor analysis not computed yet')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Compute contributors' }))

    expect(api.computeContributors).toHaveBeenCalledWith('ANOM-000007')
    expect(await screen.findByText('SEG-000031')).toBeInTheDocument()
  })

  it('explains when the metric does not support contributor analysis', async () => {
    api.getAnomaly.mockResolvedValue(anomalyDetail())
    api.getContributors.mockRejectedValue(
      new ApiError('first_response_minutes is not additive.', 422, 'SEGMENTATION_NOT_SUPPORTED'),
    )
    renderAt('/anomalies/ANOM-000007')
    expect(
      await screen.findByText('Contributor analysis unavailable for this metric'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Compute contributors' })).not.toBeInTheDocument()
  })

  it('shows an empty state when there are no positive contributors', async () => {
    api.getAnomaly.mockResolvedValue(anomalyDetail())
    api.getContributors.mockResolvedValue({ ...contributors(), groups: [] })
    renderAt('/anomalies/ANOM-000007')
    expect(await screen.findByText('No positive contributors were found.')).toBeInTheDocument()
  })

  it('shows not found for an unknown anomaly', async () => {
    api.getAnomaly.mockRejectedValue(
      new ApiError('Anomaly ANOM-999999 was not found.', 404, 'ANOMALY_NOT_FOUND'),
    )
    renderAt('/anomalies/ANOM-999999')
    expect(await screen.findByText('Anomaly not found')).toBeInTheDocument()
    expect(api.getContributors).not.toHaveBeenCalled()
  })

  it('shows a retryable error when the backend is unreachable', async () => {
    api.getAnomaly
      .mockRejectedValueOnce(
        new ApiError('Could not reach the OpsPilot API.', 0, 'NETWORK_UNREACHABLE'),
      )
      .mockResolvedValueOnce(anomalyDetail())
    api.getContributors.mockResolvedValue(contributors())
    renderAt('/anomalies/ANOM-000007')

    expect(await screen.findByText('Anomaly unavailable')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('heading', { name: 'Ticket volume' })).toBeInTheDocument()
  })
})
