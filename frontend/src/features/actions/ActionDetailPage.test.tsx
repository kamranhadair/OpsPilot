import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { actionDetail, metricEvidence, rejectedActionDetail } from '../../../tests/fixtures/api'
import { api, pending, resetApi } from '../../../tests/mockClient'
import { renderAt } from '../../../tests/renderAt'
import { ApiError } from '../../api/client'

describe('ActionDetailPage', () => {
  beforeEach(resetApi)

  it('shows a loading state while the action is in flight', () => {
    api.getAction.mockReturnValue(pending())
    renderAt('/actions/5')
    expect(screen.getByText('Loading action…')).toBeInTheDocument()
    expect(api.getAction).toHaveBeenCalledWith(5)
  })

  it('renders the draft, its steps, the source brief and the pending state', async () => {
    api.getAction.mockResolvedValue(actionDetail())
    renderAt('/actions/5')

    expect(
      await screen.findByRole('heading', { name: 'Investigate EMEA Billing ticket spike' }),
    ).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Description' })).getByText(/Review billing ticket volume/)).toBeInTheDocument()
    expect(screen.getByText(/coinciding deploy warrant investigation/)).toBeInTheDocument()
    const steps = within(screen.getByRole('region', { name: 'Suggested investigation steps' }))
    expect(steps.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('Pending Approval')).toBeInTheDocument()
    expect(screen.getByText('Awaiting human approval')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Brief #12: Billing ticket volume is elevated' }),
    ).toHaveAttribute('href', '/briefs/12')
  })

  it('offers review controls only for the operations the backend allows', async () => {
    api.getAction.mockResolvedValue(actionDetail())
    renderAt('/actions/5')
    await screen.findByText('Awaiting human approval')

    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create investigation' })).toBeNull()
  })

  it('renders evidence citations that open provenance', async () => {
    api.getAction.mockResolvedValue(actionDetail())
    api.getEvidence.mockResolvedValue(metricEvidence())
    renderAt('/actions/5')

    const evidence = within(await screen.findByRole('region', { name: 'Evidence' }))
    for (const id of ['ANOM-000007', 'MTR-000101', 'EVT-000004']) {
      expect(evidence.getByRole('button', { name: `Show evidence ${id}` })).toBeInTheDocument()
    }
    await userEvent.click(evidence.getByRole('button', { name: 'Show evidence MTR-000101' }))

    expect(await screen.findByRole('dialog', { name: /Evidence MTR-000101/ })).toBeInTheDocument()
    expect(api.getEvidence).toHaveBeenCalledWith('MTR-000101')
  })

  it('does not show the pending banner for other backend states', async () => {
    api.getAction.mockResolvedValue(rejectedActionDetail())
    renderAt('/actions/5')
    expect(await screen.findByText('Rejected by Operations Manager')).toBeInTheDocument()
    expect(screen.queryByText('Awaiting human approval')).toBeNull()
  })

  it('shows not-found and error states', async () => {
    api.getAction.mockRejectedValueOnce(new ApiError('Action 5 does not exist.', 404, 'ACTION_NOT_FOUND'))
    const { unmount } = renderAt('/actions/5')
    expect(await screen.findByText('Action not found')).toBeInTheDocument()
    unmount()

    api.getAction.mockRejectedValueOnce(new ApiError('boom', 500, 'HTTP_500'))
    renderAt('/actions/5')
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the action')
  })

  it('rejects a malformed action ID without calling the API', () => {
    renderAt('/actions/abc')
    expect(screen.getByText('Action not found')).toBeInTheDocument()
    expect(api.getAction).not.toHaveBeenCalled()
  })
})
