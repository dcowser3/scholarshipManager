import { useQuery } from '@tanstack/react-query'

import { apiRequest } from '../api/client'
import type {
  CohortIssue,
  RosterRow,
  Sport,
  SportBudgetSummary,
  Term,
  TermAvailability,
} from '../types/api'

export function useSports() {
  return useQuery({
    queryKey: ['sports'],
    queryFn: () => apiRequest<Sport[]>('/sports'),
  })
}

export function useTerms() {
  return useQuery({
    queryKey: ['terms'],
    queryFn: () => apiRequest<Term[]>('/terms'),
  })
}

export function useRoster(sportId: number | null, termId: number | null, search: string) {
  return useQuery({
    queryKey: ['roster', sportId, termId, search],
    queryFn: () =>
      apiRequest<RosterRow[]>(
        `/rosters?sport_id=${sportId}&term_id=${termId}&search=${encodeURIComponent(search)}`,
      ),
    enabled: Boolean(sportId && termId),
  })
}

export function useCohortIssues(sportId: number | null) {
  return useQuery({
    queryKey: ['cohort-issues', sportId],
    queryFn: () => apiRequest<CohortIssue[]>(`/cohort-issues?sport_id=${sportId}`),
    enabled: Boolean(sportId),
  })
}

export function useRosterAvailability(sportId: number | null) {
  return useQuery({
    queryKey: ['roster-availability', sportId],
    queryFn: () =>
      apiRequest<TermAvailability[]>(`/roster-availability?sport_id=${sportId}`),
    enabled: Boolean(sportId),
  })
}

export function useSportBudgetSummary(sportId: number | null, academicYear: string | null) {
  return useQuery({
    queryKey: ['sport-budget-summary', sportId, academicYear],
    queryFn: () =>
      apiRequest<SportBudgetSummary>(
        `/sport-budgets/summary?sport_id=${sportId}&academic_year=${encodeURIComponent(academicYear ?? '')}`,
      ),
    enabled: Boolean(sportId && academicYear),
  })
}
