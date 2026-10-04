import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getBrief } from '../../api/client'
import { useApiResource } from '../../api/useApiResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../../components/StatePanels'
import { BriefView } from './BriefView'

function BriefLoader({ briefId }: { briefId: number }) {
  const load = useCallback(() => getBrief(briefId), [briefId])
  const { state, reload } = useApiResource(load)

  if (state.kind === 'loading') return <LoadingPanel label="Loading brief…" />
  if (state.kind === 'error') {
    if (state.error.code === 'BRIEF_NOT_FOUND') {
      return <EmptyPanel title="Brief not found">{state.error.message}</EmptyPanel>
    }
    return <ErrorPanel title="Could not load the brief" error={state.error} onRetry={reload} />
  }
  return <BriefView brief={state.data} />
}

/** `/briefs/:briefId`: any brief, valid or not, with its validation state. */
export function BriefPage() {
  const { briefId } = useParams()
  const id = Number(briefId)
  return (
    <div className="space-y-4">
      <Link to="/briefs" className="text-sm text-sky-700 underline">
        Latest validated brief
      </Link>
      {Number.isInteger(id) && id > 0 ? (
        <BriefLoader briefId={id} />
      ) : (
        <EmptyPanel title="Brief not found">{`"${briefId ?? ''}" is not a brief ID.`}</EmptyPanel>
      )}
    </div>
  )
}
