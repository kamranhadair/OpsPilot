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

// --- metrics (backend/app/schemas/metrics.py) ---------------------------------------

export type MetricUnit = 'count' | 'minutes' | 'percent'
export type Direction = 'higher_is_worse' | 'higher_is_better'

/**
 * Provenance is carried through untouched; it is rendered by the provenance
 * drawer (Spec 10), not by the dashboard.
 */
export type Provenance = Record<string, unknown>

export interface MetricDefinitionOut {
  key: string
  display_name: string
  description: string
  unit: MetricUnit
  aggregation: 'count' | 'point_in_time_count' | 'mean' | 'rate'
  cohort: 'created_in_window' | 'resolved_in_window' | 'open_at_window_end'
  formula: string
  direction: Direction
  baseline_method: 'mean_of_daily_values' | 'pooled_rate'
  supported_dimensions: string[]
  min_sample_size: number | null
  version: number
}

export interface MetricSnapshotOut {
  evidence_id: string
  metric_key: string
  display_name: string
  unit: MetricUnit
  direction: Direction
  window_start: string
  window_end: string
  baseline_start: string | null
  baseline_end: string | null
  dimensions: Record<string, string>
  value: number
  baseline_value: number | null
  /** Null when the baseline is zero or empty. */
  change_pct: number | null
  /** Percentage-point difference; rate metrics only. */
  change_pp: number | null
  baseline_zero: boolean
  baseline_empty: boolean
  sample_size: number
  sample_sufficient: boolean
  provenance: Provenance
  computed_at: string
}

// --- anomalies (backend/app/schemas/anomalies.py) -----------------------------------

export type AnomalySeverity = 'low' | 'medium' | 'high' | 'critical'
export type AnomalyStatus = 'active' | 'acknowledged' | 'resolved'
export type Comparison = 'relative_pct' | 'percentage_points'

export interface AnomalyOut {
  evidence_id: string
  metric_evidence_id: string
  metric_key: string
  display_name: string
  dimensions: Record<string, string>
  unit: MetricUnit
  /** Current-window value of the triggering snapshot. */
  value: number
  baseline_value: number | null
  severity: AnomalySeverity
  status: AnomalyStatus
  /** The triggering change, in the unit named by `score_comparison`. */
  score: number | null
  score_comparison: Comparison
  detector_key: string
  window_start: string
  window_end: string
  detected_at: string
  /** Deterministic, template-built; never model-written. */
  explanation: string
}

export interface GuardResult {
  name: string
  required: number
  actual: number
  passed: boolean
}

export interface CriticalResult {
  description: string
  min_current_value: number
  current_value: number
  met: boolean
}

export interface ZScoreResult {
  available: boolean
  value: number | null
  mean: number | null
  stdev: number | null
  sample_count: number
  unavailable_reason: 'insufficient_history' | 'zero_stdev' | null
}

export interface ThresholdDetails {
  schema_version: 1
  detector_key: string
  metric_key: string
  comparison: Comparison
  direction: Direction
  observed: number
  medium_threshold: number
  high_threshold: number
  triggered_tier: 'medium' | 'high'
  guards: GuardResult[]
  critical: CriticalResult | null
  z_score: ZScoreResult
}

export interface AnomalyDetailOut extends AnomalyOut {
  threshold: ThresholdDetails
  snapshot: MetricSnapshotOut
}

export interface AnomalyListResponse {
  items: AnomalyOut[]
  total: number
  limit: number
  offset: number
}

export interface AnomalyListParams {
  severity?: AnomalySeverity
  status?: AnomalyStatus
  limit?: number
  offset?: number
}

// --- contributors (backend/app/schemas/contributors.py) -----------------------------

export type ContributorMethod = 'count_delta' | 'rate_excess'
export type ContributorFlag = 'new_segment' | 'baseline_rate_from_parent_slice'

