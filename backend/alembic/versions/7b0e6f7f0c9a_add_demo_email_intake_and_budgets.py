"""add demo email intake and budgets

Revision ID: 7b0e6f7f0c9a
Revises: 1e8c4a9f6b21
Create Date: 2026-05-07 14:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "7b0e6f7f0c9a"
down_revision = "1e8c4a9f6b21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sport_budgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sport_id", sa.Integer(), nullable=False),
        sa.Column("academic_year", sa.String(length=16), nullable=False),
        sa.Column("budget_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["sport_id"], ["sports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sport_id", "academic_year", name="uq_sport_budgets_sport_year"),
    )

    op.create_table(
        "email_intake",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sender_email", sa.Text(), nullable=True),
        sa.Column("inbound_message_id", sa.Text(), nullable=True),
        sa.Column("raw_body", sa.Text(), nullable=True),
        sa.Column("parsed_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confirmation_message_id", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inbound_message_id"),
    )

    op.add_column(
        "submissions",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="UI"),
    )
    op.add_column("submissions", sa.Column("intake_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_submissions_intake_id_email_intake",
        "submissions",
        "email_intake",
        ["intake_id"],
        ["id"],
    )
    op.alter_column("submissions", "source", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_submissions_intake_id_email_intake", "submissions", type_="foreignkey")
    op.drop_column("submissions", "intake_id")
    op.drop_column("submissions", "source")
    op.drop_table("email_intake")
    op.drop_table("sport_budgets")
