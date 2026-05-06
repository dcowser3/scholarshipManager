import type { RosterRow } from '../types/api'
import { getCohortTheme } from '../lib/cohortTheme'

const currencyColumns: Array<keyof RosterRow> = [
  'athletic_aid_total',
  'oos_tuition',
  'tuition',
  'general_fee',
  'misc_fee',
  'room',
  'board',
  'books',
  'personal_expenses',
  'oos_resource',
  'merit_scholarship',
  'academic_aid',
]

function formatCurrency(value: string) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number(value))
}

export function RosterTable({ rows }: { rows: RosterRow[] }) {
  if (!rows.length) {
    return (
      <div className="empty-state">
        <h3>No athletes found</h3>
        <p>This sport and term combination does not have imported roster data yet.</p>
      </div>
    )
  }

  return (
    <div className="table-shell">
      <table className="roster-table">
        <thead>
          <tr>
            <th>Athlete</th>
            <th>Rocket #</th>
            <th>Class</th>
            <th>Status</th>
            {currencyColumns.map((column) => (
              <th key={column}>{toColumnLabel(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const cohortTheme = getCohortTheme(row.cohort_display)
            return (
            <tr key={row.membership_id} className={`roster-row ${cohortTheme.className}`}>
              <td>
                <div className="athlete-cell">
                  <span>{row.first_name} {row.last_name}</span>
                  <small>{row.semester} {row.academic_year}</small>
                </div>
              </td>
              <td>{row.athlete_id}</td>
              <td>
                <span className={`cohort-badge ${cohortTheme.className}`}>
                  {cohortTheme.label}
                </span>
              </td>
              <td>
                <span className={`status-pill status-${row.status.toLowerCase()}`}>
                  {row.status}
                </span>
              </td>
              {currencyColumns.map((column) => (
                <td key={`${row.membership_id}-${column}`}>{formatCurrency(String(row[column] ?? 0))}</td>
              ))}
            </tr>
          )})}
        </tbody>
      </table>
    </div>
  )
}

function toColumnLabel(value: string) {
  const labels: Record<string, string> = {
    athletic_aid_total: 'Ath Aid',
    oos_tuition: 'OOS',
    tuition: 'Tuition',
    general_fee: 'Gen Fee',
    misc_fee: 'Misc',
    room: 'Room',
    board: 'Board',
    books: 'Books',
    personal_expenses: 'P/E',
    oos_resource: 'OOS Res',
    merit_scholarship: 'Merit',
    academic_aid: 'Acad',
  }

  return labels[value] ?? value
}
