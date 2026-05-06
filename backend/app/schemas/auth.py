from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthUserSport(BaseModel):
    sport_id: int
    sport_name: str
    role: str | None


class AuthUserResponse(BaseModel):
    id: int
    email: EmailStr
    display_name: str | None
    is_admin: bool
    sports: list[AuthUserSport]

