"""add cohort overrides and issue queue

Revision ID: 1e8c4a9f6b21
Revises: 012679c40075
Create Date: 2026-05-06 15:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "1e8c4a9f6b21"
down_revision = "012679c40075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athletes", sa.Column("cohort_override_internal", sa.Text(), nullable=True))
    op.add_column(
        "athletes", sa.Column("cohort_override_display", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "athletes",
        sa.Column("cohort_override_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "import_cohort_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("import_run_id", sa.Integer(), nullable=True),
        sa.Column("athlete_id", sa.String(length=32), nullable=False),
        sa.Column("sport_id", sa.Integer(), nullable=False),
        sa.Column("source_cohort", sa.Text(), nullable=True),
        sa.Column("source_row", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("resolved_cohort_display", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.rocket_id"]),
        sa.ForeignKeyConstraint(["import_run_id"], ["import_runs.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["sport_id"], ["sports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("athlete_id", "sport_id", name="uq_import_cohort_issue_athlete_sport"),
    )


def downgrade() -> None:
    op.drop_table("import_cohort_issues")
    op.drop_column("athletes", "cohort_override_updated_at")
    op.drop_column("athletes", "cohort_override_display")
    op.drop_column("athletes", "cohort_override_internal")
