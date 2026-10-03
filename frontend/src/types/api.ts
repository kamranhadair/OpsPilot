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
