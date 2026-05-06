from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User
from app.services.importer import import_csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Import athletic aid CSV data.")
    parser.add_argument("csv_path", help="Path to the source CSV file")
    parser.add_argument("--user-email", help="Optional user email to attribute the import to")
    args = parser.parse_args()

    with SessionLocal() as db:
        imported_by = None
        if args.user_email:
            imported_by = db.scalar(select(User).where(User.email == args.user_email))

        summary = import_csv_path(db, args.csv_path, imported_by=imported_by)
        db.commit()
        print(
            {
                "rows_processed": summary.rows_processed,
                "rows_changed": summary.rows_changed,
                "duplicates_dropped": summary.duplicates_dropped,
                "error_log": summary.error_log,
            }
        )


if __name__ == "__main__":
    main()

