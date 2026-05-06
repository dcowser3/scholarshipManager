from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import record_audit_event, require_user
from app.core.config import settings
from app.core.security import sign_session
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AuthUserResponse, AuthUserSport, LoginRequest
from app.services.auth import authenticate_user

router = APIRouter(prefix="/auth", tags=["auth"])


def serialize_user(user: User) -> AuthUserResponse:
    sports = [
        AuthUserSport(
            sport_id=assignment.sport_id,
            sport_name=assignment.sport.display_name if assignment.sport else "",
            role=assignment.role,
        )
        for assignment in user.sports
    ]
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        sports=sports,
    )


@router.post("/login", response_model=AuthUserResponse)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthUserResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    response.set_cookie(
        key=settings.cookie_name,
        value=sign_session(user.id),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=60 * 60 * 24 * 7,
    )
    record_audit_event(
        db,
        user_id=user.id,
        action="LOGIN",
        entity_type="user",
        entity_id=str(user.id),
        request=request,
        after={"email": user.email},
    )
    db.commit()
    return serialize_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(settings.cookie_name)
    return response


@router.get("/me", response_model=AuthUserResponse)
def me(user: User = Depends(require_user)) -> AuthUserResponse:
    return serialize_user(user)
