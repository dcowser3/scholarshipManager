import type { AidChangeValues, RosterRow } from '../types/api'
import {
  getAidMetricDelta,
  getChangedAidMetrics,
  toAidChangeValuesFromRecord,
} from '../lib/aidFields'

type DraftEntry = {
  row: RosterRow
  values: AidChangeValues
}

type SubmissionDraftPanelProps = {
  draftEntries: DraftEntry[]
  recipientEmail: string
  onRecipientEmailChange: (value: string) => void
  comment: string
  onCommentChange: (value: string) => void
  onRemoveDraft: (membershipId: number) => void
  onSubmit: () => void
  isSubmitting: boolean
}

function formatCurrency(value: string) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number(value))
}

export function SubmissionDraftPanel({
  draftEntries,
  recipientEmail,
  onRecipientEmailChange,
  comment,
  onCommentChange,
  onRemoveDraft,
  onSubmit,
  isSubmitting,
}: SubmissionDraftPanelProps) {
  if (!draftEntries.length) {
    return null
  }

  return (
    <section className="panel draft-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-label">Draft Changes</p>
          <h3>{draftEntries.length} athlete{draftEntries.length === 1 ? '' : 's'} ready to submit</h3>
          <p>These edits will create pending financial aid adjustments. The source roster itself stays unchanged until the next import.</p>
        </div>
        <button
          type="button"
          className="primary-button"
          onClick={onSubmit}
          disabled={isSubmitting}
        >
          {isSubmitting ? 'Submitting...' : 'Submit adjustments'}
        </button>
      </div>

      <div className="draft-list">
        {draftEntries.map(({ row, values }) => (
          <div key={row.membership_id} className="draft-card">
            <div className="draft-card__header">
              <div>
                <strong>{row.first_name} {row.last_name}</strong>
                <p>{row.athlete_id}</p>
              </div>
              <button
                type="button"
                className="ghost-button mini-button"
                onClick={() => onRemoveDraft(row.membership_id)}
              >
                Remove
              </button>
            </div>
            {(() => {
              const baseline = toAidChangeValuesFromRecord(row.pending_after_values, row)
              const changedMetrics = getChangedAidMetrics(baseline, values)

              return (
                <>
                  <div className="draft-card__summary">
                    <span>
                      Current {formatCurrency(baseline.athletic_aid_total)}
                    </span>
                    <span>Proposed {formatCurrency(values.athletic_aid_total)}</span>
                  </div>
                  <div className="draft-card__changes">
                    {changedMetrics.map((metric) => {
                      const delta = getAidMetricDelta(baseline, values, metric.key)
                      const direction = delta >= 0 ? '+' : '-'
                      return (
                        <span
                          key={metric.key}
                          className={`draft-change-chip ${delta < 0 ? 'is-negative' : 'is-positive'}`}
                        >
                          {metric.fullLabel} {direction}{formatCurrency(String(Math.abs(delta)))}
                        </span>
                      )
                    })}
                  </div>
                </>
              )
            })()}
          </div>
        ))}
      </div>

      <label>
        Send test email to
        <input
          type="email"
          value={recipientEmail}
          onChange={(event) => onRecipientEmailChange(event.target.value)}
          placeholder="name@example.com"
        />
      </label>

      <label>
        Submission note
        <textarea
          className="draft-textarea"
          value={comment}
          onChange={(event) => onCommentChange(event.target.value)}
          placeholder="Optional note for the scholarship manager"
          rows={3}
        />
      </label>
    </section>
  )
}
