from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.security import unsign_session
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.core import Sport
from app.models.user import User, UserSportAccess


def require_user(
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=settings.cookie_name),
) -> User:
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user_id = unsign_session(session_token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    user = db.scalar(
        select(User)
        .options(joinedload(User.sports).joinedload(UserSportAccess.sport))
        .where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    request.state.current_user = user
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_sport_access(
    sport_id: int,
    user: User,
) -> None:
    if user.is_admin:
        return
    if not any(access.sport_id == sport_id for access in user.sports):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sport access denied")


def record_audit_event(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str,
    request: Request | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    ip_address = request.client.host if request and request.client else None
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
            ip_address=ip_address,
        )
    )


def get_accessible_sports(db: Session, user: User) -> list[Sport]:
    if user.is_admin:
        return list(
            db.scalars(
                select(Sport)
                .where(Sport.is_active.is_(True))
                .order_by(Sport.display_order, Sport.id)
            )
        )

    sport_ids = [assignment.sport_id for assignment in user.sports]
    if not sport_ids:
        return []
    return list(
        db.scalars(
            select(Sport)
            .where(Sport.id.in_(sport_ids), Sport.is_active.is_(True))
            .order_by(Sport.display_order, Sport.id)
        )
    )
