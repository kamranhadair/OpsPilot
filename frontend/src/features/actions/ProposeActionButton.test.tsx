import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { action, actionDetail, brief, invalidBrief } from '../../../tests/fixtures/api'
import { api, pending, resetApi } from '../../../tests/mockClient'
import { renderAt } from '../../../tests/renderAt'
import { ApiError } from '../../api/client'

const PROPOSE = { name: 'Propose investigation' }

describe('Propose investigation from a brief', () => {
  beforeEach(resetApi)

  it('is offered only on a validated brief', async () => {
    api.getBrief.mockResolvedValue(invalidBrief())
    renderAt('/briefs/12')
    await screen.findByRole('heading', { name: 'Billing ticket volume is elevated' })
    expect(screen.queryByRole('button', PROPOSE)).toBeNull()
  })

  it('creates a proposal and opens it awaiting approval', async () => {
    api.getBrief.mockResolvedValue(brief())
    api.proposeAction.mockResolvedValue(action())
    api.getAction.mockResolvedValue(actionDetail())
    renderAt('/briefs/12')

    await userEvent.click(await screen.findByRole('button', PROPOSE))

    expect(api.proposeAction).toHaveBeenCalledWith(12)
    expect(await screen.findByText('Awaiting human approval')).toBeInTheDocument()
    expect(api.getAction).toHaveBeenCalledWith(5)
  })

  it('disables itself while drafting', async () => {
    api.getBrief.mockResolvedValue(brief())
    api.proposeAction.mockReturnValue(pending())
    renderAt('/briefs/12')

    await userEvent.click(await screen.findByRole('button', PROPOSE))

    expect(screen.getByRole('button', { name: 'Drafting investigation…' })).toBeDisabled()
  })

  it('links to the existing proposal on a duplicate request', async () => {
    api.getBrief.mockResolvedValue(brief())
    api.proposeAction.mockRejectedValue(
      new ApiError('Brief 12 already has proposal 5.', 409, 'ACTION_ALREADY_PROPOSED', {
        body: {
          code: 'ACTION_ALREADY_PROPOSED',
          message: 'Brief 12 already has proposal 5.',
          existing_action_id: 5,
        },
      }),
    )
    renderAt('/briefs/12')

    await userEvent.click(await screen.findByRole('button', PROPOSE))

    expect(await screen.findByRole('link', { name: 'View action #5' })).toHaveAttribute(
      'href',
      '/actions/5',
    )
  })

  it('shows a rejected proposal with its policy issues', async () => {
    api.getBrief.mockResolvedValue(brief())
    api.proposeAction.mockRejectedValue(
      new ApiError('The proposed action failed validation.', 422, 'ACTION_PROPOSAL_REJECTED', {
        body: {
          code: 'ACTION_PROPOSAL_REJECTED',
          message: 'The proposed action failed validation.',
          issues: [
            {
              code: 'EVIDENCE_NOT_IN_BRIEF',
              message: 'ANOM-999999 is not evidence cited by the source brief.',
              evidence_id: 'ANOM-999999',
            },
          ],
        },
      }),
    )
    renderAt('/briefs/12')

    await userEvent.click(await screen.findByRole('button', PROPOSE))

    expect(await screen.findByRole('alert')).toHaveTextContent('ACTION_PROPOSAL_REJECTED')
    expect(screen.getByText(/ANOM-999999 is not evidence cited/)).toBeInTheDocument()
  })
})
