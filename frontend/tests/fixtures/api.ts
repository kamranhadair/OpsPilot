/** Typed API fixtures shaped like the seeded canonical Billing scenario. */

import type {
  AnomalyDetailOut,
  AnomalyOut,
  ContributorAnalysisResponse,
  DashboardOverviewResponse,
  MetricSnapshotOut,
  TrendPoint,
} from '../../src/types/api'

const WINDOW_START = '2026-10-02T00:00:00Z'
const WINDOW_END = '2026-10-03T00:00:00Z'

export function snapshot(overrides: Partial<MetricSnapshotOut> = {}): MetricSnapshotOut {
  return {
    evidence_id: 'MTR-000101',
    metric_key: 'ticket_volume',
    display_name: 'Ticket volume',
    unit: 'count',
    direction: 'higher_is_worse',
    window_start: WINDOW_START,
    window_end: WINDOW_END,
    baseline_start: '2026-09-25T00:00:00Z',
    baseline_end: WINDOW_START,
    dimensions: {},
    value: 412,
    baseline_value: 301.5,
    change_pct: 36.65,
    change_pp: null,
    baseline_zero: false,
    baseline_empty: false,
    sample_size: 412,
    sample_sufficient: true,
    provenance: {},
    computed_at: '2026-10-03T00:05:00Z',
    ...overrides,
  }
}

export const CARDS: MetricSnapshotOut[] = [
  snapshot(),
  snapshot({
    evidence_id: 'MTR-000102',
    metric_key: 'open_backlog',
    display_name: 'Open backlog',
    value: 188,
    baseline_value: 150,
    change_pct: 25.33,
  }),
  snapshot({
    evidence_id: 'MTR-000103',
    metric_key: 'sla_breach_rate',
    display_name: 'SLA breach rate',
    unit: 'percent',
    value: 12.4,
    baseline_value: 8.1,
    change_pct: 53.09,
    change_pp: 4.3,
  }),
  snapshot({
    evidence_id: 'MTR-000104',
    metric_key: 'escalation_rate',
    display_name: 'Escalation rate',
    unit: 'percent',
    value: 6.2,
    baseline_value: null,
    change_pct: null,
    change_pp: null,
    baseline_empty: true,
    sample_sufficient: false,
    sample_size: 12,
  }),
]

export function points(values: number[], prefix = 'MTR-0002'): TrendPoint[] {
  return values.map((value, index) => ({
    evidence_id: `${prefix}${String(index).padStart(2, '0')}`,
    window_end: `2026-10-0${index + 1}T00:00:00Z`,
    value,
    baseline_value: 300,
    change_pct: null,
    sample_size: 300,
  }))
}

export function anomaly(overrides: Partial<AnomalyOut> = {}): AnomalyOut {
  return {
    evidence_id: 'ANOM-000007',
    metric_evidence_id: 'MTR-000120',
    metric_key: 'ticket_volume',
    display_name: 'Ticket volume',
    dimensions: { category: 'billing' },
    unit: 'count',
    value: 168,
    baseline_value: 80,
    severity: 'high',
    status: 'active',
    score: 110,
    score_comparison: 'relative_pct',
    detector_key: 'pct_change.v1',
    window_start: WINDOW_START,
    window_end: WINDOW_END,
    detected_at: '2026-10-03T00:06:00Z',
    explanation:
      'Ticket volume changed +110.00% against its 7-day baseline, meeting the high threshold of 50% (rule pct_change.v1). Severity: high.',
    ...overrides,
  }
}

