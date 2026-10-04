import { useCallback, useState } from 'react'

import { EvidenceId } from '../../components/EvidenceId'
import { formatUtc, humanize } from '../../lib/format'
import type { BriefClaimOut, BriefOut } from '../../types/api'
import { ProposeActionButton } from '../actions/ProposeActionButton'
import { ProvenanceDrawer } from '../evidence/ProvenanceDrawer'
import { BriefStatusBanner } from './BriefStatusBanner'
import { IssueList } from './IssueList'

const CLAIM_STATUS_STYLES: Record<BriefClaimOut['validation_status'], string> = {
  valid: 'bg-emerald-100 text-emerald-800',
  invalid: 'bg-red-100 text-red-800',
  pending: 'bg-slate-100 text-slate-700',
}

function Claim({ claim, onSelect }: { claim: BriefClaimOut; onSelect: (id: string) => void }) {
  return (
    <li
      className={`rounded-lg border p-4 ${
        claim.validation_status === 'invalid' ? 'border-red-200' : 'border-slate-200'
      } bg-white`}
    >
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">
          {humanize(claim.claim_type)}
        </span>
        <span
          className={`rounded px-1.5 py-0.5 font-medium ${CLAIM_STATUS_STYLES[claim.validation_status]}`}
        >
          {humanize(claim.validation_status)}
        </span>
      </div>
      <p className="mt-2 text-sm text-slate-900">{claim.text}</p>
      <p className="mt-2 flex flex-wrap items-center gap-1 text-xs text-slate-500">
        Evidence:
        {claim.evidence_ids.map((id, index) => (
          <EvidenceId key={`${id}-${index}`} id={id} onSelect={onSelect} />
        ))}
      </p>
      <div className="text-sm">
        <IssueList issues={claim.validation_errors} />
      </div>
    </li>
  )
}

export function BriefView({ brief }: { brief: BriefOut }) {
  const [selected, setSelected] = useState<string | null>(null)
  const close = useCallback(() => setSelected(null), [])

  return (
    <article aria-labelledby="brief-headline" className="space-y-4">
      <header>
        <p className="text-xs text-slate-500">
          Brief #{brief.id} · {formatUtc(brief.analysis_window_start)} →{' '}
          {formatUtc(brief.analysis_window_end)} · {brief.model_name}
        </p>
        <h2 id="brief-headline" className="mt-1 text-xl font-semibold">
          {brief.headline}
        </h2>
      </header>
      <BriefStatusBanner status={brief.status} issues={brief.validation_errors} />
      <p className="text-sm text-slate-700">{brief.summary}</p>
      <section aria-label="Claims">
        <h3 className="mb-2 font-medium text-slate-800">Claims</h3>
        {brief.claims.length === 0 ? (
          <p className="text-sm text-slate-500">This brief contains no claims.</p>
        ) : (
          <ol className="space-y-3">
            {brief.claims.map((claim) => (
              <Claim key={claim.ordinal} claim={claim} onSelect={setSelected} />
            ))}
          </ol>
        )}
      </section>
      {brief.status === 'valid' && <ProposeActionButton briefId={brief.id} />}
      {selected && <ProvenanceDrawer evidenceId={selected} onClose={close} />}
    </article>
  )
}
