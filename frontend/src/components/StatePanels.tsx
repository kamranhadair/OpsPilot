import type { ReactNode } from 'react'

import type { ApiError } from '../api/client'

export function LoadingPanel({ label }: { label: string }) {
  return (
    <p role="status" className="py-6 text-sm text-slate-500">
      {label}
    </p>
  )
}

export function ErrorPanel({
  title,
  error,
  onRetry,
}: {
  title: string
  error: ApiError
  onRetry?: () => void
}) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm"
    >
      <p className="font-medium text-red-800">{title}</p>
      <p className="mt-1 text-slate-700">{error.message}</p>
      <p className="mt-1 font-mono text-xs text-slate-500">{error.code}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md border border-slate-300 bg-white px-3 py-1 text-sm text-slate-700 hover:bg-slate-50"
        >
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyPanel({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-sm">
      <p className="font-medium text-slate-800">{title}</p>
      {children && <div className="mt-1 text-slate-600">{children}</div>}
    </div>
  )
}