export function overview(
  overrides: Partial<DashboardOverviewResponse> = {},
): DashboardOverviewResponse {
  return {
    window_end: WINDOW_END,
    cards: CARDS,
    missing_metric_keys: [],
    trends: [
      {
        definition: {
          key: 'ticket_volume',
          display_name: 'Ticket volume',
          description: 'Tickets created in the window.',
          unit: 'count',
          aggregation: 'count',
          cohort: 'created_in_window',
          formula: 'count(tickets)',
          direction: 'higher_is_worse',
          baseline_method: 'mean_of_daily_values',
          supported_dimensions: [],
          min_sample_size: null,
          version: 1,
        },
        points: points([298, 305, 412]),
      },
      {
        definition: {
          key: 'sla_breach_rate',
          display_name: 'SLA breach rate',
          description: 'Share of tickets that breached SLA.',
          unit: 'percent',
          aggregation: 'rate',
          cohort: 'created_in_window',
          formula: 'count(tickets where sla_breached) / count(tickets) * 100',
          direction: 'higher_is_worse',
          baseline_method: 'pooled_rate',
          supported_dimensions: [],
          min_sample_size: 20,
          version: 1,
        },
        points: points([12.4], 'MTR-0003'),
      },
    ],
    active_anomalies: [
      anomaly(),
      anomaly({
        evidence_id: 'ANOM-000008',
        metric_key: 'sla_breach_rate',
        display_name: 'SLA breach rate',
        unit: 'percent',
        value: 16.1,
        baseline_value: 8.2,
        severity: 'medium',
        score: 7.9,
        score_comparison: 'percentage_points',
      }),
    ],
    active_anomaly_total: 2,
    ...overrides,
  }
}

export function anomalyDetail(overrides: Partial<AnomalyDetailOut> = {}): AnomalyDetailOut {
  return {
    ...anomaly(),
    threshold: {
      schema_version: 1,
      detector_key: 'pct_change.v1',
      metric_key: 'ticket_volume',
      comparison: 'relative_pct',
      direction: 'higher_is_worse',
      observed: 110,
      medium_threshold: 25,
      high_threshold: 50,
      triggered_tier: 'high',
      guards: [{ name: 'min_current_sample', required: 20, actual: 168, passed: true }],
      critical: null,
      z_score: {
        available: false,
        value: null,
        mean: null,
        stdev: null,
        sample_count: 7,
        unavailable_reason: 'insufficient_history',
      },
    },
    snapshot: snapshot({
      evidence_id: 'MTR-000120',
      dimensions: { category: 'billing' },
      value: 168,
      baseline_value: 80,
      change_pct: 110,
    }),
    ...overrides,
  }
}

export function contributors(): ContributorAnalysisResponse {
  return {
    anomaly_evidence_id: 'ANOM-000007',
    metric_evidence_id: 'MTR-000120',
    metric_key: 'ticket_volume',
    display_name: 'Ticket volume',
    window_start: WINDOW_START,
    window_end: WINDOW_END,
    status: 'reused',
    groups: [
      {
        family_key: 'region',
        dimensions: ['region'],
        method: 'count_delta',
        formula: 'delta = current - baseline',
        positive_delta_total: 90,
        contributors: [
          {
            evidence_id: 'SEG-000020',
            rank: 1,
            segment: { region: 'emea' },
            label: 'EMEA',
            current_value: 120,
            baseline_value: 40,
            delta_value: 80,
            contribution_pct: 88.9,
            flags: [],
            statement:
              'EMEA accounts for 88.9% of the observed positive change in Ticket volume relative to the 7-day baseline.',
            provenance: {},
          },
        ],
        other_contribution_pct: 11.1,
        suppressed_contribution_pct: 0,
      },
      {
        family_key: 'region+customer_tier',
        dimensions: ['region', 'customer_tier'],
        method: 'count_delta',
        formula: 'delta = current - baseline',
        positive_delta_total: 90,
        contributors: [
          {
            evidence_id: 'SEG-000031',
            rank: 1,
            segment: { region: 'emea', customer_tier: 'enterprise' },
            label: 'EMEA / Enterprise',
            current_value: 82,
            baseline_value: 12.43,
            delta_value: 69.57,
            contribution_pct: 77.3,
            flags: [],
            statement:
              'EMEA / Enterprise accounts for 77.3% of the observed positive change in Ticket volume relative to the 7-day baseline.',
            provenance: {},
          },
          {
            evidence_id: 'SEG-000032',
            rank: 2,
            segment: { region: 'na', customer_tier: 'growth' },
            label: 'NA / Growth',
            current_value: 30,
            baseline_value: 22,
            delta_value: 8,
            contribution_pct: 8.9,
            flags: ['new_segment'],
            statement:
              'NA / Growth accounts for 8.9% of the observed positive change in Ticket volume relative to the 7-day baseline.',
            provenance: {},
          },
        ],
        other_contribution_pct: 13.8,
        suppressed_contribution_pct: 0,
      },
    ],
    unranked_families: [],
  }
}
