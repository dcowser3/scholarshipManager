from pydantic import BaseModel


class TermAvailabilityResponse(BaseModel):
    term_id: int
    academic_year: str
    semester: str
    athlete_count: int

