from decimal import Decimal

from pydantic import BaseModel


class SportResponse(BaseModel):
    id: int
    csv_name: str
    display_name: str
    slug: str


class TermResponse(BaseModel):
    id: int
    academic_year: str
    semester: str
    start_date: str | None
    end_date: str | None


class RosterRowResponse(BaseModel):
    membership_id: int
    athlete_id: str
    first_name: str
    last_name: str
    sport_id: int
    sport_name: str
    term_id: int
    academic_year: str
    semester: str
    cohort_internal: str | None
    cohort_display: str | None
    exempt: bool | None
    housing: str | None
    status: str
    athletic_aid_total: Decimal
    oos_tuition: Decimal
    tuition: Decimal
    general_fee: Decimal
    misc_fee: Decimal
    room: Decimal
    board: Decimal
    books: Decimal
    personal_expenses: Decimal
    oos_resource: Decimal
    merit_scholarship: Decimal
    academic_aid: Decimal
    coa_total: Decimal
    source: str | None
    pending_state: str | None = None
    pending_after_values: dict[str, str] | None = None
