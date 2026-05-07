from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.roster import AidRecord, RosterMembership
from app.models.submission import Adjustment, DocumentArtifact, Submission
from app.services.documents import GeneratedArtifact, generate_adjustment_artifacts

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


@dataclass
class PreparedSubmissionChange:
    membership_id: int
    after_values: dict[str, str]


@dataclass
class SubmissionWorkflowResult:
    submission: Submission
    adjustments: list[Adjustment]


def serialize_editable_values(aid_record: AidRecord) -> dict[str, str]:
    return {field: str(getattr(aid_record, field)) for field in AID_EDITABLE_FIELDS}


def create_submission_with_adjustments(
    *,
    db: Session,
    sport_id: int,
    submitted_by_user_id: int | None,
    source: str,
    comment: str | None,
    changes: list[PreparedSubmissionChange],
    intake_id: UUID | None = None,
) -> SubmissionWorkflowResult:
    if not changes:
        raise ValueError("At least one change is required")

    membership_ids = [change.membership_id for change in changes]
    memberships = db.scalars(
        select(RosterMembership).where(RosterMembership.id.in_(membership_ids))
    ).all()
    membership_map = {membership.id: membership for membership in memberships}

    if len(membership_map) != len(set(membership_ids)):
        raise ValueError("One or more roster memberships were not found")

    for membership in memberships:
        if membership.sport_id != sport_id:
            raise ValueError("Cannot submit changes for another sport")

    submission = Submission(
        sport_id=sport_id,
        submitted_by=submitted_by_user_id,
        source=source,
        intake_id=intake_id,
        submitted_at=datetime.now(UTC),
        status="SUBMITTED",
        kind="ADJUSTMENT",
        comment=comment,
    )
    db.add(submission)
    db.flush()

    created_records: list[Adjustment] = []
    for change in changes:
        membership = membership_map[change.membership_id]
        aid_record = db.scalar(select(AidRecord).where(AidRecord.membership_id == membership.id))
        if aid_record is None:
            raise ValueError(f"Membership {membership.id} is missing its aid record")

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
            field: str(Decimal(change.after_values[field]).quantize(Decimal("0.01")))
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

    if not created_records:
        raise ValueError("No changes differed from current roster values")

    for adjustment in created_records:
        db.add(adjustment)

    db.flush()
    return SubmissionWorkflowResult(submission=submission, adjustments=created_records)


def generate_submission_artifacts(
    *,
    db: Session,
    submission: Submission,
    adjustments: list[Adjustment],
    submitted_by_name: str | None,
    comment: str | None,
) -> list[GeneratedArtifact]:
    return generate_adjustment_artifacts(
        db=db,
        submission_id=submission.id,
        adjustments=adjustments,
        submitted_by_name=submitted_by_name,
        comment=comment,
    )


def persist_generated_artifacts(
    *,
    db: Session,
    submission_id: UUID,
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
