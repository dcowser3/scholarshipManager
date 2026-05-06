from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.core import ConfigEntry, Sport, Term
from app.models.user import User, UserSportAccess
from app.services.importer import slugify_sport_name

DEFAULT_SPORTS = [
    "Baseball",
    "Cheerleading",
    "Football",
    "Mens Basketball",
    "Mens Cross Country",
    "Mens Golf",
    "Mens Tennis",
    "Softball",
    "Volleyball",
    "Womens Basketball",
    "Womens Cross Country",
    "Womens Golf",
    "Womens Rowing",
    "Womens Soccer",
    "Womens Swimming",
    "Womens Tennis",
    "Womens Track",
]

DEFAULT_TERMS = [
    ("22-23", "FALL", date(2022, 8, 22), date(2022, 12, 17)),
    ("22-23", "SPRING", date(2023, 1, 9), date(2023, 5, 7)),
    ("23-24", "FALL", date(2023, 8, 21), date(2023, 12, 16)),
    ("23-24", "SPRING", date(2024, 1, 8), date(2024, 5, 5)),
    ("24-25", "FALL", date(2024, 8, 26), date(2024, 12, 21)),
    ("24-25", "SPRING", date(2025, 1, 6), date(2025, 5, 11)),
    ("25-26", "FALL", date(2025, 8, 25), date(2025, 12, 20)),
    ("25-26", "SPRING", date(2026, 1, 5), date(2026, 5, 10)),
    ("26-27", "FALL", date(2026, 8, 24), date(2026, 12, 19)),
    ("26-27", "SPRING", date(2027, 1, 4), date(2027, 5, 9)),
]

DEFAULT_USERS = [
    {
        "email": "admin@utoledo.edu",
        "display_name": "Scholarship Admin",
        "password": "ChangeMe123!",
        "is_admin": True,
        "sports": [],
    },
    {
        "email": "football.coach@utoledo.edu",
        "display_name": "Football Coach",
        "password": "ChangeMe123!",
        "is_admin": False,
        "sports": [("Football", "HEAD_COACH")],
    },
    {
        "email": "softball.coach@utoledo.edu",
        "display_name": "Softball Coach",
        "password": "ChangeMe123!",
        "is_admin": False,
        "sports": [("Softball", "HEAD_COACH")],
    },
]


def seed_sports() -> None:
    with SessionLocal() as db:
        existing = {sport.csv_name for sport in db.scalars(select(Sport))}
        for order, csv_name in enumerate(DEFAULT_SPORTS, start=1):
            if csv_name in existing:
                continue
            db.add(
                Sport(
                    csv_name=csv_name,
                    display_name=csv_name,
                    slug=slugify_sport_name(csv_name),
                    display_order=order,
                )
            )
        db.commit()


def seed_terms() -> None:
    with SessionLocal() as db:
        existing = {(term.academic_year, term.semester) for term in db.scalars(select(Term))}
        for academic_year, semester, start_date, end_date in DEFAULT_TERMS:
            if (academic_year, semester) in existing:
                continue
            db.add(
                Term(
                    academic_year=academic_year,
                    semester=semester,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
        db.commit()


def seed_config() -> None:
    with SessionLocal() as db:
        for key, value in {
            "tender_recommended_signatory": "Henry Davidson",
            "tender_approved_signatory": "Korrin Lovette",
            "active_roster_academic_year": "25-26",
        }.items():
            entry = db.get(ConfigEntry, key)
            if entry is None:
                db.add(ConfigEntry(key=key, value=value))
        db.commit()


def seed_users() -> None:
    with SessionLocal() as db:
        sports = {sport.csv_name: sport for sport in db.scalars(select(Sport))}
        for user_data in DEFAULT_USERS:
            user = db.scalar(select(User).where(User.email == user_data["email"]))
            if user is None:
                user = User(
                    email=user_data["email"],
                    display_name=user_data["display_name"],
                    password_hash=hash_password(user_data["password"]),
                    is_admin=user_data["is_admin"],
                )
                db.add(user)
                db.flush()

            for sport_name, role in user_data["sports"]:
                sport = sports.get(sport_name)
                if sport is None:
                    continue
                existing = db.get(UserSportAccess, {"user_id": user.id, "sport_id": sport.id})
                if existing is None:
                    db.add(UserSportAccess(user_id=user.id, sport_id=sport.id, role=role))
        db.commit()


def main() -> None:
    seed_sports()
    seed_terms()
    seed_config()
    seed_users()
    print("Seeded sports, terms, config, and users.")


if __name__ == "__main__":
    main()
