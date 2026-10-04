/** Typed API fixtures shaped like the seeded canonical Billing scenario. */

import type {
  ActionDetailOut,
  ActionOut,
  ApprovalOut,
  AuditEventOut,
  ExecutionOut,
  AnomalyDetailOut,
  AnomalyOut,
  BriefOut,
  ContributorAnalysisResponse,
  DashboardOverviewResponse,
  EvidenceDetailOut,
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

export function brief(overrides: Partial<BriefOut> = {}): BriefOut {
  return {
    id: 12,
    analysis_window_start: WINDOW_START,
    analysis_window_end: WINDOW_END,
    headline: 'Billing ticket volume is elevated',
    summary: 'Billing volume rose against the seven-day baseline.',
    status: 'valid',
    model_name: 'test-model',
    validation_errors: [],
    created_at: WINDOW_END,
    claims: [
      {
        ordinal: 0,
        claim_type: 'observation',
        text: 'Billing ticket volume rose 36.7% against baseline.',
        evidence_ids: ['MTR-000101', 'ANOM-000007'],
        validation_status: 'valid',
        validation_errors: [],
      },
      {
        ordinal: 1,
        claim_type: 'inference',
        text: 'A billing deploy coincided with the spike and warrants investigation.',
        evidence_ids: ['EVT-000004'],
        validation_status: 'valid',
        validation_errors: [],
      },
    ],
    ...overrides,
  }
}

export function invalidBrief(): BriefOut {
  const issue = {
    code: 'EVIDENCE_NOT_IN_BUNDLE' as const,
    message: 'MTR-999999 is not in the Evidence Bundle allow-list.',
    evidence_id: 'MTR-999999',
  }
  const base = brief()
  return {
    ...base,
    id: 13,
    status: 'invalid',
    validation_errors: [{ ...issue, claim_ordinal: 1 }],
    claims: [
      base.claims[0]!,
      {
        ordinal: 1,
        claim_type: 'observation',
        text: 'Backlog doubled.',
        evidence_ids: ['MTR-999999'],
        validation_status: 'invalid',
        validation_errors: [issue],
      },
    ],
  }
}

export function metricEvidence(): EvidenceDetailOut {
  return {
    evidence_id: 'MTR-000101',
    evidence_type: 'MTR',
    evidence_class: 'observed_fact',
    label: 'Ticket volume (category=billing)',
    window: { start: WINDOW_START, end: WINDOW_END },
    baseline_window: { start: '2026-09-25T00:00:00Z', end: WINDOW_START },
    dimensions: { category: 'billing' },
    sample_size: 412,
    sample_sufficient: true,
    values: [
      { key: 'value', label: 'Current value', value: 412, unit: 'count', note: null },
      { key: 'baseline_value', label: 'Baseline value', value: 301.5, unit: 'count', note: null },
      {
        key: 'change_pct',
        label: 'Change vs baseline',
        value: null,
        unit: 'percent',
        note: 'Baseline is zero; percentage change is undefined.',
      },
    ],
    method: {
      kind: 'metric_calculation',
      name: 'ticket_volume',
      version: '1',
      formula: 'count(tickets created in window)',
      description: null,
    },
    related_evidence_ids: [],
    contextual_disclaimer: null,
    provenance: {
      evidence_type: 'MTR',
      computed_at: WINDOW_END,
      metric: { schema_version: 1, source: { table: 'tickets' } },
    },
  }
}

export function eventEvidence(): EvidenceDetailOut {
  return {
    evidence_id: 'EVT-000004',
    evidence_type: 'EVT',
    evidence_class: 'contextual_event',
    label: 'Billing API 2.4 deployment',
    window: null,
    baseline_window: null,
    dimensions: { product: 'billing_api' },
    sample_size: null,
    sample_sufficient: null,
    values: [
      { key: 'event_type', label: 'Event type', value: 'deployment', unit: null, note: null },
    ],
    method: {
      kind: 'timeline_event',
      name: 'incident_timeline',
      version: null,
      formula: null,
      description: null,
    },
    related_evidence_ids: [],
    contextual_disclaimer:
      'Timeline context only. It occurred near the analysis window; no link to the metric change has been established.',
    provenance: {
      evidence_type: 'EVT',
      source: 'incident_timeline',
      event_type: 'deployment',
      occurred_at: '2026-10-01T18:00:00Z',
      details: { version: '2.4.0' },
    },
  }
}

export function action(overrides: Partial<ActionOut> = {}): ActionOut {
  return {
    id: 5,
    action_type: 'open_investigation',
    title: 'Investigate EMEA Billing ticket spike',
    description: 'Review billing ticket volume against the seven-day baseline.',
    rationale: 'The anomaly and a coinciding deploy warrant investigation.',
    investigation_steps: ['Review the top contributing segment', 'Check the billing deploy'],
    evidence_ids: ['ANOM-000007', 'MTR-000101', 'EVT-000004'],
    status: 'pending_approval',
    source_brief: {
      id: 12,
      headline: 'Billing ticket volume is elevated',
      status: 'valid',
      analysis_window_start: WINDOW_START,
      analysis_window_end: WINDOW_END,
    },
    created_at: WINDOW_END,
    updated_at: WINDOW_END,
    ...overrides,
  }
}

const PROPOSED_AT = '2026-10-03T00:00:00Z'
const DECIDED_AT = '2026-10-03T09:15:00Z'
const EXECUTED_AT = '2026-10-03T09:16:00Z'

function auditEvent(
  id: number,
  event_type: string,
  actor_type: AuditEventOut['actor_type'],
  actor_id: string | null,
  created_at: string,
  payload: Record<string, unknown> = {},
): AuditEventOut {
  return { id, actor_type, actor_id, event_type, payload, created_at }
}

const PROPOSED_EVENTS: AuditEventOut[] = [
  auditEvent(1, 'action.proposed', 'ai', 'action_proposer', PROPOSED_AT),
  auditEvent(2, 'action.status_changed', 'system', null, PROPOSED_AT, {
    from: 'proposed',
    to: 'pending_approval',
  }),
]

export function approval(overrides: Partial<ApprovalOut> = {}): ApprovalOut {
  return {
    id: 3,
    decision: 'approved',
    reviewer: 'Operations Manager',
    comment: 'Worth a look before the weekly review.',
    edited_fields: ['title'],
    decided_at: DECIDED_AT,
    ...overrides,
  }
}

export function execution(overrides: Partial<ExecutionOut> = {}): ExecutionOut {
  return {
    id: 4,
    status: 'succeeded',
    adapter_key: 'mock_investigation',
    external_ref: 'INV-0001',
    error_message: null,
    started_at: EXECUTED_AT,
    finished_at: EXECUTED_AT,
    ...overrides,
  }
}

/** A drafted investigation awaiting a human decision. */
export function actionDetail(overrides: Partial<ActionDetailOut> = {}): ActionDetailOut {
  return {
    ...action(),
    approval: null,
    execution: null,
    audit_events: PROPOSED_EVENTS,
    allowed_operations: ['approve', 'reject'],
    ...overrides,
  }
}

const APPROVED_EVENTS: AuditEventOut[] = [
  ...PROPOSED_EVENTS,
  auditEvent(3, 'action.edited', 'human', 'Operations Manager', DECIDED_AT, {
    fields: ['title'],
  }),
  auditEvent(4, 'action.approved', 'human', 'Operations Manager', DECIDED_AT),
]

export function approvedActionDetail(overrides: Partial<ActionDetailOut> = {}): ActionDetailOut {
  return actionDetail({
    title: 'Investigate EMEA Billing ticket spike (edited)',
    status: 'approved',
    approval: approval(),
    audit_events: APPROVED_EVENTS,
    allowed_operations: ['execute'],
    ...overrides,
  })
}

export function succeededActionDetail(overrides: Partial<ActionDetailOut> = {}): ActionDetailOut {
  return approvedActionDetail({
    status: 'succeeded',
    execution: execution(),
    audit_events: [
      ...APPROVED_EVENTS,
      auditEvent(5, 'action.execution_started', 'system', 'mock_investigation', EXECUTED_AT),
      auditEvent(6, 'action.execution_succeeded', 'system', 'mock_investigation', EXECUTED_AT, {
        external_ref: 'INV-0001',
      }),
    ],
    allowed_operations: [],
    ...overrides,
  })
}

export function failedActionDetail(overrides: Partial<ActionDetailOut> = {}): ActionDetailOut {
  return approvedActionDetail({
    status: 'failed',
    execution: execution({
      status: 'failed',
      external_ref: null,
      error_message: 'Mock investigation adapter is unavailable.',
    }),
    audit_events: [
      ...APPROVED_EVENTS,
      auditEvent(5, 'action.execution_started', 'system', 'mock_investigation', EXECUTED_AT),
      auditEvent(6, 'action.execution_failed', 'system', 'mock_investigation', EXECUTED_AT),
    ],
    allowed_operations: [],
    ...overrides,
  })
}

export function rejectedActionDetail(overrides: Partial<ActionDetailOut> = {}): ActionDetailOut {
  return actionDetail({
    status: 'rejected',
    approval: approval({
      decision: 'rejected',
      comment: 'Already covered by the billing incident review.',
      edited_fields: [],
    }),
    audit_events: [
      ...PROPOSED_EVENTS,
      auditEvent(3, 'action.rejected', 'human', 'Operations Manager', DECIDED_AT),
    ],
    allowed_operations: [],
    ...overrides,
  })
}
