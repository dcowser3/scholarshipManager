from __future__ import annotations

from app.db.session import SessionLocal
from app.services.budgets import upsert_mock_budgets_for_academic_year
from app.services.importer import get_active_import_academic_year


def main() -> None:
    with SessionLocal() as db:
        academic_year = get_active_import_academic_year(db)
        updated = upsert_mock_budgets_for_academic_year(db, academic_year=academic_year)
        db.commit()
    print(f"Seeded or updated {updated} sport budgets for {academic_year}.")


if __name__ == "__main__":
    main()
