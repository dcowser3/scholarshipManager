from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import record_audit_event, require_sport_access, require_user
from app.db.session import get_db
from app.models.core import Athlete, Sport, Term
from app.models.imports import ImportCohortIssue
from app.models.user import User
from app.schemas.cohort_issues import CohortIssueResponse, ResolveCohortIssueRequest
from app.services.importer import resolve_cohort_issue

router = APIRouter(prefix="/cohort-issues", tags=["cohort-issues"])


@router.get("", response_model=list[CohortIssueResponse])
def list_cohort_issues(
    sport_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[CohortIssueResponse]:
    require_sport_access(sport_id, user)
    sport = db.get(Sport, sport_id)
    if sport is None:
        raise HTTPException(status_code=404, detail="Sport not found")

    query = (
        select(ImportCohortIssue, Athlete)
        .join(Athlete, Athlete.rocket_id == ImportCohortIssue.athlete_id)
        .where(
            ImportCohortIssue.sport_id == sport_id,
            ImportCohortIssue.status == "PENDING",
        )
        .order_by(Athlete.last_name, Athlete.first_name, Athlete.rocket_id)
    )
    rows = db.execute(query).all()
    return [
        CohortIssueResponse(
            id=issue.id,
            athlete_id=athlete.rocket_id,
            athlete_name=f"{athlete.first_name} {athlete.last_name}",
            sport_id=sport.id,
            sport_name=sport.display_name,
            source_cohort=issue.source_cohort,
            status=issue.status,
            resolved_cohort_display=issue.resolved_cohort_display,
            has_saved_override=bool(
                athlete.cohort_override_internal and athlete.cohort_override_display
            ),
        )
        for issue, athlete in rows
    ]


@router.post("/{issue_id}/resolve", response_model=CohortIssueResponse)
def resolve_issue(
    issue_id: int,
    payload: ResolveCohortIssueRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> CohortIssueResponse:
    issue = db.get(ImportCohortIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Cohort issue not found")

    require_sport_access(issue.sport_id, user)
    valid_years = set(db.scalars(select(Term.academic_year).distinct()))
    if payload.academic_year not in valid_years:
        raise HTTPException(status_code=400, detail="Academic year is not configured")

    resolved_issue = resolve_cohort_issue(
        db,
        issue=issue,
        academic_year=payload.academic_year,
        resolved_by=user,
    )
    athlete = db.get(Athlete, resolved_issue.athlete_id)
    sport = db.get(Sport, resolved_issue.sport_id)
    record_audit_event(
        db,
        user_id=user.id,
        action="RESOLVE_COHORT_ISSUE",
        entity_type="import_cohort_issue",
        entity_id=str(resolved_issue.id),
        request=request,
        after={
            "athlete_id": resolved_issue.athlete_id,
            "sport_id": resolved_issue.sport_id,
            "academic_year": payload.academic_year,
        },
    )
    db.commit()

    if athlete is None or sport is None:
        raise HTTPException(status_code=500, detail="Resolved issue is missing related data")

    return CohortIssueResponse(
        id=resolved_issue.id,
        athlete_id=athlete.rocket_id,
        athlete_name=f"{athlete.first_name} {athlete.last_name}",
        sport_id=sport.id,
        sport_name=sport.display_name,
        source_cohort=resolved_issue.source_cohort,
        status=resolved_issue.status,
        resolved_cohort_display=resolved_issue.resolved_cohort_display,
        has_saved_override=bool(
            athlete.cohort_override_internal and athlete.cohort_override_display
        ),
    )

