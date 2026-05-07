from __future__ import annotations

import imaplib
import logging
import threading

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.email_demo import process_inbound_email_message

logger = logging.getLogger(__name__)


class EmailDemoPoller:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_loop,
            name="email-demo-poller",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                process_email_inbox_cycle()
            except Exception:  # pragma: no cover - background worker safety
                logger.exception("Email demo poll cycle failed")
            self._stop_event.wait(settings.email_poll_interval_seconds)


def process_email_inbox_cycle() -> None:
    if (
        not settings.email_imap_host
        or not settings.email_imap_user
        or not settings.email_imap_password
    ):
        logger.info("Email poller is enabled but IMAP credentials are incomplete; skipping cycle")
        return

    with imaplib.IMAP4_SSL(settings.email_imap_host) as client:
        client.login(settings.email_imap_user, settings.email_imap_password)
        client.select("INBOX")
        status, data = client.search(None, "UNSEEN")
        if status != "OK" or not data:
            return
        for message_num in data[0].split():
            status, message_data = client.fetch(message_num, "(RFC822)")
            if status != "OK":
                continue
            raw_message = _extract_rfc822_bytes(message_data)
            if raw_message is None:
                continue
            with SessionLocal() as db:
                try:
                    process_inbound_email_message(db, raw_message)
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("Failed to process inbound email message")
            client.store(message_num, "+FLAGS", "(\\Seen)")


def _extract_rfc822_bytes(message_data: list[object]) -> bytes | None:
    for item in message_data:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            return item[1]
    return None
