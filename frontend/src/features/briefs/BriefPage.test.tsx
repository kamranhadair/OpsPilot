import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  brief,
  eventEvidence,
  invalidBrief,
  metricEvidence,
} from '../../../tests/fixtures/api'
import { api, pending, resetApi } from '../../../tests/mockClient'
import { renderAt } from '../../../tests/renderAt'
import { ApiError } from '../../api/client'

describe('BriefPage', () => {
  beforeEach(resetApi)

  it('shows a loading state while the brief is in flight', () => {
    api.getBrief.mockReturnValue(pending())
    renderAt('/briefs/12')
    expect(screen.getByText('Loading brief…')).toBeInTheDocument()
    expect(api.getBrief).toHaveBeenCalledWith(12)
  })

  it('renders a validated brief with clickable evidence chips', async () => {
    api.getBrief.mockResolvedValue(brief())
    renderAt('/briefs/12')

    expect(
      await screen.findByRole('heading', { name: 'Billing ticket volume is elevated' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Validated against evidence/)).toBeInTheDocument()
    expect(screen.queryByText(/Failed validation/)).not.toBeInTheDocument()
    const claims = within(screen.getByRole('region', { name: 'Claims' })).getAllByRole('listitem')
    expect(claims).toHaveLength(2)
    expect(
      within(claims[0]!).getByRole('button', { name: 'Show evidence MTR-000101' }),
    ).toBeInTheDocument()
    expect(
      within(claims[0]!).getByRole('button', { name: 'Show evidence ANOM-000007' }),
    ).toBeInTheDocument()
  })

  it('opens the provenance drawer with backend windows, values and sample', async () => {
    api.getBrief.mockResolvedValue(brief())
    api.getEvidence.mockResolvedValue(metricEvidence())
    renderAt('/briefs/12')

    await userEvent.click(await screen.findByRole('button', { name: 'Show evidence MTR-000101' }))

    const drawer = await screen.findByRole('dialog', { name: /Evidence MTR-000101/ })
    expect(api.getEvidence).toHaveBeenCalledWith('MTR-000101')
    expect(await within(drawer).findByText('Ticket volume (category=billing)')).toBeInTheDocument()
    const values = within(drawer).getByRole('region', { name: 'Values' })
    expect(within(values).getByText('412')).toBeInTheDocument()
    expect(within(values).getByText('301.5')).toBeInTheDocument()
    expect(within(values).getByText('Unavailable')).toBeInTheDocument()
    expect(
      within(values).getByText('Baseline is zero; percentage change is undefined.'),
    ).toBeInTheDocument()
    const scope = within(drawer).getByRole('region', { name: 'Scope and sample' })
    expect(scope).toHaveTextContent('02 Oct 2026, 00:00 UTC → 03 Oct 2026, 00:00 UTC')
    expect(scope).toHaveTextContent('412')
    expect(scope).toHaveTextContent('Category: Billing')
    expect(within(drawer).getByText('count(tickets created in window)')).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows the non-causal disclaimer for timeline events', async () => {
    api.getBrief.mockResolvedValue(brief())
    api.getEvidence.mockResolvedValue(eventEvidence())
    renderAt('/briefs/12')

    await userEvent.click(await screen.findByRole('button', { name: 'Show evidence EVT-000004' }))

    const drawer = await screen.findByRole('dialog')
    expect(await within(drawer).findByRole('note')).toHaveTextContent(
      'no link to the metric change has been established',
    )
    expect(within(drawer).getByText('01 Oct 2026, 18:00 UTC')).toBeInTheDocument()
  })

  it('handles a resolver 404 as evidence no longer available', async () => {
    api.getBrief.mockResolvedValue(invalidBrief())
    api.getEvidence.mockRejectedValue(
      new ApiError('Evidence MTR-999999 was not found.', 404, 'EVIDENCE_NOT_FOUND'),
    )
    renderAt('/briefs/13')

    await userEvent.click(await screen.findByRole('button', { name: 'Show evidence MTR-999999' }))

    const drawer = await screen.findByRole('dialog')
    expect(await within(drawer).findByText('Evidence no longer available')).toBeInTheDocument()
    expect(within(drawer).getByText('EVIDENCE_NOT_FOUND')).toBeInTheDocument()
  })

  it('handles other resolver errors with a retry', async () => {
    api.getBrief.mockResolvedValue(brief())
    api.getEvidence.mockRejectedValueOnce(new ApiError('Server error', 500, 'HTTP_500'))
    api.getEvidence.mockResolvedValueOnce(metricEvidence())
    renderAt('/briefs/12')

    await userEvent.click(await screen.findByRole('button', { name: 'Show evidence MTR-000101' }))
    const drawer = await screen.findByRole('dialog')
    expect(await within(drawer).findByText('Could not load evidence')).toBeInTheDocument()

    await userEvent.click(within(drawer).getByRole('button', { name: 'Retry' }))
    expect(await within(drawer).findByText('Ticket volume (category=billing)')).toBeInTheDocument()
  })

  it('visibly separates an invalid brief and lists its validation errors', async () => {
    api.getBrief.mockResolvedValue(invalidBrief())
    renderAt('/briefs/13')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Failed validation — not validated operational truth')
    expect(alert).toHaveTextContent('EVIDENCE_NOT_IN_BUNDLE')
    expect(alert).toHaveTextContent('Claim 2:')
    expect(screen.queryByText(/Validated against evidence/)).not.toBeInTheDocument()
    const claims = within(screen.getByRole('region', { name: 'Claims' })).getAllByRole('listitem')
    expect(within(claims[1]!).getByText('Invalid')).toBeInTheDocument()
    expect(within(claims[0]!).getByText('Valid')).toBeInTheDocument()
  })

  it('shows not found for a missing brief', async () => {
    api.getBrief.mockRejectedValue(new ApiError('Brief 99 does not exist.', 404, 'BRIEF_NOT_FOUND'))
    renderAt('/briefs/99')
    expect(await screen.findByText('Brief not found')).toBeInTheDocument()
  })
})

describe('LatestBriefPage', () => {
  beforeEach(resetApi)

  it('renders the latest validated brief', async () => {
    api.getLatestBrief.mockResolvedValue(brief())
    renderAt('/briefs')
    expect(
      await screen.findByRole('heading', { name: 'Billing ticket volume is elevated' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Validated against evidence/)).toBeInTheDocument()
  })

  it('shows an empty state when no validated brief exists', async () => {
    api.getLatestBrief.mockRejectedValue(
      new ApiError('No validated brief is available.', 404, 'NO_VALIDATED_BRIEF'),
    )
    renderAt('/briefs')
    expect(await screen.findByText('No validated brief yet')).toBeInTheDocument()
  })

  it('shows an error state with retry for other failures', async () => {
    api.getLatestBrief.mockRejectedValue(new ApiError('down', 0, 'NETWORK_UNREACHABLE'))
    renderAt('/briefs')
    expect(await screen.findByText('Could not load the brief')).toBeInTheDocument()
  })
})
