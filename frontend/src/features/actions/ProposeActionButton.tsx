import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, NETWORK_ERROR_CODE, proposeAction } from '../../api/client'
import { ErrorPanel } from '../../components/StatePanels'

type ProposeState = { kind: 'idle' } | { kind: 'submitting' } | { kind: 'error'; error: ApiError }

/**
 * Ask the backend to draft an investigation for a validated brief. The backend decides
 * eligibility; this control only reports the outcome and links to the proposal.
 */
export function ProposeActionButton({ briefId }: { briefId: number }) {
  const navigate = useNavigate()
  const [state, setState] = useState<ProposeState>({ kind: 'idle' })

  async function submit() {
    setState({ kind: 'submitting' })
    try {
      const action = await proposeAction(briefId)
      navigate(`/actions/${action.id}`)
    } catch (error) {
      setState({
        kind: 'error',
        error:
          error instanceof ApiError
            ? error
            : new ApiError('Unexpected client error.', 0, NETWORK_ERROR_CODE, { cause: error }),
      })
    }
  }

  const existingId =
    state.kind === 'error' && state.error.code === 'ACTION_ALREADY_PROPOSED'
      ? (state.error.body?.existing_action_id ?? null)
      : null

  return (
    <section aria-label="Next step" className="space-y-2">
      <button
        type="button"
        onClick={() => void submit()}
        disabled={state.kind === 'submitting'}
        className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
      >
        {state.kind === 'submitting' ? 'Drafting investigation…' : 'Propose investigation'}
      </button>
      <p className="text-xs text-slate-500">
        AI drafts a proposal for human review. Nothing is approved or executed.
      </p>
      {existingId !== null ? (
        <p role="status" className="text-sm text-slate-700">
          This brief already has a proposal.{' '}
          <Link to={`/actions/${existingId}`} className="text-sky-700 underline">
            View action #{existingId}
          </Link>
        </p>
      ) : (
        state.kind === 'error' && (
          <ErrorPanel title="Could not propose an investigation" error={state.error} />
        )
      )}
      {state.kind === 'error' && state.error.body?.issues && (
        <ul className="list-disc pl-5 text-sm text-red-800">
          {state.error.body.issues.map((issue, index) => (
            <li key={index}>
              <span className="font-mono text-xs">{issue.code}</span> {issue.message}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
