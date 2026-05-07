from __future__ import annotations

import re
from email.message import Message
from html.parser import HTMLParser

CONFIRM_WORDS = {"yes", "y", "confirm", "confirmed", "approve", "approved", "ok", "okay", "go"}
REJECT_WORDS = {"no", "n", "cancel", "stop", "reject", "decline"}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def extract_message_text(message: Message) -> str:
    if message.is_multipart():
        plain_parts: list[str] = []
        html_parts: list[str] = []
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            payload = _decode_message_part(part)
            content_type = part.get_content_type()
            if content_type == "text/plain" and payload.strip():
                plain_parts.append(payload)
            elif content_type == "text/html" and payload.strip():
                html_parts.append(strip_html(payload))
        if plain_parts:
            return "\n".join(plain_parts).strip()
        if html_parts:
            return "\n".join(html_parts).strip()
        return ""
    return _decode_message_part(message).strip()


def strip_html(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    return parser.get_text()


def strip_quoted_reply_text(value: str) -> str:
    reply_header_match = re.search(r"(?is)\nOn .+?wrote:\s*", value)
    if reply_header_match:
        value = value[: reply_header_match.start()]

    lines = value.splitlines()
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if re.match(r"^On .+ wrote:\s*$", stripped):
            break
        kept.append(line)
    cleaned = "\n".join(kept).strip()
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def normalize_reply_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def classify_confirmation_reply(value: str) -> str | None:
    first_line = next((line.strip() for line in value.splitlines() if line.strip()), "")
    normalized = normalize_reply_text(first_line)
    normalized = re.sub(r"^[^a-z]+|[^a-z]+$", "", normalized)
    if normalized in CONFIRM_WORDS:
        return "CONFIRM"
    if normalized in REJECT_WORDS:
        return "REJECT"
    return None


def _decode_message_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")
