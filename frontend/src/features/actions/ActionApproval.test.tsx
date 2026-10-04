import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  actionDetail,
  approvedActionDetail,
  execution,
  failedActionDetail,
  rejectedActionDetail,
  succeededActionDetail,
} from '../../../tests/fixtures/api'
import { api, pending, resetApi } from '../../../tests/mockClient'
import { renderAt } from '../../../tests/renderAt'
import { ApiError } from '../../api/client'

const APPROVE = { name: 'Approve' }
const REJECT = { name: 'Reject' }
const APPROVE_AND_CREATE = { name: 'Approve & create investigation' }
const EXECUTE = { name: 'Create investigation' }

async function openPending() {
  api.getAction.mockResolvedValue(actionDetail())
  renderAt('/actions/5')
  await screen.findByRole('heading', { name: 'Human review' })
}

describe('Action review panel', () => {
  beforeEach(resetApi)

  it('prefills a demo reviewer identity and says it is not authentication', async () => {
    await openPending()
    expect(screen.getByLabelText('Reviewer')).toHaveValue('Operations Manager')
    expect(screen.getByText(/not verified/)).toBeInTheDocument()
  })

  it.each([
    ['approved', approvedActionDetail()],
    ['succeeded', succeededActionDetail()],
    ['rejected', rejectedActionDetail()],
    ['failed', failedActionDetail()],
  ])('is hidden for a %s action', async (_label, detail) => {
    api.getAction.mockResolvedValue(detail)
    renderAt('/actions/5')
    await screen.findByRole('heading', { name: 'Audit timeline' })
    expect(screen.queryByRole('heading', { name: 'Human review' })).toBeNull()
    expect(screen.queryByRole('button', APPROVE)).toBeNull()
    expect(screen.queryByRole('button', REJECT)).toBeNull()
  })

  it('follows allowed_operations rather than the status', async () => {
    api.getAction.mockResolvedValue(actionDetail({ allowed_operations: ['reject'] }))
    renderAt('/actions/5')
    expect(await screen.findByRole('button', REJECT)).toBeInTheDocument()
    expect(screen.queryByRole('button', APPROVE)).toBeNull()
    expect(screen.queryByRole('button', APPROVE_AND_CREATE)).toBeNull()

    api.getAction.mockResolvedValue(actionDetail({ allowed_operations: [] }))
    renderAt('/actions/5')
    expect(screen.queryAllByRole('heading', { name: 'Human review' })).toHaveLength(1)
  })

  it('approves without edits when nothing was changed', async () => {
    api.approveAction.mockResolvedValue(approvedActionDetail({ approval: null }))
    await openPending()

    await userEvent.click(screen.getByRole('button', APPROVE))

    expect(api.approveAction).toHaveBeenCalledWith(5, {
      reviewer: 'Operations Manager',
      comment: null,
    })
    expect(api.executeAction).not.toHaveBeenCalled()
  })

  it('sends only the fields the reviewer changed, then shows the returned state', async () => {
    api.approveAction.mockResolvedValue(approvedActionDetail())
    await openPending()

    const title = screen.getByLabelText('Title')
    await userEvent.clear(title)
    await userEvent.type(title, 'Investigate EMEA Billing ticket spike (edited)')
    await userEvent.type(screen.getByLabelText('Comment (optional)'), 'Looks right')
    await userEvent.click(screen.getByRole('button', APPROVE))

    expect(api.approveAction).toHaveBeenCalledWith(5, {
      reviewer: 'Operations Manager',
      comment: 'Looks right',
      edits: { title: 'Investigate EMEA Billing ticket spike (edited)' },
    })
    expect(
      await screen.findByRole('heading', { name: 'Investigate EMEA Billing ticket spike (edited)' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Approved by Operations Manager')).toBeInTheDocument()
    expect(screen.getByText(/Human edits before approval: Title/)).toBeInTheDocument()
    expect(screen.getByRole('button', EXECUTE)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Human review' })).toBeNull()
  })

  it('sends edited investigation steps as a list', async () => {
    api.approveAction.mockResolvedValue(approvedActionDetail())
    await openPending()

    const steps = screen.getByLabelText('Investigation steps (one per line)')
    await userEvent.type(steps, '\nCompare with last quarter')
    await userEvent.click(screen.getByRole('button', APPROVE))

    expect(api.approveAction).toHaveBeenCalledWith(5, {
      reviewer: 'Operations Manager',
      comment: null,
      edits: {
        investigation_steps: [
          'Review the top contributing segment',
          'Check the billing deploy',
          'Compare with last quarter',
        ],
      },
    })
  })

  it('rejects with the reviewer and comment', async () => {
    api.rejectAction.mockResolvedValue(rejectedActionDetail())
    await openPending()

    const reviewer = screen.getByLabelText('Reviewer')
    await userEvent.clear(reviewer)
    await userEvent.type(reviewer, 'Support Lead')
    await userEvent.type(screen.getByLabelText('Comment (optional)'), 'Duplicate')
    await userEvent.click(screen.getByRole('button', REJECT))

    expect(api.rejectAction).toHaveBeenCalledWith(5, { reviewer: 'Support Lead', comment: 'Duplicate' })
    expect(api.approveAction).not.toHaveBeenCalled()
    expect(await screen.findByText('Rejected by Operations Manager')).toBeInTheDocument()
    expect(screen.getByText('Rejected actions are never executed.')).toBeInTheDocument()
  })

  it('disables the controls while a decision is in flight', async () => {
    api.approveAction.mockReturnValue(pending())
    await openPending()

    await userEvent.click(screen.getByRole('button', APPROVE))

    expect(screen.getByRole('button', { name: 'Approving…' })).toBeDisabled()
    expect(screen.getByRole('button', REJECT)).toBeDisabled()
    expect(screen.getByRole('button', APPROVE_AND_CREATE)).toBeDisabled()
  })

  it('"Approve & create" approves first, then executes as a second request', async () => {
    const calls: string[] = []
    api.approveAction.mockImplementation(() => {
      calls.push('approve')
      return Promise.resolve(approvedActionDetail())
    })
    api.executeAction.mockImplementation(() => {
      calls.push('execute')
      return Promise.resolve(succeededActionDetail())
    })
    await openPending()

    await userEvent.click(screen.getByRole('button', APPROVE_AND_CREATE))

    expect(await screen.findByText('INV-0001')).toBeInTheDocument()
    expect(calls).toEqual(['approve', 'execute'])
    expect(api.executeAction).toHaveBeenCalledWith(5)
    expect(screen.getByText('Mock investigation created')).toBeInTheDocument()
  })

  it('"Approve & create" does not execute when approval fails', async () => {
    api.approveAction.mockRejectedValue(
      new ApiError('Reviewer must be a human.', 422, 'REVIEWER_NOT_HUMAN'),
    )
    await openPending()

    await userEvent.click(screen.getByRole('button', APPROVE_AND_CREATE))

    expect(await screen.findByRole('alert')).toHaveTextContent('Reviewer must be a human.')
    expect(api.executeAction).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { name: 'Human review' })).toBeInTheDocument()
  })

  it('lists the reasons an edit was refused and keeps the form', async () => {
    api.approveAction.mockRejectedValue(
      new ApiError('Edits failed the action policy.', 422, 'ACTION_EDIT_REJECTED', {
        body: {
          code: 'ACTION_EDIT_REJECTED',
          message: 'Edits failed the action policy.',
          issues: [
            {
              code: 'CAUSAL_LANGUAGE',
              message: 'Do not assert causation.',
              phrase: 'caused by',
              field: 'description',
            },
          ],
        },
      }),
    )
    await openPending()

    await userEvent.type(screen.getByLabelText('Description', { selector: 'textarea' }), ' Caused by the deploy.')
    await userEvent.click(screen.getByRole('button', APPROVE))

    expect(await screen.findByText('Your edits were not accepted')).toBeInTheDocument()
    const issues = within(screen.getByRole('list', { name: 'Edit issues' }))
    expect(issues.getByText(/CAUSAL_LANGUAGE/)).toBeInTheDocument()
    expect(issues.getByText(/Do not assert causation/)).toBeInTheDocument()
    expect(issues.getByText(/caused by/)).toBeInTheDocument()
    expect(screen.getByLabelText('Description', { selector: 'textarea' })).toHaveValue(
      'Review billing ticket volume against the seven-day baseline. Caused by the deploy.',
    )
  })

  it('reloads and explains when the action changed since it was loaded', async () => {
    api.rejectAction.mockRejectedValue(
      new ApiError('Cannot reject an action in status approved.', 409, 'ACTION_INVALID_TRANSITION', {
        body: {
          code: 'ACTION_INVALID_TRANSITION',
          message: 'Cannot reject an action in status approved.',
          current_status: 'approved',
        },
      }),
    )
    await openPending()
    api.getAction.mockResolvedValue(approvedActionDetail())

    await userEvent.click(screen.getByRole('button', REJECT))

    expect(
      await screen.findByText('This action changed since you loaded it'),
    ).toBeInTheDocument()
    expect(screen.getByText('Cannot reject an action in status approved.')).toBeInTheDocument()
    expect(await screen.findByRole('button', EXECUTE)).toBeInTheDocument()
    expect(api.getAction).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('heading', { name: 'Human review' })).toBeNull()
  })
})

describe('Action execution panel', () => {
  beforeEach(resetApi)

  it('offers execution only when the backend allows it', async () => {
    api.getAction.mockResolvedValue(approvedActionDetail())
    renderAt('/actions/5')
    expect(await screen.findByRole('button', EXECUTE)).toBeInTheDocument()
    expect(screen.getByText(/Worth a look before the weekly review/)).toBeInTheDocument()
  })

  it('executes and shows the mock investigation reference', async () => {
    api.getAction.mockResolvedValue(approvedActionDetail())
    api.executeAction.mockResolvedValue(succeededActionDetail())
    renderAt('/actions/5')

    await userEvent.click(await screen.findByRole('button', EXECUTE))

    expect(api.executeAction).toHaveBeenCalledWith(5)
    expect(await screen.findByText('INV-0001')).toBeInTheDocument()
    expect(screen.getByText(/mock reference; no external system was contacted/)).toBeInTheDocument()
    expect(screen.queryByRole('button', EXECUTE)).toBeNull()
  })

  it('shows a succeeded action without an execute control', async () => {
    api.getAction.mockResolvedValue(succeededActionDetail())
    renderAt('/actions/5')
    expect(await screen.findByText('INV-0001')).toBeInTheDocument()
    expect(screen.queryByRole('button', EXECUTE)).toBeNull()
  })

  it('shows the safe error message of a failed execution', async () => {
    api.getAction.mockResolvedValue(failedActionDetail())
    renderAt('/actions/5')
    expect(await screen.findByText('Execution failed')).toBeInTheDocument()
    expect(screen.getByText('Mock investigation adapter is unavailable.')).toBeInTheDocument()
    expect(screen.queryByText('INV-0001')).toBeNull()
  })

  it('shows an in-progress execution', async () => {
    api.getAction.mockResolvedValue(
      approvedActionDetail({
        status: 'executing',
        execution: execution({ status: 'executing', external_ref: null, finished_at: null }),
        allowed_operations: [],
      }),
    )
    renderAt('/actions/5')
    expect(await screen.findByText(/Execution in progress/)).toBeInTheDocument()
  })

  it('handles a 502 execution failure by reporting it and reloading', async () => {
    api.getAction.mockResolvedValue(approvedActionDetail())
    const failed = failedActionDetail()
    api.executeAction.mockRejectedValue(
      new ApiError('The investigation adapter failed.', 502, 'ACTION_EXECUTION_FAILED', {
        body: {
          code: 'ACTION_EXECUTION_FAILED',
          message: 'The investigation adapter failed.',
          execution: failed.execution ?? undefined,
        },
      }),
    )
    renderAt('/actions/5')
    const execute = await screen.findByRole('button', EXECUTE)
    api.getAction.mockResolvedValue(failed)
    await userEvent.click(execute)

    expect(await screen.findByText('The investigation could not be created')).toBeInTheDocument()
    expect(await screen.findByText('Mock investigation adapter is unavailable.')).toBeInTheDocument()
    expect(screen.queryByRole('button', EXECUTE)).toBeNull()
    expect(api.getAction).toHaveBeenCalledTimes(2)
  })

  it('reports an unconfigured adapter without reloading', async () => {
    api.getAction.mockResolvedValue(approvedActionDetail())
    api.executeAction.mockRejectedValue(
      new ApiError('No investigation adapter is configured.', 503, 'ADAPTER_NOT_CONFIGURED'),
    )
    renderAt('/actions/5')
    await userEvent.click(await screen.findByRole('button', EXECUTE))

    expect(await screen.findByText('No investigation adapter is configured.')).toBeInTheDocument()
    expect(screen.getByRole('button', EXECUTE)).toBeEnabled()
    expect(api.getAction).toHaveBeenCalledTimes(1)
  })
})

describe('Audit timeline', () => {
  beforeEach(resetApi)

  it('renders the backend events in order with actor and time', async () => {
    api.getAction.mockResolvedValue(succeededActionDetail())
    renderAt('/actions/5')

    const list = within(await screen.findByRole('list', { name: 'Audit events' }))
    const items = list.getAllByRole('listitem')
    expect(items.map((item) => item.querySelector('p')?.textContent)).toEqual([
      'Proposed',
      'Status Changed',
      'Edited',
      'Approved',
      'Execution Started',
      'Execution Succeeded',
    ])
    expect(items[0]).toHaveTextContent('AI')
    expect(items[0]).toHaveTextContent('action_proposer')
    expect(items[1]).toHaveTextContent('System')
    expect(items[3]).toHaveTextContent('Human')
    expect(items[3]).toHaveTextContent('Operations Manager')
    expect(items[5]).toHaveTextContent('action.execution_succeeded')
  })
})
