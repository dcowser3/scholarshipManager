from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Athletic Scholarship Management System"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://scholarship:scholarship@localhost:5432/scholarship"
    secret_key: str = "change-me"
    frontend_origin: str = "http://localhost:5173"
    cookie_name: str = "athletic_session"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    storage_root: str = "storage"
    adjustment_template_path: str = "templates/Adjustment_of_Aid_Template_2526.xlsx"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "Athletic Scholarship MVP"
    smtp_use_starttls: bool = True
    smtp_use_ssl: bool = False
    tender_recommended_signatory: str = "Athletic Department Representative"
    tender_approved_signatory: str = "Financial Aid Representative"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def resolve_backend_path(value: str) -> Path:
    return (Path(__file__).resolve().parents[2] / value).resolve()
