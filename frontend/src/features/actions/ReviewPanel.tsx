import { useId, useState } from 'react'

import { humanize } from '../../lib/format'
import type {
  ActionDetailOut,
  ActionEdits,
  ApproveActionRequest,
  RejectActionRequest,
} from '../../types/api'
import type { ActionMutation } from './mutations'

const DEFAULT_REVIEWER = 'Operations Manager'

function sameSteps(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((step, index) => step === b[index])
}

/** Form diffing only: send a field only when the reviewer actually changed it. */
function changedEdits(
  action: ActionDetailOut,
  title: string,
  description: string,
  stepsText: string,
): ActionEdits | null {
  const edits: ActionEdits = {}
  const nextTitle = title.trim()
  const nextDescription = description.trim()
  const nextSteps = stepsText
    .split('\n')
    .map((step) => step.trim())
    .filter((step) => step.length > 0)

  if (nextTitle !== action.title) edits.title = nextTitle
  if (nextDescription !== action.description) edits.description = nextDescription
  if (!sameSteps(nextSteps, action.investigation_steps)) edits.investigation_steps = nextSteps
  return Object.keys(edits).length > 0 ? edits : null
}

const INPUT =
  'mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900 disabled:bg-slate-50'

/**
 * Human review of an AI-drafted investigation. Rendered only when the backend lists
 * `approve` or `reject` in `allowed_operations`; the backend re-checks every request.
 */
export function ReviewPanel({
  action,
  busy,
  onApprove,
  onReject,
  onApproveAndExecute,
}: {
  action: ActionDetailOut
  busy: ActionMutation | null
  onApprove: (body: ApproveActionRequest) => void
  onReject: (body: RejectActionRequest) => void
  onApproveAndExecute: (body: ApproveActionRequest) => void
}) {
  const ids = useId()
  const [reviewer, setReviewer] = useState(DEFAULT_REVIEWER)
  const [title, setTitle] = useState(action.title)
  const [description, setDescription] = useState(action.description)
  const [stepsText, setStepsText] = useState(action.investigation_steps.join('\n'))
  const [comment, setComment] = useState('')

  const canApprove = action.allowed_operations.includes('approve')
  const canReject = action.allowed_operations.includes('reject')
  const disabled = busy !== null
  const edits = changedEdits(action, title, description, stepsText)

  function decisionBase(): RejectActionRequest {
    const trimmed = comment.trim()
    return { reviewer, comment: trimmed.length > 0 ? trimmed : null }
  }

  function approveBody(): ApproveActionRequest {
    return edits ? { ...decisionBase(), edits } : decisionBase()
  }

  return (
    <section
      aria-labelledby={`${ids}-heading`}
      className="space-y-3 rounded-lg border border-slate-200 bg-white p-4"
    >
      <h3 id={`${ids}-heading`} className="font-medium text-slate-800">
        Human review
      </h3>

      <div>
        <label htmlFor={`${ids}-reviewer`} className="text-sm font-medium text-slate-700">
          Reviewer
        </label>
        <input
          id={`${ids}-reviewer`}
          value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
          disabled={disabled}
          aria-describedby={`${ids}-reviewer-help`}
          className={INPUT}
        />
        <p id={`${ids}-reviewer-help`} className="mt-1 text-xs text-slate-500">
          Demo identity recorded with the decision and in the audit log. V1 has no
          authentication, so this name is not verified.
        </p>
      </div>

      {canApprove && (
        <fieldset className="space-y-3" disabled={disabled}>
          <legend className="text-sm font-medium text-slate-700">
            Edit before approval (optional)
          </legend>
          <div>
            <label htmlFor={`${ids}-title`} className="text-sm text-slate-700">
              Title
            </label>
            <input
              id={`${ids}-title`}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className={INPUT}
            />
          </div>
          <div>
            <label htmlFor={`${ids}-description`} className="text-sm text-slate-700">
              Description
            </label>
            <textarea
              id={`${ids}-description`}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              className={INPUT}
            />
          </div>
          <div>
            <label htmlFor={`${ids}-steps`} className="text-sm text-slate-700">
              Investigation steps (one per line)
            </label>
            <textarea
              id={`${ids}-steps`}
              value={stepsText}
              onChange={(event) => setStepsText(event.target.value)}
              rows={Math.max(3, action.investigation_steps.length + 1)}
              className={INPUT}
            />
          </div>
          <p className="text-xs text-slate-500" role="note">
            {edits
              ? `Edited: ${Object.keys(edits).map(humanize).join(', ')}. Edits are submitted with the approval and recorded in the audit log.`
              : 'No edits. The draft will be approved as written.'}
          </p>
        </fieldset>
      )}

      <div>
        <label htmlFor={`${ids}-comment`} className="text-sm font-medium text-slate-700">
          Comment (optional)
        </label>
        <textarea
          id={`${ids}-comment`}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          disabled={disabled}
          rows={2}
          className={INPUT}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {canApprove && (
          <button
            type="button"
            onClick={() => onApprove(approveBody())}
            disabled={disabled}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          >
            {busy === 'approve' ? 'Approving…' : 'Approve'}
          </button>
        )}
        {canApprove && (
          <button
            type="button"
            onClick={() => onApproveAndExecute(approveBody())}
            disabled={disabled}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {busy === 'approve_execute' ? 'Approving and creating…' : 'Approve & create investigation'}
          </button>
        )}
        {canReject && (
          <button
            type="button"
            onClick={() => onReject(decisionBase())}
            disabled={disabled}
            className="rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-50 disabled:opacity-50"
          >
            {busy === 'reject' ? 'Rejecting…' : 'Reject'}
          </button>
        )}
      </div>
      {canApprove && (
        <p className="text-xs text-slate-500">
          “Approve &amp; create investigation” records the approval first, then requests
          execution as a separate step. If approval fails, nothing is executed.
        </p>
      )}
    </section>
  )
}
