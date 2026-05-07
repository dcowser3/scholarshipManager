import type { AidChangeValues, RosterRow } from '../types/api'
import { getCohortTheme } from '../lib/cohortTheme'
import {
  aidMetricDefinitions,
  getAidMetricDelta,
  getChangedAidMetrics,
  toAidChangeValuesFromRecord,
} from '../lib/aidFields'

function formatCurrency(value: string) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number(value))
}

type CoachRosterBoardProps = {
  rows: RosterRow[]
  editingMembershipId: number | null
  draftValues: Record<number, AidChangeValues>
  onStartEdit: (row: RosterRow) => void
  onCancelEdit: (membershipId: number) => void
  onChangeDraftValue: (
    membershipId: number,
    field: keyof AidChangeValues,
    value: string,
  ) => void
}

export function CoachRosterBoard({
  rows,
  editingMembershipId,
  draftValues,
  onStartEdit,
  onCancelEdit,
  onChangeDraftValue,
}: CoachRosterBoardProps) {
  if (!rows.length) {
    return (
      <div className="empty-state">
        <h3>No athletes found</h3>
        <p>This sport and filter combination does not have visible athletes right now.</p>
      </div>
    )
  }

  return (
    <div className="coach-roster-board">
      {rows.map((row) => {
        const cohortTheme = getCohortTheme(row.cohort_display)
        const isEditing = editingMembershipId === row.membership_id
        const hasPending = Boolean(row.pending_state)
        const pendingSourceLabel = row.pending_source === 'EMAIL' ? 'Email' : row.pending_source
        const baselineValues = toAidChangeValuesFromRecord(row.pending_after_values, row)
        const visibleValues = draftValues[row.membership_id] ?? baselineValues
        const changedMetrics = getChangedAidMetrics(baselineValues, visibleValues)
        const hasDraftChanges = changedMetrics.length > 0
        const hasNegativeChange = changedMetrics.some(
          (metric) => getAidMetricDelta(baselineValues, visibleValues, metric.key) < 0,
        )

        return (
          <article
            key={row.membership_id}
            className={`coach-roster-card ${cohortTheme.className} ${hasPending ? 'is-pending' : ''} ${hasDraftChanges ? 'is-draft-changed' : ''} ${hasNegativeChange ? 'is-draft-negative' : ''}`}
          >
            <div className="coach-roster-card__header">
              <div className="coach-roster-card__identity">
                <div className="coach-roster-card__name-group">
                  <div className="coach-roster-card__name-row">
                    <h3>{row.first_name} {row.last_name}</h3>
                    <div className="coach-roster-card__actions">
                      {isEditing ? (
                        <button
                          type="button"
                          className="ghost-button mini-button"
                          onClick={() => onCancelEdit(row.membership_id)}
                        >
                          {hasDraftChanges ? 'Done' : 'Cancel'}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="ghost-button mini-button"
                          onClick={() => onStartEdit(row)}
                        >
                          Edit aid
                        </button>
                      )}
                    </div>
                  </div>
                  <p>{row.athlete_id}</p>
                  {hasPending ? (
                    <span className="coach-roster-card__pending-copy">
                      Pending adjustment is already staged for this athlete.
                    </span>
                  ) : null}
                  {hasDraftChanges ? (
                    <span
                      className={`coach-roster-card__changed-copy ${hasNegativeChange ? 'is-negative' : ''}`}
                    >
                      Changed: {changedMetrics.map((metric) => metric.fullLabel).join(', ')}
                    </span>
                  ) : null}
                </div>
                <div className="coach-roster-card__meta">
                  <span className={`cohort-badge ${cohortTheme.className}`}>
                    {cohortTheme.label}
                  </span>
                  <span className={`status-pill status-${row.status.toLowerCase()}`}>
                    {row.status}
                  </span>
                  {hasPending ? <span className="pending-pill">Pending</span> : null}
                  {pendingSourceLabel ? <span className="source-pill">{pendingSourceLabel}</span> : null}
                </div>
              </div>

              <div className="coach-roster-card__summary">
                <div className="coach-roster-card__summary-copy">
                  <span>{hasPending && !isEditing ? 'Pending total' : 'Total'}</span>
                  <strong>{formatCurrency(visibleValues.athletic_aid_total)}</strong>
                </div>
              </div>
            </div>

            <div className="coach-roster-card__metrics">
              {aidMetricDefinitions.map((metric) => (
                <div
                  key={`${row.membership_id}-${metric.key}`}
                  className={`coach-metric ${
                    baselineValues[metric.key] !== visibleValues[metric.key]
                      ? getAidMetricDelta(baselineValues, visibleValues, metric.key) < 0
                        ? 'is-changed-negative'
                        : 'is-changed'
                      : ''
                  }`}
                >
                  <span className="coach-metric__label">{metric.shortLabel}</span>
                  {isEditing && metric.editable ? (
                    <input
                      className="coach-metric__input"
                      inputMode="decimal"
                      value={visibleValues[metric.key]}
                      onChange={(event) =>
                        onChangeDraftValue(row.membership_id, metric.key, event.target.value)
                      }
                    />
                  ) : (
                    <strong>{formatCurrency(visibleValues[metric.key])}</strong>
                  )}
                </div>
              ))}
            </div>
          </article>
        )
      })}
    </div>
  )
}
