import { useCallback, useEffect, useState } from 'react'

import { ApiError, getHealth } from '../../api/client'
import type { HealthResponse } from '../../types/api'

type HealthState =
  | { kind: 'loading' }
  | { kind: 'success'; data: HealthResponse }
  | { kind: 'error'; message: string; code: string }
  | { kind: 'unknown' }

export function HealthPanel() {
  const [state, setState] = useState<HealthState>({ kind: 'loading' })

  const load = useCallback(async () => {
    setState({ kind: 'loading' })
    try {
      const data = await getHealth()
      setState({ kind: 'success', data })
    } catch (error) {
      if (error instanceof ApiError) {
        setState({ kind: 'error', message: error.message, code: error.code })
      } else {
        setState({
          kind: 'unknown',
        })
      }
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <section
      aria-labelledby="backend-health-heading"
      className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="flex items-center justify-between gap-4">
        <h2
          id="backend-health-heading"
          className="text-sm font-semibold tracking-wide text-slate-700 uppercase"
        >
          Backend health
        </h2>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50"
        >
          Re-check
        </button>
      </div>

      <div className="mt-4">
        {state.kind === 'loading' && (
          <p role="status" className="text-sm text-slate-500">
            Checking backend health…
          </p>
        )}

        {state.kind === 'success' && (
          <dl className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <dt className="text-slate-500">Service</dt>
              <dd className="font-medium text-slate-900">
                {state.data.service}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">API</dt>
              <dd className="font-medium text-emerald-700">
                {state.data.status}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Database</dt>
              <dd
                className={
                  state.data.database === 'ok'
                    ? 'font-medium text-emerald-700'
                    : 'font-medium text-red-700'
                }
              >
                {state.data.database}
              </dd>
            </div>
          </dl>
        )}

        {state.kind === 'error' && (
          <div role="alert" className="text-sm">
            <p className="font-medium text-red-700">Backend unavailable</p>
            <p className="mt-1 text-slate-600">{state.message}</p>
            <p className="mt-1 font-mono text-xs text-slate-500">
              {state.code}
            </p>
          </div>
        )}

        {state.kind === 'unknown' && (
          <p role="alert" className="text-sm text-slate-600">
            Health state unknown. The check did not return a recognised result.
          </p>
        )}
      </div>
    </section>
  )
}

