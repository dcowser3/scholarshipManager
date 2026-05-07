from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from app.core.config import settings


class EmailConfigurationError(RuntimeError):
    pass


def send_email_with_attachments(
    *,
    recipient_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    attachments: list[Path],
    in_reply_to: str | None = None,
    references: list[str] | None = None,
) -> str:
    return send_email(
        recipient_email=recipient_email,
        subject=subject,
        body=body,
        html_body=html_body,
        attachments=attachments,
        in_reply_to=in_reply_to,
        references=references,
    )


def send_plain_text_email(
    *,
    recipient_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    in_reply_to: str | None = None,
    references: list[str] | None = None,
) -> str:
    return send_email(
        recipient_email=recipient_email,
        subject=subject,
        body=body,
        html_body=html_body,
        attachments=[],
        in_reply_to=in_reply_to,
        references=references,
    )


def send_email(
    *,
    recipient_email: str,
    subject: str,
    body: str,
    html_body: str | None,
    attachments: list[Path],
    in_reply_to: str | None = None,
    references: list[str] | None = None,
) -> str:
    config = _resolved_smtp_settings()
    _validate_smtp_settings(config)

    message = EmailMessage()
    message_id = make_msgid()
    message["From"] = (
        f"{settings.smtp_from_name} <{config['from_email']}>"
        if settings.smtp_from_name
        else config["from_email"]
    )
    message["To"] = recipient_email
    message["Subject"] = subject
    message["Message-ID"] = message_id
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = " ".join(references)
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    for attachment in attachments:
        message.add_attachment(
            attachment.read_bytes(),
            maintype="application",
            subtype=_subtype_for_attachment(attachment),
            filename=attachment.name,
        )

    if config["use_ssl"]:
        with smtplib.SMTP_SSL(config["host"], config["port"]) as server:
            _login_if_needed(server, username=config["username"], password=config["password"])
            server.send_message(message)
        return message_id

    with smtplib.SMTP(config["host"], config["port"]) as server:
        if config["use_starttls"]:
            server.starttls()
        _login_if_needed(server, username=config["username"], password=config["password"])
        server.send_message(message)
    return message_id


def _resolved_smtp_settings() -> dict[str, object]:
    host = settings.smtp_host
    port = settings.smtp_port
    username = settings.smtp_username
    password = settings.smtp_password
    from_email = settings.smtp_from_email
    use_starttls = settings.smtp_use_starttls
    use_ssl = settings.smtp_use_ssl

    if not host and settings.email_imap_user and settings.email_imap_password:
        if settings.email_imap_host and "gmail" in settings.email_imap_host.lower():
            host = "smtp.gmail.com"
        username = username or settings.email_imap_user
        password = password or settings.email_imap_password
        from_email = from_email or settings.email_from_address or settings.email_imap_user
        use_starttls = True
        use_ssl = False

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "from_email": from_email,
        "use_starttls": use_starttls,
        "use_ssl": use_ssl,
    }


def _validate_smtp_settings(config: dict[str, object]) -> None:
    required = {
        "SMTP_HOST": config["host"],
        "SMTP_FROM_EMAIL": config["from_email"],
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise EmailConfigurationError(
            "SMTP is not configured. Add "
            + ", ".join(missing)
            + " in backend/.env before sending real email."
        )


def _login_if_needed(
    server: smtplib.SMTP,
    *,
    username: str | None,
    password: str | None,
) -> None:
    if username and password:
        server.login(username, password)


def _subtype_for_attachment(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".xlsx":
        return "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "octet-stream"
