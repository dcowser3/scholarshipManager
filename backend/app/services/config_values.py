from __future__ import annotations

import json
from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.core import ConfigEntry

CONFIG_KEY_TO_SETTING_ATTR = {
    "email.imap_host": "email_imap_host",
    "email.imap_user": "email_imap_user",
    "email.imap_password": "email_imap_password",
    "email.allowed_senders": "email_allowed_senders",
    "email.sender_sports": "email_sender_sports",
    "email.demo_recipient": "email_demo_recipient",
    "email.from_address": "email_from_address",
    "openai.api_key": "openai_api_key",
    "openai.model": "openai_model",
}


def get_config_value(db: Session, key: str) -> str | None:
    entry = db.get(ConfigEntry, key)
    if entry and entry.value is not None and entry.value.strip():
        return entry.value.strip()

    setting_name = CONFIG_KEY_TO_SETTING_ATTR.get(key)
    if not setting_name:
        return None
    value = getattr(settings, setting_name, None)
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def get_allowed_senders(db: Session) -> set[str]:
    raw = get_config_value(db, "email.allowed_senders")
    if not raw:
        return set()
    return {entry.strip().lower() for entry in raw.split(",") if entry.strip()}


def get_sender_sport_map(db: Session) -> dict[str, str]:
    raw = get_config_value(db, "email.sender_sports")
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, Mapping):
        raise ValueError("email.sender_sports must be a JSON object")
    return {
        str(sender).strip().lower(): str(sport).strip()
        for sender, sport in parsed.items()
        if str(sender).strip() and str(sport).strip()
    }
