from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Athlete(Base):
    __tablename__ = "athletes"

    rocket_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    cohort_override_internal: Mapped[str | None] = mapped_column(Text)
    cohort_override_display: Mapped[str | None] = mapped_column(String(16))
    cohort_override_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    memberships = relationship("RosterMembership", back_populates="athlete")


class Sport(Base):
    __tablename__ = "sports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    csv_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    is_headcount: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int | None] = mapped_column(Integer)

    memberships = relationship("RosterMembership", back_populates="sport")
    access_assignments = relationship("UserSportAccess", back_populates="sport")


class Term(Base):
    __tablename__ = "terms"
    __table_args__ = (UniqueConstraint("academic_year", "semester", name="uq_terms_year_semester"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_year: Mapped[str] = mapped_column(String(16), nullable=False)
    semester: Mapped[str] = mapped_column(String(16), nullable=False)
    start_date: Mapped[Date | None] = mapped_column(Date)
    end_date: Mapped[Date | None] = mapped_column(Date)

    memberships = relationship("RosterMembership", back_populates="term")


class ConfigEntry(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
