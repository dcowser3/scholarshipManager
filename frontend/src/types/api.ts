export type AuthSport = {
  sport_id: number
  sport_name: string
  role: string | null
}

export type AuthUser = {
  id: number
  email: string
  display_name: string | null
  is_admin: boolean
  sports: AuthSport[]
}

export type Sport = {
  id: number
  csv_name: string
  display_name: string
  slug: string
}

export type Term = {
  id: number
  academic_year: string
  semester: 'FALL' | 'SPRING'
  start_date: string | null
  end_date: string | null
}

export type TermAvailability = {
  term_id: number
  academic_year: string
  semester: 'FALL' | 'SPRING'
  athlete_count: number
}

export type RosterRow = {
  membership_id: number
  athlete_id: string
  first_name: string
  last_name: string
  sport_id: number
  sport_name: string
  term_id: number
  academic_year: string
  semester: 'FALL' | 'SPRING'
  cohort_internal: string | null
  cohort_display: string | null
  exempt: boolean | null
  housing: string | null
  status: string
  athletic_aid_total: string
  oos_tuition: string
  tuition: string
  general_fee: string
  misc_fee: string
  room: string
  board: string
  books: string
  personal_expenses: string
  oos_resource: string
  merit_scholarship: string
  academic_aid: string
  coa_total: string
  source: string | null
  pending_state: string | null
  pending_after_values: Record<string, string> | null
}

export type ImportRun = {
  id: number
  rows_processed: number
  rows_changed: number
  duplicates_dropped: number
  source_filename: string | null
  error_log: Record<string, unknown> | null
}

export type CohortIssue = {
  id: number
  athlete_id: string
  athlete_name: string
  sport_id: number
  sport_name: string
  source_cohort: string | null
  status: string
  resolved_cohort_display: string | null
  has_saved_override: boolean
}

export type AidChangeValues = {
  athletic_aid_total: string
  oos_tuition: string
  tuition: string
  general_fee: string
  misc_fee: string
  room: string
  board: string
  books: string
  personal_expenses: string
  oos_resource: string
}

export type SubmittedAdjustmentResponse = {
  submission_id: string
  adjustments_created: number
  artifacts_created: number
  recipient_email: string
}
