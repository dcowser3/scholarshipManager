from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.user import User


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

