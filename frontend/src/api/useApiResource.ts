import { useCallback, useEffect, useState } from 'react'

import { ApiError, NETWORK_ERROR_CODE } from './client'

export type ResourceState<T> =
  | { kind: 'loading' }
  | { kind: 'success'; data: T }
  | { kind: 'error'; error: ApiError }

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError('Unexpected client error.', 0, NETWORK_ERROR_CODE, {
    cause: error,
  })
}

/**
 * Loads one API resource and tracks loading/error/success.
 * `load` must be memoised by the caller; a new `load` triggers a reload.
 * Responses from a superseded load are ignored.
 */
export function useApiResource<T>(load: () => Promise<T>): {
  state: ResourceState<T>
  reload: () => void
} {
  const [state, setState] = useState<ResourceState<T>>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    setState({ kind: 'loading' })
    load().then(
      (data) => {
        if (current) setState({ kind: 'success', data })
      },
      (error: unknown) => {
        if (current) setState({ kind: 'error', error: toApiError(error) })
      },
    )
    return () => {
      current = false
    }
  }, [load, attempt])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  return { state, reload }
}
