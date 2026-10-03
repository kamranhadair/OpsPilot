import { describe, expect, it } from 'vitest'

import { snapshot } from '../../tests/fixtures/api'
import { formatChange, formatDimensions, formatMetricValue, formatScore } from './format'

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
