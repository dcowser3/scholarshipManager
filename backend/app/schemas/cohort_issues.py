from pydantic import BaseModel


class CohortIssueResponse(BaseModel):
    id: int
    athlete_id: str
    athlete_name: str
    sport_id: int
    sport_name: str
    source_cohort: str | None
    status: str
    resolved_cohort_display: str | None
    has_saved_override: bool


class ResolveCohortIssueRequest(BaseModel):
    academic_year: str

