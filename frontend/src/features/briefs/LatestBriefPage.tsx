import { useCallback } from 'react'

import { getLatestBrief } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import { BriefView } from './BriefView'

/** `/briefs`: only the newest *validated* brief; invalid briefs never appear here. */
export function LatestBriefPage() {
  const load = useCallback(() => getLatestBrief(), [])
  const { state, reload } = useApiResource(load)

  return (
    <section aria-labelledby="briefs-heading" className="space-y-4">
      <h2 id="briefs-heading" className="text-lg font-semibold">
        Operations brief
      </h2>
      {state.kind === 'loading' && <LoadingPanel label="Loading latest validated brief…" />}
      {state.kind === 'error' &&
        (state.error.code === 'NO_VALIDATED_BRIEF' ? (
          <EmptyPanel title="No validated brief yet">
            Briefs appear here only after every claim passes evidence validation.
          </EmptyPanel>
        ) : (
          <ErrorPanel title="Could not load the brief" error={state.error} onRetry={reload} />
        ))}
      {state.kind === 'success' && <BriefView brief={state.data} />}
    </section>
  )
}
