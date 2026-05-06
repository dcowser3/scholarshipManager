from __future__ import annotations

from argon2 import PasswordHasher
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except Exception:
        return False


def build_session_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="auth-session")


def sign_session(user_id: int) -> str:
    return build_session_serializer().dumps({"user_id": user_id})


def unsign_session(token: str, max_age_seconds: int = 60 * 60 * 24 * 7) -> int | None:
    try:
        payload = build_session_serializer().loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    return int(payload["user_id"])

