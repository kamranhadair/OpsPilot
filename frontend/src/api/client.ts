/**
 * The single HTTP boundary for the frontend.
 * Feature code must call these helpers rather than using `fetch` directly.
 */

import type {
  ActionDetailOut,
  ActionListOut,
  ActionListParams,
  ActionOut,
  AnomalyDetailOut,
  AnomalyListParams,
  AnomalyListResponse,
  BriefOut,
  ApiErrorBody,
  ApproveActionRequest,
  AnalysisRunResponse,
  ContributorAnalysisResponse,
  DashboardOverviewResponse,
  DemoStatusResponse,
  EvaluationLatestResponse,
  EvidenceDetailOut,
  HealthResponse,
  LLMTraceListOut,
  LLMTraceListParams,
  RejectActionRequest,
  SummaryPeriod,
  SystemHealthResponse,
  SystemSummaryOut,
} from '../types/api'

const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/** Error carrying the HTTP status and the backend's machine-readable code. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  /** The parsed typed error body, when the backend sent one. */
  readonly body: ApiErrorBody | null

  constructor(
    message: string,
    status: number,
    code: string,
    options?: { cause?: unknown; body?: ApiErrorBody | null },
  ) {
    super(message, options)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.body = options?.body ?? null
  }
}

/** Raised when the backend could not be reached at all. */
export const NETWORK_ERROR_CODE = 'NETWORK_UNREACHABLE'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
    })
  } catch (cause) {
    throw new ApiError('Could not reach the OpsPilot API.', 0, NETWORK_ERROR_CODE, {
      cause,
    })
  }

  if (!response.ok) {
    let code = `HTTP_${response.status}`
    let message = `Request to ${path} failed with status ${response.status}.`
    let body: ApiErrorBody | null = null

    try {
      const parsed = (await response.json()) as Partial<ApiErrorBody>
      if (parsed.code) code = parsed.code
      if (parsed.message) message = parsed.message
      if (parsed.code && parsed.message) body = parsed as ApiErrorBody
    } catch {
      // Non-JSON error body: keep the status-derived defaults.
    }

    throw new ApiError(message, response.status, code, { body })
  }

  return (await response.json()) as T
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/health')
}

export function getDashboardOverview(): Promise<DashboardOverviewResponse> {
  return request<DashboardOverviewResponse>('/api/dashboard/overview')
}

export function listAnomalies(
  params: AnomalyListParams = {},
): Promise<AnomalyListResponse> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value))
  }
  const qs = query.toString()
  const suffix = qs ? `?${qs}` : ''
  return request<AnomalyListResponse>(`/api/anomalies${suffix}`)
}

export function getAnomaly(evidenceId: string): Promise<AnomalyDetailOut> {
  return request<AnomalyDetailOut>(
    `/api/anomalies/${encodeURIComponent(evidenceId)}`,
  )
}

export function getContributors(
  evidenceId: string,
): Promise<ContributorAnalysisResponse> {
  return request<ContributorAnalysisResponse>(
    `/api/anomalies/${encodeURIComponent(evidenceId)}/contributors`,
  )
}

/** Idempotent: the backend reuses stored contributors on a repeat call. */
export function computeContributors(
  evidenceId: string,
): Promise<ContributorAnalysisResponse> {
  return request<ContributorAnalysisResponse>(
    `/api/anomalies/${encodeURIComponent(evidenceId)}/contributors/compute`,
    { method: 'POST' },
  )
}

export function getBrief(briefId: number): Promise<BriefOut> {
  return request<BriefOut>(`/api/briefs/${briefId}`)
}

/** The newest *validated* brief; 404 `NO_VALIDATED_BRIEF` when none exists. */
export function getLatestBrief(): Promise<BriefOut> {
  return request<BriefOut>('/api/briefs/latest')
}

export function getEvidence(evidenceId: string): Promise<EvidenceDetailOut> {
  return request<EvidenceDetailOut>(`/api/evidence/${encodeURIComponent(evidenceId)}`)
}

export function listActions(params: ActionListParams = {}): Promise<ActionListOut> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value))
  }
  const qs = query.toString()
  return request<ActionListOut>(`/api/actions${qs ? `?${qs}` : ''}`)
}

/** One action with its human decision, execution outcome, audit trail and allowed operations. */
export function getAction(actionId: number): Promise<ActionDetailOut> {
  return request<ActionDetailOut>(`/api/actions/${actionId}`)
}

/**
 * Ask the backend to draft one investigation from a validated brief. The result is
 * always `pending_approval`; 409 `ACTION_ALREADY_PROPOSED` carries `existing_action_id`.
 */
export function proposeAction(briefId: number): Promise<ActionOut> {
  return request<ActionOut>(`/api/briefs/${briefId}/actions/propose`, { method: 'POST' })
}

function postJson<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    ...(body === undefined
      ? {}
      : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  })
}

/** Record a human approval (with optional edits). The backend enforces the state machine. */
export function approveAction(
  actionId: number,
  body: ApproveActionRequest,
): Promise<ActionDetailOut> {
  return postJson<ActionDetailOut>(`/api/actions/${actionId}/approve`, body)
}

/** Record a human rejection. */
export function rejectAction(
  actionId: number,
  body: RejectActionRequest,
): Promise<ActionDetailOut> {
  return postJson<ActionDetailOut>(`/api/actions/${actionId}/reject`, body)
}

/**
 * Execute an approved action through the mock investigation adapter. A separate backend
 * transition from approval; replaying a succeeded action returns the same execution.
 */
export function executeAction(actionId: number): Promise<ActionDetailOut> {
  return postJson<ActionDetailOut>(`/api/actions/${actionId}/execute`)
}

/**
 * The newest stored evaluation report. `state: "not_run"` when none exists;
 * 500 `EVAL_REPORT_INVALID` when the stored report is corrupt.
 */
export function getLatestEvaluation(): Promise<EvaluationLatestResponse> {
  return request<EvaluationLatestResponse>('/api/evaluations/latest')
}

/**
 * Detailed demo/dev readiness. 503 `DATABASE_UNAVAILABLE` (body carries `health`);
 * 404 `SYSTEM_ENDPOINTS_DISABLED` outside demo/development environments.
 */
export function getSystemHealth(): Promise<SystemHealthResponse> {
  return request<SystemHealthResponse>('/api/system/health')
}

/** Paginated, safe LLM trace metadata, newest first (ordering is the backend's). */
export function listLlmTraces(params: LLMTraceListParams = {}): Promise<LLMTraceListOut> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value))
  }
  const qs = query.toString()
  return request<LLMTraceListOut>(`/api/system/llm-traces${qs ? `?${qs}` : ''}`)
}

/** Backend-aggregated LLM call and action execution summary for a period. */
export function getSystemSummary(period: SummaryPeriod = '7d'): Promise<SystemSummaryOut> {
  return request<SystemSummaryOut>(
    `/api/system/summary?period=${encodeURIComponent(period)}`,
  )
}

/** Demo readiness. 404 `DEMO_DISABLED` outside demo/development environments. */
export function getDemoStatus(): Promise<DemoStatusResponse> {
  return request<DemoStatusResponse>('/api/demo/status')
}

/**
 * Runs metrics -> anomalies -> contributors -> evidence -> brief for the final window.
 * Never proposes or executes an action. 409 `NO_SOURCE_DATA` when the demo is not seeded.
 */
export function runDemoAnalysis(): Promise<AnalysisRunResponse> {
  return postJson<AnalysisRunResponse>('/api/demo/analysis/run')
}
