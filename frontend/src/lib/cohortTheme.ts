import type { RosterRow } from '../types/api'

type CohortTheme = {
  key: string
  label: string
  className: string
}

const palette = ['gold', 'sky', 'mint', 'coral', 'violet', 'teal']

export function getCohortTheme(cohortDisplay: string | null | undefined): CohortTheme {
  if (!cohortDisplay) {
    return {
      key: 'unassigned',
      label: 'Unassigned',
      className: 'cohort-unassigned',
    }
  }

  if (cohortDisplay === 'GRAD/NON') {
    return {
      key: 'grad-non',
      label: cohortDisplay,
      className: 'cohort-grad-non',
    }
  }

  const match = cohortDisplay.match(/^(\d{2})-(\d{2})$/)
  if (match) {
    const index = Number(match[1]) % palette.length
    return {
      key: cohortDisplay,
      label: cohortDisplay,
      className: `cohort-${palette[index]}`,
    }
  }

  return {
    key: cohortDisplay,
    label: cohortDisplay,
    className: 'cohort-unassigned',
  }
}

export function buildCohortSummary(rows: RosterRow[]) {
  const grouped = new Map<string, { label: string; className: string; count: number }>()

  for (const row of rows) {
    const theme = getCohortTheme(row.cohort_display)
    const existing = grouped.get(theme.key)
    if (existing) {
      existing.count += 1
      continue
    }
    grouped.set(theme.key, {
      label: theme.label,
      className: theme.className,
      count: 1,
    })
  }

  return Array.from(grouped.values()).sort((left, right) => left.label.localeCompare(right.label))
}