export interface ContributorOut {
  evidence_id: string
  rank: number
  segment: Record<string, string>
  label: string
  current_value: number
  baseline_value: number
  delta_value: number
  /** Share of the family's positive change, 0-100. */
  contribution_pct: number
  flags: ContributorFlag[]
  statement: string
  provenance: Provenance
}

export interface ContributorGroupOut {
  family_key: string
  dimensions: string[]
  method: ContributorMethod
  formula: string
  positive_delta_total: number
  contributors: ContributorOut[]
  other_contribution_pct: number
  suppressed_contribution_pct: number
}

export interface UnrankedFamilyOut {
  family_key: string
  status: 'ranked' | 'no_positive_contributors' | 'skipped_fixed_dimension'
}

export interface ContributorAnalysisResponse {
  anomaly_evidence_id: string
  metric_evidence_id: string
  metric_key: string
  display_name: string
  window_start: string
  window_end: string
  status: 'computed' | 'reused'
  groups: ContributorGroupOut[]
  unranked_families: UnrankedFamilyOut[]
}

// --- dashboard (backend/app/schemas/dashboard.py) -----------------------------------

export interface TrendPoint {
  evidence_id: string
  window_end: string
  value: number
  baseline_value: number | null
  change_pct: number | null
  sample_size: number
}

export interface DashboardTrend {
  definition: MetricDefinitionOut
  points: TrendPoint[]
}

export interface DashboardOverviewResponse {
  window_end: string | null
  cards: MetricSnapshotOut[]
  missing_metric_keys: string[]
  trends: DashboardTrend[]
  active_anomalies: AnomalyOut[]
  active_anomaly_total: number
}

// --- briefs (backend/app/schemas/briefs.py) -------------------------------------------

export type BriefStatus = 'draft' | 'valid' | 'invalid'
export type ClaimType = 'observation' | 'inference'
export type ClaimValidationStatus = 'pending' | 'valid' | 'invalid'

export type ValidationIssueCode =
  | 'EVIDENCE_MISSING'
  | 'EVIDENCE_NOT_IN_BUNDLE'
  | 'EVIDENCE_UNRESOLVED'
  | 'EVIDENCE_WINDOW_MISMATCH'
  | 'CAUSAL_LANGUAGE_FOR_EVENT'
  | 'CAUSAL_LANGUAGE_IN_NARRATIVE'
  | 'BRIEF_HAS_NO_CLAIMS'

export interface ValidationIssue {
  code: ValidationIssueCode
  message: string
  evidence_id?: string | null
  phrase?: string | null
  claim_ordinal?: number | null
  field?: 'headline' | 'summary' | null
}

export interface BriefClaimOut {
  ordinal: number
  claim_type: ClaimType
  text: string
  evidence_ids: string[]
  validation_status: ClaimValidationStatus
  validation_errors: ValidationIssue[]
}

export interface BriefOut {
  id: number
  analysis_window_start: string
  analysis_window_end: string
  headline: string
  summary: string
  status: BriefStatus
  model_name: string
  validation_errors: ValidationIssue[]
  created_at: string
  claims: BriefClaimOut[]
}

// --- evidence resolver (backend/app/schemas/evidence.py) ------------------------------

export type EvidenceType = 'MTR' | 'ANOM' | 'SEG' | 'EVT'
export type EvidenceClass = 'observed_fact' | 'contextual_event'
export type EvidenceValueUnit = MetricUnit | 'percentage_points'

export interface EvidenceWindow {
  start: string
  end: string
}

export interface EvidenceValue {
  key: string
  label: string
  value: number | string | null
  unit: EvidenceValueUnit | null
  note: string | null
}

export interface EvidenceMethod {
  kind: 'metric_calculation' | 'anomaly_detector' | 'contribution' | 'timeline_event'
  name: string
  version: string | null
  formula: string | null
  description: string | null
}

export interface EventDetailProvenance {
  evidence_type: 'EVT'
  source: 'incident_timeline'
  event_type: string
  occurred_at: string
  details: Record<string, string>
}

