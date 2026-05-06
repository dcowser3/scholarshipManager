from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sports = relationship("UserSportAccess", back_populates="user")


class UserSportAccess(Base):
    __tablename__ = "user_sport_access"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"), primary_key=True)
    role: Mapped[str | None] = mapped_column(String(32))

    user = relationship("User", back_populates="sports")
    sport = relationship("Sport", back_populates="access_assignments")

