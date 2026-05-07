import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Navigate, useParams } from 'react-router-dom'

import { apiRequest } from '../api/client'
import { CoachRosterBoard } from '../components/CoachRosterBoard'
import { CohortIssuesPanel } from '../components/CohortIssuesPanel'
import { SubmissionDraftPanel } from '../components/SubmissionDraftPanel'
import { useAuth } from '../context/AuthContext'
import {
  useCohortIssues,
  useRoster,
  useRosterAvailability,
  useSportBudgetSummary,
  useSports,
  useTerms,
} from '../hooks/usePhaseOneData'
import {
  aidValuesEqual,
  applyAidFieldChange,
  getChangedAidMetrics,
  toAidChangeValuesFromRecord,
} from '../lib/aidFields'
import { buildCohortSummary } from '../lib/cohortTheme'
import type { AidChangeValues, RosterRow, SubmittedAdjustmentResponse } from '../types/api'

function getVisibleAidValues(row: RosterRow) {
  return toAidChangeValuesFromRecord(row.pending_after_values, row)
}

export function CoachSportPage() {
  const { sportSlug } = useParams()
  const { user, logout } = useAuth()
  const queryClient = useQueryClient()
  const sportsQuery = useSports()
  const termsQuery = useTerms()
  const [selectedTermId, setSelectedTermId] = useState<number | null>(null)
  const [selectedClass, setSelectedClass] = useState('ALL')
  const [search, setSearch] = useState('')
  const [editingMembershipId, setEditingMembershipId] = useState<number | null>(null)
  const [draftValues, setDraftValues] = useState<Record<number, AidChangeValues>>({})
  const [recipientEmail, setRecipientEmail] = useState(user?.email ?? '')
  const [submissionComment, setSubmissionComment] = useState('')
  const [submissionMessage, setSubmissionMessage] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const activeInputAnchorRef = useRef<{
    element: HTMLElement
    top: number
  } | null>(null)
  const draftPanelRef = useRef<HTMLDivElement | null>(null)

  const sport = useMemo(
    () => sportsQuery.data?.find((entry) => entry.slug === sportSlug) ?? null,
    [sportSlug, sportsQuery.data],
  )
  const rosterAvailabilityQuery = useRosterAvailability(sport?.id ?? null)
  const rosterQuery = useRoster(sport?.id ?? null, selectedTermId, search)
  const cohortIssuesQuery = useCohortIssues(sport?.id ?? null)
  const selectedTerm = termsQuery.data?.find((term) => term.id === selectedTermId) ?? null
  const budgetSummaryQuery = useSportBudgetSummary(sport?.id ?? null, selectedTerm?.academic_year ?? null)

  useEffect(() => {
    if (rosterAvailabilityQuery.data?.length) {
      setSelectedTermId(rosterAvailabilityQuery.data[0].term_id)
    }
  }, [rosterAvailabilityQuery.data, sportSlug])

  if (!user?.is_admin && sport && !user?.sports.some((entry) => entry.sport_id === sport.id)) {
    const fallbackSport = sportsQuery.data?.[0]
    return fallbackSport ? <Navigate to={`/sports/${fallbackSport.slug}`} replace /> : null
  }

  if (!sportSlug && sportsQuery.data?.[0]) {
    return <Navigate to={`/sports/${sportsQuery.data[0].slug}`} replace />
  }

  if (!sport && sportsQuery.isSuccess) {
    return <Navigate to="/" replace />
  }

  const rows = rosterQuery.data ?? []
  const filteredRows = rows.filter((row) => {
    if (selectedClass === 'ALL') {
      return true
    }
    if (selectedClass === 'UNASSIGNED') {
      return !row.cohort_display
    }
    return row.cohort_display === selectedClass
  })
  const summary = {
    athleteCount: filteredRows.length,
    totalAid: filteredRows.reduce((sum, row) => {
      const visibleValues = draftValues[row.membership_id] ?? getVisibleAidValues(row)
      return sum + Number(visibleValues.athletic_aid_total)
    }, 0),
  }
  const cohortSummary = buildCohortSummary(rows)
  const activeRosterLabel =
    rosterAvailabilityQuery.data?.[0]
      ? `${rosterAvailabilityQuery.data[0].academic_year} ${rosterAvailabilityQuery.data[0].semester}`
      : 'Current roster'
  const rowMap = new Map(rows.map((row) => [row.membership_id, row]))
  const draftEntries = Object.entries(draftValues)
    .map(([membershipId, values]) => {
      const row = rowMap.get(Number(membershipId))
      if (!row) {
        return null
      }
      return { row, values }
    })
    .filter((entry): entry is { row: RosterRow; values: AidChangeValues } => {
      if (!entry) {
        return false
      }
      return getChangedAidMetrics(getVisibleAidValues(entry.row), entry.values).length > 0
    })

  useLayoutEffect(() => {
    const anchor = activeInputAnchorRef.current
    if (!anchor) {
      return
    }

    const currentTop = anchor.element.getBoundingClientRect().top
    const delta = currentTop - anchor.top

    if (Math.abs(delta) > 2) {
      window.scrollBy(0, delta)
    }

    activeInputAnchorRef.current = null
  }, [draftValues])

  function startEdit(row: RosterRow) {
    setEditingMembershipId(row.membership_id)
    setDraftValues((current) => ({
      ...current,
      [row.membership_id]: current[row.membership_id] ?? getVisibleAidValues(row),
    }))
  }

  function cancelEdit(membershipId: number) {
    setEditingMembershipId((current) => (current === membershipId ? null : current))
    const row = rowMap.get(membershipId)
    if (!row) {
      return
    }
    const baseline = getVisibleAidValues(row)
    const currentDraft = draftValues[membershipId]
    if (!currentDraft || aidValuesEqual(baseline, currentDraft)) {
      setDraftValues((current) => {
        const next = { ...current }
        delete next[membershipId]
        return next
      })
    }
  }

  function removeDraft(membershipId: number) {
    setEditingMembershipId((current) => (current === membershipId ? null : current))
    setDraftValues((current) => {
      const next = { ...current }
      delete next[membershipId]
      return next
    })
  }

  function scrollToDraftPanel() {
    draftPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function changeDraftValue(
    membershipId: number,
    field: keyof AidChangeValues,
    value: string,
  ) {
    if (document.activeElement instanceof HTMLElement) {
      activeInputAnchorRef.current = {
        element: document.activeElement,
        top: document.activeElement.getBoundingClientRect().top,
      }
    }

    setDraftValues((current) => {
      const baseline = getVisibleAidValues(rowMap.get(membershipId)!)
      const nextValues = applyAidFieldChange(
        baseline,
        current[membershipId] ?? baseline,
        field,
        value,
      )

      if (aidValuesEqual(baseline, nextValues)) {
        const next = { ...current }
        delete next[membershipId]
        return next
      }

      return {
        ...current,
        [membershipId]: nextValues,
      }
    })
  }

  async function submitDraftChanges() {
    if (!sport || !draftEntries.length) {
      return
    }
    if (!recipientEmail.trim()) {
      setSubmissionMessage('Enter a recipient email before sending test documents.')
      return
    }

    setIsSubmitting(true)
    setSubmissionMessage(null)

    try {
      const result = await apiRequest<SubmittedAdjustmentResponse>('/submissions/adjustments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sport_id: sport.id,
          recipient_email: recipientEmail.trim(),
          comment: submissionComment || null,
          changes: draftEntries.map(({ row, values }) => ({
            membership_id: row.membership_id,
            after_values: values,
          })),
        }),
      })
      setDraftValues({})
      setEditingMembershipId(null)
      setSubmissionComment('')
      setSubmissionMessage(
        `Submitted ${result.adjustments_created} adjustment${result.adjustments_created === 1 ? '' : 's'} and emailed ${result.artifacts_created} document${result.artifacts_created === 1 ? '' : 's'} to ${result.recipient_email}.`,
      )
      await queryClient.invalidateQueries({ queryKey: ['roster'] })
      await queryClient.invalidateQueries({ queryKey: ['sport-budget-summary'] })
    } catch (caught) {
      setSubmissionMessage(caught instanceof Error ? caught.message : 'Unable to submit changes.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="coach-shell">
      <header className="coach-header">
        <div className="coach-header-copy">
          <p className="eyebrow">Coach View</p>
          <h1>{sport?.display_name ?? 'Sport roster'}</h1>
          <p>
            Current team roster. Every player on the team appears here together, and class is just
            a label you can filter by.
          </p>
          <div className="current-roster-pill">{activeRosterLabel}</div>
        </div>

        <div className="coach-header-actions">
          <div className="metric-card compact">
            <span>Athletes</span>
            <strong>{summary.athleteCount}</strong>
          </div>
          <div className="metric-card compact">
            <span>Total athletic aid</span>
            <strong>
              {new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                maximumFractionDigits: 0,
              }).format(summary.totalAid)}
            </strong>
          </div>
          <button type="button" className="ghost-button" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </header>

      <section className="panel coach-legend-panel">
        <div className="panel-heading">
          <div>
            <p className="panel-label">Class Colors</p>
            <h3>Quick roster scan</h3>
          </div>
        </div>
        <div className="cohort-legend">
          {cohortSummary.map((entry) => (
            <div key={entry.label} className="legend-chip">
              <span className={`cohort-badge ${entry.className}`}>{entry.label}</span>
              <strong>{entry.count}</strong>
            </div>
          ))}
        </div>
      </section>

      {budgetSummaryQuery.data ? (
        <section className="budget-banner">
          <strong>
            Budget{' '}
            {new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
              maximumFractionDigits: 0,
            }).format(Number(budgetSummaryQuery.data.budget_amount))}
          </strong>
          <span>
            Allocated{' '}
            {new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
              maximumFractionDigits: 0,
            }).format(Number(budgetSummaryQuery.data.allocated_amount))}{' '}
            ({Number(budgetSummaryQuery.data.percent_used).toFixed(2)}%)
          </span>
        </section>
      ) : null}

      {sport?.id && termsQuery.data ? (
        <CohortIssuesPanel
          issues={cohortIssuesQuery.data ?? []}
          sportId={sport.id}
          terms={termsQuery.data}
        />
      ) : null}

      {draftEntries.length ? (
        <section className="draft-status-bar">
          <div className="draft-status-bar__copy">
            <strong>{draftEntries.length} draft{draftEntries.length === 1 ? '' : 's'} in progress</strong>
            <span>
              {draftEntries
                .flatMap(({ row, values }) =>
                  getChangedAidMetrics(getVisibleAidValues(row), values).map(
                    (metric) => `${row.last_name}: ${metric.shortLabel}`,
                  ),
                )
                .slice(0, 4)
                .join(' • ')}
            </span>
          </div>
          <button
            type="button"
            className="ghost-button mini-button"
            onClick={scrollToDraftPanel}
          >
            Open draft
          </button>
        </section>
      ) : null}

      <div ref={draftPanelRef}>
        <SubmissionDraftPanel
          draftEntries={draftEntries}
          recipientEmail={recipientEmail}
          onRecipientEmailChange={setRecipientEmail}
          comment={submissionComment}
          onCommentChange={setSubmissionComment}
          onRemoveDraft={removeDraft}
          onSubmit={() => void submitDraftChanges()}
          isSubmitting={isSubmitting}
        />
      </div>

      <section className="panel filters-panel">
        <div className="filter-grid coach-filter-grid">
          <label>
            Class Filter
            <select
              value={selectedClass}
              onChange={(event) => setSelectedClass(event.target.value)}
            >
              <option value="ALL">All classes</option>
              {cohortSummary.map((entry) => (
                <option
                  key={entry.label}
                  value={entry.label === 'Unassigned' ? 'UNASSIGNED' : entry.label}
                >
                  {entry.label} ({entry.count})
                </option>
              ))}
            </select>
          </label>

          <label className="search-field">
            Search
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Rocket #, first, or last name"
            />
          </label>
        </div>
      </section>

      <section className="panel roster-panel">
        {submissionMessage ? <p className="submission-banner">{submissionMessage}</p> : null}
        {sportsQuery.isLoading || termsQuery.isLoading || rosterQuery.isLoading ? (
          <div className="empty-state">
            <h3>Loading roster data</h3>
            <p>The coach page is pulling the latest imported roster for this sport.</p>
          </div>
        ) : rosterQuery.isError ? (
          <div className="empty-state error-state">
            <h3>Unable to load roster</h3>
            <p>{rosterQuery.error instanceof Error ? rosterQuery.error.message : 'Unknown error'}</p>
          </div>
        ) : (
          <CoachRosterBoard
            rows={filteredRows}
            editingMembershipId={editingMembershipId}
            draftValues={draftValues}
            onStartEdit={startEdit}
            onCancelEdit={cancelEdit}
            onChangeDraftValue={changeDraftValue}
          />
        )}
      </section>
    </main>
  )
}