/** Typed per evidence type by the backend; rendered verbatim, never re-derived. */
export type EvidenceDetailProvenance =
  | { evidence_type: 'MTR'; computed_at: string; metric: Provenance }
  | { evidence_type: 'ANOM'; detected_at: string; threshold: Provenance }
  | { evidence_type: 'SEG'; statement: string; contribution: Provenance }
  | EventDetailProvenance

export interface EvidenceDetailOut {
  evidence_id: string
  evidence_type: EvidenceType
  evidence_class: EvidenceClass
  label: string
  window: EvidenceWindow | null
  baseline_window: EvidenceWindow | null
  dimensions: Record<string, string>
  sample_size: number | null
  sample_sufficient: boolean | null
  values: EvidenceValue[]
  method: EvidenceMethod
  related_evidence_ids: string[]
  contextual_disclaimer: string | null
  provenance: EvidenceDetailProvenance
}

// --- action proposals (backend/app/schemas/actions.py) --------------------------------

export type ActionType = 'open_investigation'
export type ActionStatus =
  | 'proposed'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'executing'
  | 'succeeded'
  | 'failed'

export type ActionProposalIssueCode =
  | 'UNSUPPORTED_ACTION_TYPE'
  | 'EVIDENCE_MISSING'
  | 'EVIDENCE_NOT_IN_BRIEF'
  | 'EVIDENCE_UNRESOLVED'
  | 'ANOMALY_EVIDENCE_MISSING'
  | 'CAUSAL_LANGUAGE'
  | 'ACTION_CLAIMED_COMPLETE'

export interface ActionProposalIssue {
  code: ActionProposalIssueCode
  message: string
  evidence_id?: string | null
  phrase?: string | null
  field?: 'action_type' | 'title' | 'description' | 'rationale' | 'investigation_steps' | null
}

export interface ActionSourceBriefOut {
  id: number
  headline: string
  status: BriefStatus
  analysis_window_start: string
  analysis_window_end: string
}

export interface ActionOut {
  id: number
  action_type: ActionType
  title: string
  description: string
  rationale: string
  investigation_steps: string[]
  evidence_ids: string[]
  status: ActionStatus
  source_brief: ActionSourceBriefOut
  created_at: string
  updated_at: string
}

export interface ActionListOut {
  items: ActionOut[]
  limit: number
  offset: number
}

export interface ActionListParams {
  status?: ActionStatus
  limit?: number
  offset?: number
}

// --- human approval and execution (backend/app/schemas/actions.py, Spec 12) ----------

/** Transitions the backend would currently accept. A presentation hint only. */
export type ActionOperation = 'approve' | 'reject' | 'execute'
export type EditableActionField = 'title' | 'description' | 'investigation_steps'

/** Human edits applied at approval. Send only fields the reviewer actually changed. */
export interface ActionEdits {
  title?: string
  description?: string
  investigation_steps?: string[]
}

export interface ApproveActionRequest {
  /** Demo reviewer identity; V1 has no authentication, so this is recorded, not verified. */
  reviewer: string
  comment?: string | null
  edits?: ActionEdits | null
}

export interface RejectActionRequest {
  reviewer: string
  comment?: string | null
}

export interface ApprovalOut {
  id: number
  decision: 'approved' | 'rejected'
  reviewer: string
  comment: string | null
  edited_fields: EditableActionField[]
  decided_at: string
}

export type ExecutionStatus = 'executing' | 'succeeded' | 'failed'

export interface ExecutionOut {
  id: number
  status: ExecutionStatus
  adapter_key: string
  /** Mock investigation reference, e.g. `INV-0001`. */
  external_ref: string | null
  error_message: string | null
  started_at: string
  finished_at: string | null
}

export type AuditActorType = 'human' | 'system' | 'ai'

