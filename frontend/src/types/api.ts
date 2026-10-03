/**
 * TypeScript mirrors of the backend Pydantic contracts.
 * Keep these in sync with `backend/app/schemas/`.
 */

export type ComponentStatus = 'ok' | 'error'

export interface HealthResponse {
  status: ComponentStatus
  service: string
  database: ComponentStatus
}

/** Stable machine-readable error body returned by the API. */
export interface ErrorResponse {
  code: string
  message: string
}
