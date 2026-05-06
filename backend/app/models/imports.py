from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    source_filename: Mapped[str | None] = mapped_column(Text)
    rows_processed: Mapped[int | None] = mapped_column(Integer)
    rows_changed: Mapped[int | None] = mapped_column(Integer)
    duplicates_dropped: Mapped[int | None] = mapped_column(Integer)
    error_log: Mapped[dict | None] = mapped_column(JSONB)


class ImportDiff(Base):
    __tablename__ = "import_diffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_run_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id"), nullable=False)
    athlete_id: Mapped[str | None] = mapped_column(Text)
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id"))
    field: Mapped[str | None] = mapped_column(Text)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)


class ImportCohortIssue(Base):
    __tablename__ = "import_cohort_issues"
    __table_args__ = (
        UniqueConstraint("athlete_id", "sport_id", name="uq_import_cohort_issue_athlete_sport"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_run_id: Mapped[int | None] = mapped_column(ForeignKey("import_runs.id"))
    athlete_id: Mapped[str] = mapped_column(ForeignKey("athletes.rocket_id"), nullable=False)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"), nullable=False)
    source_cohort: Mapped[str | None] = mapped_column(Text)
    source_row: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="PENDING", nullable=False)
    resolved_cohort_display: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