export interface AuditEventOut {
  id: number
  actor_type: AuditActorType
  actor_id: string | null
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

export interface ActionDetailOut extends ActionOut {
  approval: ApprovalOut | null
  execution: ExecutionOut | null
  /** Oldest first. */
  audit_events: AuditEventOut[]
  allowed_operations: ActionOperation[]
}

/** One reason a human edit was refused (422 `ACTION_EDIT_REJECTED`). */
export interface ActionEditIssue {
  code: 'CAUSAL_LANGUAGE' | 'ACTION_CLAIMED_COMPLETE'
  message: string
  phrase: string
  field: EditableActionField
}

/**
 * Error body fields beyond `code`/`message` that some endpoints add:
 * `existing_action_id` on 409 `ACTION_ALREADY_PROPOSED`,
 * `issues` on 422 `ACTION_PROPOSAL_REJECTED` / `ACTION_EDIT_REJECTED`,
 * `current_status` on 409 `ACTION_INVALID_TRANSITION`,
 * `execution` on 502 `ACTION_EXECUTION_FAILED`.
 */
export interface ApiErrorBody extends ErrorResponse {
  existing_action_id?: number | null
  issues?: ActionProposalIssue[] | ActionEditIssue[]
  current_status?: ActionStatus | null
  execution?: ExecutionOut
  /** Spec 14: present on 503 `DATABASE_UNAVAILABLE` from `/api/system/health`. */
  health?: SystemHealthResponse
}

// ---------------------------------------------------------------------------
// Spec 13: evaluation report (mirrors backend/app/schemas/evaluations.py)
// ---------------------------------------------------------------------------

export type EvalCaseStatus = 'pass' | 'fail' | 'not_run' | 'error'
export type EvalSuiteName = 'all' | 'deterministic' | 'ai'
export type EvalOverallStatus = 'pass' | 'fail' | 'incomplete'
export type EvalSeedState = 'complete' | 'empty' | 'inconsistent' | 'unavailable'

export type EvalCategory =
  | 'metric_correctness'
  | 'anomaly_detection'
  | 'false_positive'
  | 'contributor_attribution'
  | 'citation_validity'
  | 'causal_guardrail'
  | 'action_grounding'
  | 'approval_boundary'

/** A count measured inside one case, e.g. high/critical flags among checked metrics. */
export interface EvalCaseTally {
  flagged: number
  checked: number
}

export interface EvalCaseResult {
  case_id: string
  title: string
  category: EvalCategory
  status: EvalCaseStatus
  expected: string
  observed: string | null
  /** Why the case failed, errored or did not run. */
  failure_reason: string | null
  evidence: string[]
  tally: EvalCaseTally | null
}

export interface EvalCategorySummary {
  category: EvalCategory
  total: number
  passed: number
  failed: number
  errored: number
  not_run: number
  /** passed / (passed + failed + errored); null when nothing was executed. */
  pass_rate: number | null
}

export interface EvalRatioMetric {
  key: string
  label: string
  numerator: number
  denominator: number
  /** numerator / denominator as a 0..1 fraction; null when the denominator is 0. */
  value: number | null
  description: string
}

export interface EvalCountMetric {
  key: string
  label: string
  passed: number
  failed: number
  errored: number
  not_run: number
  description: string
}

export interface EvalSeedInfo {
  expected_version: string
  case_version: string
  observed_state: EvalSeedState
  observed_version: string | null
  matches: boolean
}

export interface EvalReplayAnomaly {
  metric_key: string
  display_name: string
  filters: Record<string, string>
  severity: AnomalySeverity
  score: number | null
}

export interface EvalReplayDay {
  window_start: string
  window_end: string
  status: 'ok' | 'no_data'
  detail: string | null
  anomalies: EvalReplayAnomaly[]
  high_or_critical_count: number
}

export interface EvalReplaySummary {
  status: 'completed' | 'not_run' | 'error'
  reason: string | null
  days_requested: number
  days: EvalReplayDay[]
  note: string
}

/** Optional semantic citation-support judgement. Never part of deterministic totals. */
export interface EvalModelBasedSection {
  label: 'model_based'
  status: 'completed' | 'not_run' | 'error'
  reason: string | null
  model_name: string | null
  prompt_version: string | null
  cases: EvalCaseResult[]
}

export interface EvaluationReport {
  schema_version: 1
  run_id: string
  suite: EvalSuiteName
  generated_at: string
  overall_status: EvalOverallStatus
  /** True when any case, replay or judge errored. */
  partial_failure: boolean
  seed: EvalSeedInfo
  cases: EvalCaseResult[]
  categories: EvalCategorySummary[]
  ratios: EvalRatioMetric[]
  counts: EvalCountMetric[]
  replay: EvalReplaySummary | null
  model_based: EvalModelBasedSection
  notes: string[]
}

/** `GET /api/evaluations/latest`; 500 `EVAL_REPORT_INVALID` when the stored file is corrupt. */
export type EvaluationLatestResponse =
  | { state: 'available'; report: EvaluationReport; message: string | null }
  | { state: 'not_run'; report: null; message: string | null }

// ---------------------------------------------------------------------------
// Spec 14: system observability (mirrors backend/app/schemas/system.py)
// ---------------------------------------------------------------------------

export type SystemOverallStatus = 'ok' | 'degraded' | 'error'

/**
 * `GET /api/system/health`. 503 `DATABASE_UNAVAILABLE` carries this body under
 * `health`; 404 `SYSTEM_ENDPOINTS_DISABLED` outside demo/dev environments.
 */
export interface SystemHealthResponse {
  status: SystemOverallStatus
  service: string
  environment: string
  database: { status: 'ok' | 'error'; migration_revision: string | null }
  llm: { configured: boolean; model: string | null }
  cost_estimation: { configured: boolean }
  evaluation: { model_enabled: boolean; latest_report: 'available' | 'not_run' | 'invalid' }
  checked_at: string
}

export type TraceStatus = 'success' | 'error'

export interface LLMTraceOut {
  id: number
  operation: string
  model_name: string
  status: TraceStatus
  latency_ms: number
  input_tokens: number | null
  output_tokens: number | null
  estimated_cost_usd: number | null
  error_code: string | null
  error_message: string | null
  brief_id: number | null
  action_id: number | null
  request_id: string | null
  created_at: string
}

export interface LLMTraceListOut {
  items: LLMTraceOut[]
  total: number
  limit: number
  offset: number
}

export interface LLMTraceListParams {
  operation?: string
  status?: TraceStatus
  since?: string
  until?: string
  limit?: number
  offset?: number
}

export type SummaryPeriod = '24h' | '7d' | '30d' | 'all'

export interface LatencySummary {
  avg: number
  p50: number
  p95: number
  max: number
}

export interface OperationSummary {
  operation: string
  total_calls: number
  error_count: number
  error_rate: number | null
  avg_latency_ms: number | null
  input_tokens_total: number
  output_tokens_total: number
  estimated_cost_usd: number | null
}

export interface LLMSummary {
  total_calls: number
  success_count: number
  error_count: number
  /** Fraction 0..1; null when there were no calls. */
  error_rate: number | null
  /** Null when there were no calls. */
  latency_ms: LatencySummary | null
  input_tokens_total: number
  output_tokens_total: number
  calls_missing_usage: number
  cost_configured: boolean
  /** Null when no trace in the period has a cost. */
  estimated_cost_usd: number | null
  calls_missing_cost: number
  by_operation: OperationSummary[]
}

export interface ExecutionFailureOut {
  execution_id: number
  action_id: number
  adapter_key: string
  error_code: string | null
  error_message: string | null
  started_at: string
  finished_at: string | null
}

export interface ExecutionSummary {
  total: number
  succeeded: number
  failed: number
  recent_failures: ExecutionFailureOut[]
}

export interface SystemSummaryOut {
  period: SummaryPeriod
  window_start: string | null
  window_end: string
  llm: LLMSummary
  executions: ExecutionSummary
}
