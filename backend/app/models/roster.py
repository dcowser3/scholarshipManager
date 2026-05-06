from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RosterMembership(Base):
    __tablename__ = "roster_memberships"
    __table_args__ = (
        UniqueConstraint(
            "athlete_id",
            "sport_id",
            "term_id",
            name="uq_membership_athlete_sport_term",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[str] = mapped_column(ForeignKey("athletes.rocket_id"), nullable=False)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"), nullable=False)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id"), nullable=False)
    cohort_internal: Mapped[str | None] = mapped_column(Text)
    cohort_display: Mapped[str | None] = mapped_column(String(16))
    exempt: Mapped[bool | None] = mapped_column(Boolean)
    housing: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    athlete = relationship("Athlete", back_populates="memberships")
    sport = relationship("Sport", back_populates="memberships")
    term = relationship("Term", back_populates="memberships")
    aid_record = relationship("AidRecord", back_populates="membership", uselist=False)


class AidRecord(Base):
    __tablename__ = "aid_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    membership_id: Mapped[int] = mapped_column(
        ForeignKey("roster_memberships.id"), nullable=False, unique=True
    )
    oos_tuition: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    tuition: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    general_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    misc_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    room: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    board: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    books: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    personal_expenses: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    athletic_aid_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    oos_resource: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    merit_scholarship: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    academic_aid: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    coa_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(String(32))

    membership = relationship("RosterMembership", back_populates="aid_record")
