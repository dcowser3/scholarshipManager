import type { AidChangeValues, RosterRow } from '../types/api'

export const aidMetricDefinitions: Array<{
  key: keyof AidChangeValues
  shortLabel: string
  fullLabel: string
  editable: boolean
}> = [
  {
    key: 'athletic_aid_total',
    shortLabel: 'Ath Aid',
    fullLabel: 'Athletic Aid Total',
    editable: false,
  },
  {
    key: 'oos_tuition',
    shortLabel: 'OOS',
    fullLabel: 'Out-of-State Tuition',
    editable: true,
  },
  { key: 'tuition', shortLabel: 'Tuition', fullLabel: 'Tuition', editable: true },
  { key: 'general_fee', shortLabel: 'Gen Fee', fullLabel: 'General Fee', editable: true },
  { key: 'misc_fee', shortLabel: 'Misc', fullLabel: 'Miscellaneous Fees', editable: true },
  { key: 'room', shortLabel: 'Room', fullLabel: 'Room', editable: true },
  { key: 'board', shortLabel: 'Board', fullLabel: 'Board', editable: true },
  { key: 'books', shortLabel: 'Books', fullLabel: 'Books', editable: true },
  {
    key: 'personal_expenses',
    shortLabel: 'P/E',
    fullLabel: 'Personal Expenses',
    editable: true,
  },
  {
    key: 'oos_resource',
    shortLabel: 'OOS Res',
    fullLabel: 'Out-of-State Resource',
    editable: true,
  },
]

const totalMetricKey: keyof AidChangeValues = 'athletic_aid_total'

const deltaMetricKeys = aidMetricDefinitions
  .filter((metric) => metric.key !== totalMetricKey)
  .map((metric) => metric.key)

export function toAidChangeValues(row: RosterRow): AidChangeValues {
  return {
    athletic_aid_total: row.athletic_aid_total,
    oos_tuition: row.oos_tuition,
    tuition: row.tuition,
    general_fee: row.general_fee,
    misc_fee: row.misc_fee,
    room: row.room,
    board: row.board,
    books: row.books,
    personal_expenses: row.personal_expenses,
    oos_resource: row.oos_resource,
  }
}

export function toAidChangeValuesFromRecord(
  record: Partial<Record<keyof AidChangeValues, string>> | null | undefined,
  fallback: RosterRow,
): AidChangeValues {
  const baseline = toAidChangeValues(fallback)
  if (!record) {
    return baseline
  }

  return {
    athletic_aid_total: record.athletic_aid_total ?? baseline.athletic_aid_total,
    oos_tuition: record.oos_tuition ?? baseline.oos_tuition,
    tuition: record.tuition ?? baseline.tuition,
    general_fee: record.general_fee ?? baseline.general_fee,
    misc_fee: record.misc_fee ?? baseline.misc_fee,
    room: record.room ?? baseline.room,
    board: record.board ?? baseline.board,
    books: record.books ?? baseline.books,
    personal_expenses: record.personal_expenses ?? baseline.personal_expenses,
    oos_resource: record.oos_resource ?? baseline.oos_resource,
  }
}

function parseAidValue(value: string) {
  const parsed = Number.parseFloat(value)
  if (!Number.isFinite(parsed)) {
    return 0
  }
  return parsed
}

function formatAidValue(value: number) {
  return value.toFixed(2)
}

export function applyAidFieldChange(
  baseline: AidChangeValues,
  current: AidChangeValues,
  field: keyof AidChangeValues,
  value: string,
): AidChangeValues {
  const next = {
    ...current,
    [field]: value,
  }

  if (field === totalMetricKey) {
    return next
  }

  const delta = deltaMetricKeys.reduce((sum, key) => {
    return sum + (parseAidValue(next[key]) - parseAidValue(baseline[key]))
  }, 0)

  next.athletic_aid_total = formatAidValue(parseAidValue(baseline.athletic_aid_total) + delta)
  return next
}

export function getChangedAidMetrics(
  baseline: AidChangeValues,
  current: AidChangeValues,
) {
  return aidMetricDefinitions.filter(
    (metric) =>
      metric.key !== totalMetricKey &&
      parseAidValue(baseline[metric.key]) !== parseAidValue(current[metric.key]),
  )
}

export function getAidMetricDelta(
  baseline: AidChangeValues,
  current: AidChangeValues,
  key: keyof AidChangeValues,
) {
  return parseAidValue(current[key]) - parseAidValue(baseline[key])
}

export function aidValuesEqual(left: AidChangeValues, right: AidChangeValues) {
  return aidMetricDefinitions.every(
    (metric) => parseAidValue(left[metric.key]) === parseAidValue(right[metric.key]),
  )
}
