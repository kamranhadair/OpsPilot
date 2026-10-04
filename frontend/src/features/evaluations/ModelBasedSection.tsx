import type { EvalModelBasedSection } from '../../types/api'
import { CaseCard } from './CaseList'
import { EvalStatusBadge } from './EvalStatusBadge'

/** The optional model judge; visually separated and never part of deterministic totals. */
export function ModelBasedSection({ section }: { section: EvalModelBasedSection }) {
  return (
    <section
      aria-labelledby="eval-model-heading"
      className="space-y-3 rounded-lg border-2 border-dashed border-violet-300 bg-violet-50/40 p-4"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h3 id="eval-model-heading" className="text-base font-semibold">
          Model-based (non-deterministic)
        </h3>
        <EvalStatusBadge status={section.status} />
      </div>
      <p className="text-sm text-slate-600">
        Semantic citation-support judgements from a language model. These results can vary
        between runs and are excluded from the deterministic summary above.
      </p>
      {section.reason && (
        <p className="text-sm">
          <span className="font-medium text-slate-700">Reason: </span>
          {section.reason}
        </p>
      )}
      {section.status === 'completed' && (
        <>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Model</dt>
              <dd className="font-mono text-xs">{section.model_name ?? 'Not recorded'}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Prompt version</dt>
              <dd className="font-mono text-xs">{section.prompt_version ?? 'Not recorded'}</dd>
            </div>
          </dl>
          {section.cases.length === 0 ? (
            <p className="text-sm text-slate-600">The model judge recorded no cases.</p>
          ) : (
            <ul className="space-y-3">
              {section.cases.map((result) => (
                <CaseCard key={result.case_id} result={result} />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
