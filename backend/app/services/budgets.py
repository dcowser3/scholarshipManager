from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import SportBudget, Term
from app.models.roster import AidRecord, RosterMembership


@dataclass
class SportBudgetSummary:
    sport_id: int
    academic_year: str
    budget_amount: Decimal
    allocated_amount: Decimal
    percent_used: Decimal


def get_sport_budget_summary(
    db: Session,
    *,
    sport_id: int,
    academic_year: str,
    athletic_aid_overrides: dict[int, Decimal] | None = None,
) -> SportBudgetSummary:
    athletic_aid_overrides = athletic_aid_overrides or {}
    budget = db.scalar(
        select(SportBudget).where(
            SportBudget.sport_id == sport_id,
            SportBudget.academic_year == academic_year,
        )
    )
    budget_amount = budget.budget_amount if budget else Decimal("0.00")
    allocated_amount = Decimal("0.00")

    rows = db.execute(
        select(RosterMembership.id, AidRecord.athletic_aid_total)
        .join(AidRecord, AidRecord.membership_id == RosterMembership.id)
        .join(Term, Term.id == RosterMembership.term_id)
        .where(
            RosterMembership.sport_id == sport_id,
            Term.academic_year == academic_year,
        )
    ).all()
    for membership_id, athletic_aid_total in rows:
        allocated_amount += athletic_aid_overrides.get(membership_id, athletic_aid_total)

    percent_used = Decimal("0.00")
    if budget_amount > 0:
        percent_used = (allocated_amount / budget_amount * Decimal("100")).quantize(
            Decimal("0.01")
        )

    return SportBudgetSummary(
        sport_id=sport_id,
        academic_year=academic_year,
        budget_amount=budget_amount,
        allocated_amount=allocated_amount.quantize(Decimal("0.01")),
        percent_used=percent_used,
    )


def upsert_mock_budgets_for_academic_year(
    db: Session,
    *,
    academic_year: str,
) -> int:
    sport_ids = list(
        db.scalars(
            select(RosterMembership.sport_id)
            .join(Term, Term.id == RosterMembership.term_id)
            .where(Term.academic_year == academic_year)
            .distinct()
        )
    )
    updated = 0
    for sport_id in sport_ids:
        summary = get_sport_budget_summary(db, sport_id=sport_id, academic_year=academic_year)
        budget_amount = (summary.allocated_amount * Decimal("1.25")).quantize(Decimal("0.01"))
        existing = db.scalar(
            select(SportBudget).where(
                SportBudget.sport_id == sport_id,
                SportBudget.academic_year == academic_year,
            )
        )
        if existing is None:
            db.add(
                SportBudget(
                    sport_id=sport_id,
                    academic_year=academic_year,
                    budget_amount=budget_amount,
                    notes="Demo-seeded at 1.25x current allocation.",
                )
            )
        else:
            existing.budget_amount = budget_amount
            existing.notes = "Demo-seeded at 1.25x current allocation."
        updated += 1
    return updated
