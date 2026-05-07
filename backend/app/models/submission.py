from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sport_id: Mapped[int | None] = mapped_column(ForeignKey("sports.id"))
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(16), default="UI", nullable=False)
    intake_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("email_intake.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(32))
    kind: Mapped[str | None] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Adjustment(Base):
    __tablename__ = "adjustments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"))
    membership_id: Mapped[int | None] = mapped_column(ForeignKey("roster_memberships.id"))
    athlete_id: Mapped[str | None] = mapped_column(ForeignKey("athletes.rocket_id"))
    type: Mapped[str | None] = mapped_column(String(32))
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id"))
    before_values: Mapped[dict | None] = mapped_column(JSONB)
    after_values: Mapped[dict | None] = mapped_column(JSONB)
    state: Mapped[str | None] = mapped_column(String(32))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentArtifact(Base):
    __tablename__ = "document_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"))
    kind: Mapped[str | None] = mapped_column(String(32))
    athlete_id: Mapped[str | None] = mapped_column(ForeignKey("athletes.rocket_id"))
    filename: Mapped[str | None] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    send_status: Mapped[str | None] = mapped_column(String(32))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_to: Mapped[str | None] = mapped_column(Text)


class EmailIntake(Base):
    __tablename__ = "email_intake"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sender_email: Mapped[str | None] = mapped_column(Text)
    inbound_message_id: Mapped[str | None] = mapped_column(Text, unique=True)
    raw_body: Mapped[str | None] = mapped_column(Text)
    parsed_payload: Mapped[dict | None] = mapped_column(JSONB)
    confirmation_message_id: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(String(32))
    submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
