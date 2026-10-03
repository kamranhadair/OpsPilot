/**
 * Presentation-only formatting of values the backend already computed.
 * Nothing here derives a metric, a change, a threshold or a severity.
 */

import type { Comparison, MetricSnapshotOut, MetricUnit } from '../types/api'

const COUNT = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })
const ONE_DECIMAL = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

export function formatMetricValue(value: number, unit: MetricUnit): string {
  switch (unit) {
    case 'percent':
      return `${ONE_DECIMAL.format(value)}%`
    case 'minutes':
      return `${COUNT.format(value)} min`
    case 'count':
      return COUNT.format(value)
  }
}

function signed(value: number, suffix: string): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '±'
  return `${sign}${ONE_DECIMAL.format(Math.abs(value))}${suffix}`
}

/**
 * The backend-computed change versus baseline. Rate metrics use percentage
 * points; other metrics use percent. A missing or zero baseline is stated
 * explicitly rather than rendered as a number.
 */
export function formatChange(
  snapshot: Pick<
    MetricSnapshotOut,
    'unit' | 'change_pct' | 'change_pp' | 'baseline_zero' | 'baseline_empty'
  >,
): string {
  if (snapshot.unit === 'percent' && snapshot.change_pp !== null) {
    return signed(snapshot.change_pp, ' pp')
  }
  if (snapshot.change_pct !== null) return signed(snapshot.change_pct, '%')
  if (snapshot.baseline_empty) return 'No baseline'
  if (snapshot.baseline_zero) return 'Baseline zero'
  return 'Change unavailable'
}

/** A detector threshold or observed change, in the detector's comparison unit. */
export function formatThresholdValue(value: number, comparison: Comparison): string {
  const rounded = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)
  return `${rounded}${comparison === 'percentage_points' ? ' pp' : '%'}`
}

/** The anomaly's triggering change as stored by the detector. */
export function formatScore(
  score: number | null,
  comparison: Comparison,
): string {
  if (score === null) return 'Unavailable'
  return signed(score, comparison === 'percentage_points' ? ' pp' : '%')
}

const UTC_DATE_TIME = new Intl.DateTimeFormat('en-GB', {
  year: 'numeric',
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'UTC',
})

const UTC_DATE = new Intl.DateTimeFormat('en-GB', {
  month: 'short',
  day: '2-digit',
  timeZone: 'UTC',
})

export function formatUtc(iso: string): string {
  return `${UTC_DATE_TIME.format(new Date(iso))} UTC`
}

export function formatUtcDate(iso: string): string {
  return UTC_DATE.format(new Date(iso))
}

const DIMENSION_LABELS: Record<string, string> = {
  category: 'Category',
  product: 'Product',
  region: 'Region',
  customer_tier: 'Tier',
  support_team: 'Team',
}

export function humanize(value: string): string {
  return value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/** Acronym-style values that title case would garble. */
const VALUE_LABELS: Record<string, string> = {
  emea: 'EMEA',
  apac: 'APAC',
  north_america: 'North America',
  billing_api: 'Billing API',
}

function formatValue(value: string): string {
  return VALUE_LABELS[value] ?? humanize(value)
}

export function formatDimensions(dimensions: Record<string, string>): string {
  const entries = Object.entries(dimensions)
  if (entries.length === 0) return 'All tickets'
  return entries
    .map(([key, value]) => `${DIMENSION_LABELS[key] ?? humanize(key)}: ${formatValue(value)}`)
    .join(' · ')
}

export function formatFamily(dimensions: string[]): string {
  return dimensions.map((d) => DIMENSION_LABELS[d] ?? humanize(d)).join(' + ')
}
