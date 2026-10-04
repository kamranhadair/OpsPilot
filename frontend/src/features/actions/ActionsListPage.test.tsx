import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { action } from '../../../tests/fixtures/api'
import { api, pending, resetApi } from '../../../tests/mockClient'
import { renderAt } from '../../../tests/renderAt'
import { ApiError } from '../../api/client'

describe('ActionsListPage', () => {
  beforeEach(resetApi)

  it('shows a loading state', () => {
    api.listActions.mockReturnValue(pending())
    renderAt('/actions')
    expect(screen.getByText('Loading actions…')).toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    api.listActions.mockResolvedValue({ items: [], limit: 50, offset: 0 })
    renderAt('/actions')
    expect(await screen.findByText('No proposed actions')).toBeInTheDocument()
  })

  it('shows an error state with retry', async () => {
    api.listActions.mockRejectedValueOnce(new ApiError('down', 503, 'HTTP_503'))
    api.listActions.mockResolvedValueOnce({ items: [], limit: 50, offset: 0 })
    renderAt('/actions')

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load actions')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('No proposed actions')).toBeInTheDocument()
  })

  it('lists actions in backend order with status and links', async () => {
    api.listActions.mockResolvedValue({
      items: [action(), action({ id: 4, title: 'Older proposal', status: 'rejected' })],
      limit: 50,
      offset: 0,
    })
    renderAt('/actions')

    const rows = within(await screen.findByRole('table')).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(
      within(rows[0]!).getByRole('link', { name: 'Investigate EMEA Billing ticket spike' }),
    ).toHaveAttribute('href', '/actions/5')
    expect(within(rows[0]!).getByText('Pending Approval')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('Rejected')).toBeInTheDocument()
    expect(api.listActions).toHaveBeenCalledWith({})
  })

  it('filters by status through the API', async () => {
    api.listActions.mockResolvedValue({ items: [], limit: 50, offset: 0 })
    renderAt('/actions')
    await screen.findByText('No proposed actions')

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'pending_approval')

    expect(api.listActions).toHaveBeenLastCalledWith({ status: 'pending_approval' })
  })
})
