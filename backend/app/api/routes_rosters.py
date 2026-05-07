from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import get_accessible_sports, require_sport_access, require_user
from app.db.session import get_db
from app.models.core import Athlete, Sport, Term
from app.models.roster import AidRecord, RosterMembership
from app.models.submission import Adjustment, Submission
from app.models.user import User
from app.schemas.availability import TermAvailabilityResponse
from app.schemas.roster import (
    RosterRowResponse,
    SportBudgetSummaryResponse,
    SportResponse,
    TermResponse,
)
from app.services.budgets import get_sport_budget_summary

router = APIRouter(tags=["rosters"])


@router.get("/sports", response_model=list[SportResponse])
def list_sports(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[SportResponse]:
    sports = get_accessible_sports(db, user)
    return [
        SportResponse(
            id=sport.id,
            csv_name=sport.csv_name,
            display_name=sport.display_name,
            slug=sport.slug,
        )
        for sport in sports
    ]


@router.get("/terms", response_model=list[TermResponse])
def list_terms(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[TermResponse]:
    _ = user
    terms = list(
        db.scalars(select(Term).order_by(Term.start_date.desc(), Term.id.desc()))
    )
    return [
        TermResponse(
            id=term.id,
            academic_year=term.academic_year,
            semester=term.semester,
            start_date=term.start_date.isoformat() if term.start_date else None,
            end_date=term.end_date.isoformat() if term.end_date else None,
        )
        for term in terms
    ]


@router.get("/roster-availability", response_model=list[TermAvailabilityResponse])
def list_roster_availability(
    sport_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[TermAvailabilityResponse]:
    require_sport_access(sport_id, user)

    sport = db.get(Sport, sport_id)
    if sport is None:
        raise HTTPException(status_code=404, detail="Sport not found")

    rows = db.execute(
        select(
            Term.id,
            Term.academic_year,
            Term.semester,
            func.count(RosterMembership.id).label("athlete_count"),
        )
        .join(RosterMembership, RosterMembership.term_id == Term.id)
        .where(RosterMembership.sport_id == sport_id)
        .group_by(Term.id, Term.academic_year, Term.semester, Term.start_date)
        .order_by(Term.start_date.desc(), Term.id.desc())
    ).all()

    return [
        TermAvailabilityResponse(
            term_id=term_id,
            academic_year=academic_year,
            semester=semester,
            athlete_count=athlete_count,
        )
        for term_id, academic_year, semester, athlete_count in rows
    ]


@router.get("/rosters", response_model=list[RosterRowResponse])
def list_roster_rows(
    sport_id: int = Query(...),
    term_id: int = Query(...),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[RosterRowResponse]:
    require_sport_access(sport_id, user)

    sport = db.get(Sport, sport_id)
    term = db.get(Term, term_id)
    if sport is None or term is None:
        raise HTTPException(status_code=404, detail="Sport or term not found")

    query = (
        select(RosterMembership, AidRecord)
        .join(AidRecord, AidRecord.membership_id == RosterMembership.id, isouter=True)
        .join(Athlete, Athlete.rocket_id == RosterMembership.athlete_id)
        .options(joinedload(RosterMembership.athlete))
        .where(RosterMembership.sport_id == sport_id, RosterMembership.term_id == term_id)
        .order_by(RosterMembership.status, RosterMembership.athlete_id)
    )
    if search:
        like = f"%{search.strip()}%"
        query = query.where(
            or_(
                RosterMembership.athlete_id.ilike(like),
                Athlete.first_name.ilike(like),
                Athlete.last_name.ilike(like),
            )
        )

    rows = db.execute(query).all()
    membership_ids = [membership.id for membership, _aid in rows]
    pending_adjustment_map: dict[int, Adjustment] = {}
    pending_submission_source_map: dict[int, str | None] = {}
    if membership_ids:
        adjustments = db.scalars(
            select(Adjustment)
            .where(
                Adjustment.membership_id.in_(membership_ids),
                Adjustment.state == "SUBMITTED",
            )
            .order_by(Adjustment.created_at.desc())
        ).all()
        submission_ids = {
            adjustment.submission_id
            for adjustment in adjustments
            if adjustment.submission_id
        }
        submission_map = {}
        if submission_ids:
            submission_map = {
                submission.id: submission
                for submission in db.scalars(
                    select(Submission).where(Submission.id.in_(submission_ids))
                )
            }
        for adjustment in adjustments:
            if adjustment.membership_id not in pending_adjustment_map:
                pending_adjustment_map[adjustment.membership_id] = adjustment
                pending_submission_source_map[adjustment.membership_id] = (
                    submission_map.get(adjustment.submission_id).source
                    if adjustment.submission_id in submission_map
                    else None
                )

    response: list[RosterRowResponse] = []
    for membership, aid in rows:
        athlete = membership.athlete
        pending_adjustment = pending_adjustment_map.get(membership.id)
        response.append(
            RosterRowResponse(
                membership_id=membership.id,
                athlete_id=athlete.rocket_id,
                first_name=athlete.first_name,
                last_name=athlete.last_name,
                sport_id=sport.id,
                sport_name=sport.display_name,
                term_id=term.id,
                academic_year=term.academic_year,
                semester=term.semester,
                cohort_internal=membership.cohort_internal,
                cohort_display=membership.cohort_display,
                exempt=membership.exempt,
                housing=membership.housing,
                status=membership.status,
                athletic_aid_total=aid.athletic_aid_total if aid else 0,
                oos_tuition=aid.oos_tuition if aid else 0,
                tuition=aid.tuition if aid else 0,
                general_fee=aid.general_fee if aid else 0,
                misc_fee=aid.misc_fee if aid else 0,
                room=aid.room if aid else 0,
                board=aid.board if aid else 0,
                books=aid.books if aid else 0,
                personal_expenses=aid.personal_expenses if aid else 0,
                oos_resource=aid.oos_resource if aid else 0,
                merit_scholarship=aid.merit_scholarship if aid else 0,
                academic_aid=aid.academic_aid if aid else 0,
                coa_total=aid.coa_total if aid else 0,
                source=aid.source if aid else None,
                pending_state=pending_adjustment.state if pending_adjustment else None,
                pending_after_values=(
                    pending_adjustment.after_values if pending_adjustment else None
                ),
                pending_source=pending_submission_source_map.get(membership.id),
            )
        )

    return response


@router.get("/sport-budgets/summary", response_model=SportBudgetSummaryResponse)
def get_budget_summary(
    sport_id: int = Query(...),
    academic_year: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> SportBudgetSummaryResponse:
    require_sport_access(sport_id, user)
    summary = get_sport_budget_summary(
        db,
        sport_id=sport_id,
        academic_year=academic_year,
    )
    return SportBudgetSummaryResponse(
        sport_id=summary.sport_id,
        academic_year=summary.academic_year,
        budget_amount=summary.budget_amount,
        allocated_amount=summary.allocated_amount,
        percent_used=summary.percent_used,
    )
