import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { AdminImportPanel } from '../components/AdminImportPanel'
import { CohortIssuesPanel } from '../components/CohortIssuesPanel'
import { RosterTable } from '../components/RosterTable'
import { useAuth } from '../context/AuthContext'
import {
  useCohortIssues,
  useRoster,
  useRosterAvailability,
  useSports,
  useTerms,
} from '../hooks/usePhaseOneData'

function chooseDefaultTerm(termIds: number[]) {
  return termIds[0] ?? null
}

export function AdminDashboardPage() {
  const { user, logout } = useAuth()
  const sportsQuery = useSports()
  const termsQuery = useTerms()
  const [selectedSportId, setSelectedSportId] = useState<number | null>(null)
  const [selectedTermId, setSelectedTermId] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (!sportsQuery.data?.length) {
      return
    }
    setSelectedSportId((current) => current ?? sportsQuery.data[0].id)
  }, [sportsQuery.data])

  const rosterAvailabilityQuery = useRosterAvailability(selectedSportId)
  const rosterQuery = useRoster(selectedSportId, selectedTermId, search)
  const cohortIssuesQuery = useCohortIssues(selectedSportId)

  useEffect(() => {
    if (!termsQuery.data?.length) {
      return
    }

    if (rosterAvailabilityQuery.data?.length) {
      setSelectedTermId(rosterAvailabilityQuery.data[0].term_id)
      return
    }

    setSelectedTermId((current) =>
      current ?? chooseDefaultTerm(termsQuery.data.map((term) => term.id)),
    )
  }, [rosterAvailabilityQuery.data, termsQuery.data, selectedSportId])

  const rows = rosterQuery.data ?? []
  const summary = {
    athleteCount: rows.length,
    totalAid: rows.reduce((sum, row) => sum + Number(row.athletic_aid_total), 0),
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-card brand-card">
          <p className="eyebrow">Admin Workspace</p>
          <h1>Scholarship Operations</h1>
          <p>
            Import source data, review sport-specific roster pages, and help resolve missing cohort
            assignments without touching the coach experience.
          </p>
        </div>

        <div className="sidebar-card">
          <p className="panel-label">Signed in as</p>
          <h2>{user?.display_name ?? user?.email}</h2>
          <p>Scholarship admin</p>
          <button type="button" className="ghost-button" onClick={() => void logout()}>
            Sign out
          </button>
          <p className="helper-copy">
            Coach demo logins:
            <br />
            football.coach@utoledo.edu
            <br />
            softball.coach@utoledo.edu
          </p>
        </div>

        <div className="sidebar-card">
          <p className="panel-label">Sports</p>
          <div className="sport-list">
            {sportsQuery.data?.map((sport) => (
              <div key={sport.id} className="sport-preview-row">
                <button
                  type="button"
                  className={selectedSportId === sport.id ? 'sport-chip active' : 'sport-chip'}
                  onClick={() => setSelectedSportId(sport.id)}
                >
                  {sport.display_name}
                </button>
                <Link className="preview-link" to={`/sports/${sport.slug}`} target="_blank" rel="noreferrer">
                  Open coach page
                </Link>
              </div>
            ))}
          </div>
        </div>
      </aside>

      <section className="content">
        <header className="hero-panel">
          <div>
            <p className="eyebrow">University of Toledo Athletics</p>
            <h2>Admin overview</h2>
            <p>
              This is the behind-the-scenes workspace. Coaches should not land here in the MVP.
            </p>
          </div>

          <div className="hero-metrics">
            <div className="metric-card">
              <span>Athletes on page</span>
              <strong>{summary.athleteCount}</strong>
            </div>
            <div className="metric-card">
              <span>Total athletic aid</span>
              <strong>
                {new Intl.NumberFormat('en-US', {
                  style: 'currency',
                  currency: 'USD',
                  maximumFractionDigits: 0,
                }).format(summary.totalAid)}
              </strong>
            </div>
          </div>
        </header>

        <AdminImportPanel />

        {selectedSportId && termsQuery.data ? (
          <CohortIssuesPanel
            issues={cohortIssuesQuery.data ?? []}
            sportId={selectedSportId}
            terms={termsQuery.data}
          />
        ) : null}

        <section className="panel filters-panel">
          <div className="filter-grid">
            <label>
              Term
              <select
                value={selectedTermId ?? ''}
                onChange={(event) => setSelectedTermId(Number(event.target.value))}
              >
                {termsQuery.data?.map((term) => (
                  <option key={term.id} value={term.id}>
                    {term.academic_year} {term.semester}
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

        <section className="panel">
          {sportsQuery.isLoading || termsQuery.isLoading || rosterQuery.isLoading ? (
            <div className="empty-state">
              <h3>Loading roster data</h3>
              <p>The dashboard is pulling sports, terms, and roster rows from the API.</p>
            </div>
          ) : rosterQuery.isError ? (
            <div className="empty-state error-state">
              <h3>Unable to load roster</h3>
              <p>{rosterQuery.error instanceof Error ? rosterQuery.error.message : 'Unknown error'}</p>
            </div>
          ) : (
            <RosterTable rows={rosterQuery.data ?? []} />
          )}
        </section>
      </section>
    </main>
  )
}
