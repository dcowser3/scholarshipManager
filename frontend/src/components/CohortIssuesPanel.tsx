import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { apiRequest } from '../api/client'
import { getCohortTheme } from '../lib/cohortTheme'
import type { CohortIssue, Term } from '../types/api'

type CohortIssuesPanelProps = {
  issues: CohortIssue[]
  sportId: number
  terms: Term[]
}

function uniqueAcademicYears(terms: Term[]) {
  return Array.from(new Set(terms.map((term) => term.academic_year))).sort().reverse()
}

export function CohortIssuesPanel({ issues, sportId, terms }: CohortIssuesPanelProps) {
  const queryClient = useQueryClient()
  const academicYears = uniqueAcademicYears(terms)
  const [selectedYears, setSelectedYears] = useState<Record<number, string>>({})
  const [busyId, setBusyId] = useState<number | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [isExpanded, setIsExpanded] = useState(false)

  async function resolveIssue(issue: CohortIssue) {
    const academicYear = selectedYears[issue.id] ?? academicYears[0]
    if (!academicYear) {
      setMessage('No academic years are configured yet.')
      return
    }

    setBusyId(issue.id)
    setMessage(null)

    try {
      await apiRequest(`/cohort-issues/${issue.id}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ academic_year: academicYear }),
      })
      setMessage(`${issue.athlete_name} was assigned to ${academicYear}.`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['cohort-issues', sportId] }),
        queryClient.invalidateQueries({ queryKey: ['roster'] }),
      ])
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : 'Unable to resolve cohort issue.')
    } finally {
      setBusyId(null)
    }
  }

  if (!issues.length) {
    return null
  }

  return (
    <section className="panel compact-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-label">Needs Cohort Assignment</p>
          <h3>{issues.length} athletes need a class tag</h3>
          <p>These players still appear on the roster now. This just saves their class label for later imports.</p>
        </div>
        <button
          type="button"
          className="ghost-button"
          onClick={() => setIsExpanded((current) => !current)}
        >
          {isExpanded ? 'Hide' : 'Review'}
        </button>
      </div>

      {isExpanded ? (
        <>
          <div className="issue-list">
            {issues.map((issue) => {
              const selectedYear = selectedYears[issue.id] ?? academicYears[0] ?? ''
              const cohortTheme = getCohortTheme(issue.source_cohort)
              return (
                <div key={issue.id} className="issue-card">
                  <div className="issue-main">
                    <span className={`cohort-badge compact ${cohortTheme.className}`}>
                      {issue.source_cohort ?? 'Blank'}
                    </span>
                    <strong>{issue.athlete_name}</strong>
                    <p>{issue.athlete_id} needs a saved class assignment</p>
                  </div>

                  <div className="issue-actions">
                    <select
                      value={selectedYear}
                      onChange={(event) =>
                        setSelectedYears((current) => ({
                          ...current,
                          [issue.id]: event.target.value,
                        }))
                      }
                    >
                      {academicYears.map((year) => (
                        <option key={year} value={year}>
                          {year}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="primary-button"
                      onClick={() => void resolveIssue(issue)}
                      disabled={busyId === issue.id}
                    >
                      {busyId === issue.id ? 'Saving...' : 'Save class'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>

          {message ? <p className="import-message">{message}</p> : null}
        </>
      ) : null}
    </section>
  )
}
