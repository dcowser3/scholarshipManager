from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path

from app.core.config import settings


class EmailConfigurationError(RuntimeError):
    pass


def _validate_smtp_settings() -> None:
    required = {
        "SMTP_HOST": settings.smtp_host,
        "SMTP_FROM_EMAIL": settings.smtp_from_email,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise EmailConfigurationError(
            "SMTP is not configured. Add "
            + ", ".join(missing)
            + " in backend/.env before sending real email."
        )


def send_email_with_attachments(
    *,
    recipient_email: str,
    subject: str,
    body: str,
    attachments: list[Path],
) -> None:
    _validate_smtp_settings()

    message = EmailMessage()
    message["From"] = (
        f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        if settings.smtp_from_name
        else settings.smtp_from_email
    )
    message["To"] = recipient_email
    message["Subject"] = subject
    message.set_content(body)

    for attachment in attachments:
        message.add_attachment(
            attachment.read_bytes(),
            maintype="application",
            subtype=_subtype_for_attachment(attachment),
            filename=attachment.name,
        )

    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
            _login_if_needed(server)
            server.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_use_starttls:
            server.starttls()
        _login_if_needed(server)
        server.send_message(message)


def _login_if_needed(server: smtplib.SMTP) -> None:
    if settings.smtp_username and settings.smtp_password:
        server.login(settings.smtp_username, settings.smtp_password)


def _subtype_for_attachment(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".xlsx":
        return "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "octet-stream"
