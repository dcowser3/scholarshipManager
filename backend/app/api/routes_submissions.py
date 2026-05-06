from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    record_audit_event,
    require_sport_access,
    require_user,
)
from app.db.session import get_db
from app.models.roster import AidRecord, RosterMembership
from app.models.submission import Adjustment, DocumentArtifact, Submission
from app.models.user import User
from app.schemas.submissions import SubmitAdjustmentsRequest, SubmittedAdjustmentResponse
from app.services.documents import GeneratedArtifact, generate_adjustment_artifacts
from app.services.emailer import EmailConfigurationError, send_email_with_attachments

router = APIRouter(prefix="/submissions", tags=["submissions"])

AID_EDITABLE_FIELDS = [
    "athletic_aid_total",
    "oos_tuition",
    "tuition",
    "general_fee",
    "misc_fee",
    "room",
    "board",
    "books",
    "personal_expenses",
    "oos_resource",
]


def serialize_editable_values(aid_record: AidRecord) -> dict[str, str]:
    return {field: str(getattr(aid_record, field)) for field in AID_EDITABLE_FIELDS}


@router.post("/adjustments", response_model=SubmittedAdjustmentResponse)
def submit_adjustments(
    payload: SubmitAdjustmentsRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> SubmittedAdjustmentResponse:
    require_sport_access(payload.sport_id, user)

    if not payload.changes:
        raise HTTPException(status_code=400, detail="At least one change is required")

    membership_ids = [change.membership_id for change in payload.changes]
    memberships = db.scalars(
        select(RosterMembership).where(RosterMembership.id.in_(membership_ids))
    ).all()
    membership_map = {membership.id: membership for membership in memberships}

    if len(membership_map) != len(set(membership_ids)):
        raise HTTPException(status_code=404, detail="One or more roster memberships were not found")

    for membership in memberships:
        if membership.sport_id != payload.sport_id:
            raise HTTPException(status_code=403, detail="Cannot submit changes for another sport")

    submission = Submission(
        sport_id=payload.sport_id,
        submitted_by=user.id,
        submitted_at=datetime.now(UTC),
        status="SUBMITTED",
        kind="ADJUSTMENT",
        comment=payload.comment,
    )
    db.add(submission)
    db.flush()

    created_records: list[Adjustment] = []
    created_adjustments = 0
    for change in payload.changes:
        membership = membership_map[change.membership_id]
        aid_record = db.scalar(select(AidRecord).where(AidRecord.membership_id == membership.id))
        if aid_record is None:
            raise HTTPException(
                status_code=400,
                detail=f"Membership {membership.id} is missing its aid record",
            )

        existing_active = db.scalars(
            select(Adjustment).where(
                Adjustment.membership_id == membership.id,
                Adjustment.state == "SUBMITTED",
            )
        ).all()
        for prior in existing_active:
            prior.state = "SUPERSEDED"

        before_values = serialize_editable_values(aid_record)
        after_values = {
            field: str(Decimal(getattr(change.after_values, field)).quantize(Decimal("0.01")))
            for field in AID_EDITABLE_FIELDS
        }

        if before_values == after_values:
            continue

        created_records.append(
            Adjustment(
                submission_id=submission.id,
                membership_id=membership.id,
                athlete_id=membership.athlete_id,
                type="AID_CHANGE",
                term_id=membership.term_id,
                before_values=before_values,
                after_values=after_values,
                state="SUBMITTED",
                created_at=datetime.now(UTC),
            )
        )
        created_adjustments += 1

    for adjustment in created_records:
        db.add(adjustment)

    db.flush()

    if created_adjustments == 0:
        raise HTTPException(
            status_code=400,
            detail="No changes differed from current roster values",
        )

    generated_artifacts = generate_adjustment_artifacts(
        db=db,
        submission_id=submission.id,
        adjustments=created_records,
        submitted_by=user,
        comment=payload.comment,
    )

    try:
        send_email_with_attachments(
            recipient_email=str(payload.recipient_email),
            subject=f"Athletic aid adjustment submission - {submission.id}",
            body=build_email_body(
                user_name=user.display_name or user.email,
                comment=payload.comment,
                adjustments_created=created_adjustments,
            ),
            attachments=[artifact.path for artifact in generated_artifacts],
        )
    except EmailConfigurationError as caught:
        raise HTTPException(status_code=500, detail=str(caught)) from caught
    except Exception as caught:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=f"Email send failed: {caught}") from caught

    persist_generated_artifacts(
        db=db,
        submission_id=submission.id,
        recipient_email=str(payload.recipient_email),
        generated_artifacts=generated_artifacts,
    )

    record_audit_event(
        db,
        user_id=user.id,
        action="SUBMIT_ADJUSTMENTS",
        entity_type="submission",
        entity_id=str(submission.id),
        request=request,
        after={
            "submission_id": str(submission.id),
            "sport_id": payload.sport_id,
            "adjustments_created": created_adjustments,
            "recipient_email": str(payload.recipient_email),
            "artifacts_created": len(generated_artifacts),
        },
    )
    db.commit()
    return SubmittedAdjustmentResponse(
        submission_id=submission.id,
        adjustments_created=created_adjustments,
        artifacts_created=len(generated_artifacts),
        recipient_email=payload.recipient_email,
    )


def persist_generated_artifacts(
    *,
    db: Session,
    submission_id,
    recipient_email: str,
    generated_artifacts: list[GeneratedArtifact],
) -> None:
    for artifact in generated_artifacts:
        db.add(
            DocumentArtifact(
                submission_id=submission_id,
                kind=artifact.kind,
                athlete_id=artifact.athlete_id,
                filename=artifact.filename,
                storage_path=str(Path(artifact.path)),
                generated_at=datetime.now(UTC),
                send_status="SENT",
                sent_at=datetime.now(UTC),
                sent_to=recipient_email,
            )
        )


def build_email_body(*, user_name: str, comment: str | None, adjustments_created: int) -> str:
    lines = [
        "This email was generated by the Athletic Scholarship Management MVP.",
        "",
        f"Submitted by: {user_name}",
        f"Adjustments included: {adjustments_created}",
    ]
    if comment:
        lines.extend(["", "Submission note:", comment])
    lines.extend(
        [
            "",
            "Attachments:",
            "- Adjustment of Aid workbook(s)",
            "- Tender PDF(s)",
        ]
    )
    return "\n".join(lines)
