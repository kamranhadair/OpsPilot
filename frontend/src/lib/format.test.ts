import { describe, expect, it } from 'vitest'

import { snapshot } from '../../tests/fixtures/api'
import {
  formatChange,
  formatDimensions,
  formatEvidenceValue,
  formatFraction,
  formatLatencyMs,
  formatMetricValue,
  formatScore,
  formatTokens,
  formatUsd,
} from './format'

describe('format', () => {
  it('formats values by unit', () => {
    expect(formatMetricValue(1234, 'count')).toBe('1,234')
    expect(formatMetricValue(16.04, 'percent')).toBe('16.0%')
    expect(formatMetricValue(42.5, 'minutes')).toBe('42.5 min')
  })

  it('uses the backend change and never invents one for a missing baseline', () => {
    expect(formatChange(snapshot({ change_pct: -12.34 }))).toBe('−12.3%')
    expect(formatChange(snapshot({ unit: 'percent', change_pp: 7.9, change_pct: 98 }))).toBe(
      '+7.9 pp',
    )
    expect(formatChange(snapshot({ change_pct: null, baseline_zero: true }))).toBe(
      'Baseline zero',
    )
    expect(formatChange(snapshot({ change_pct: null, baseline_empty: true }))).toBe('No baseline')
  })

  it('formats scores in the comparison the detector used', () => {
    expect(formatScore(110, 'relative_pct')).toBe('+110.0%')
    expect(formatScore(7.9, 'percentage_points')).toBe('+7.9 pp')
    expect(formatScore(null, 'relative_pct')).toBe('Unavailable')
  })

  it('describes the anomaly context', () => {
    expect(formatDimensions({})).toBe('All tickets')
    expect(formatDimensions({ region: 'emea', customer_tier: 'enterprise' })).toBe(
      'Region: EMEA · Tier: Enterprise',
    )
  })
})

describe('formatEvidenceValue', () => {
  it('formats backend values by unit without deriving anything', () => {
    expect(formatEvidenceValue({ value: 412, unit: 'count' })).toBe('412')
    expect(formatEvidenceValue({ value: 77.3, unit: 'percent' })).toBe('77.3%')
    expect(formatEvidenceValue({ value: 4.25, unit: 'percentage_points' })).toBe('4.3 pp')
    expect(formatEvidenceValue({ value: 3, unit: null })).toBe('3')
    expect(formatEvidenceValue({ value: 'high', unit: null })).toBe('High')
    expect(formatEvidenceValue({ value: 'billing_api', unit: null })).toBe('Billing API')
  })

  it('never fabricates a number for a missing value', () => {
    expect(formatEvidenceValue({ value: null, unit: 'percent' })).toBe('Unavailable')
  })
})

describe('formatFraction', () => {
  it('formats a backend fraction as a percentage', () => {
    expect(formatFraction(1)).toBe('100.0%')
    expect(formatFraction(0)).toBe('0.0%')
    expect(formatFraction(0.041666)).toBe('4.2%')
  })

  it('shows an unmeasured rate as n/a', () => {
    expect(formatFraction(null)).toBe('n/a')
  })
})

describe('observability formatting', () => {
  it('formats latency in ms below a second and seconds above', () => {
    expect(formatLatencyMs(842.4)).toBe('842 ms')
    expect(formatLatencyMs(0)).toBe('0 ms')
    expect(formatLatencyMs(2150)).toBe('2.15 s')
    expect(formatLatencyMs(null)).toBe('n/a')
  })

  it('formats cost in USD and shows null as an em dash', () => {
    expect(formatUsd(0.0123)).toBe('$0.0123')
    expect(formatUsd(1.5)).toBe('$1.50')
    expect(formatUsd(0)).toBe('$0.00')
    expect(formatUsd(null)).toBe('—')
  })

  it('formats token counts and shows null as not reported', () => {
    expect(formatTokens(12345)).toBe('12,345')
    expect(formatTokens(0)).toBe('0')
    expect(formatTokens(null)).toBe('not reported')
  })
})
