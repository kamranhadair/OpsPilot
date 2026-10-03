/**
 * The single HTTP boundary for the frontend.
 * Feature code must call these helpers rather than using `fetch` directly.
 */

import type { ErrorResponse, HealthResponse } from '../types/api'

const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/** Error carrying the HTTP status and the backend's machine-readable code. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(
    message: string,
    status: number,
    code: string,
    options?: { cause?: unknown },
  ) {
    super(message, options)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/** Raised when the backend could not be reached at all. */
export const NETWORK_ERROR_CODE = 'NETWORK_UNREACHABLE'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: 'application/json' },
      ...init,
    })
  } catch (cause) {
    throw new ApiError('Could not reach the OpsPilot API.', 0, NETWORK_ERROR_CODE, {
      cause,
    })
  }

  if (!response.ok) {
    let code = `HTTP_${response.status}`
    let message = `Request to ${path} failed with status ${response.status}.`

    try {
      const body = (await response.json()) as Partial<ErrorResponse>
      if (body.code) code = body.code
      if (body.message) message = body.message
    } catch {
      // Non-JSON error body: keep the status-derived defaults.
    }

    throw new ApiError(message, response.status, code)
  }

  return (await response.json()) as T
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/health')
}
