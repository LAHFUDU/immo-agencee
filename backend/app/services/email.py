"""Outbound email via SMTP. If SMTP is not configured, nothing is sent and callers are told so.

WhatsApp/SMS providers can be added later behind the same "send or report not configured" contract.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("immo.email")


def send_email(to: str, subject: str, body: str) -> str:
    """Returns 'sent', 'failed' or 'not_configured'. Never pretends a message was sent."""
    if not settings.smtp_configured:
        return "not_configured"
    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            if settings.SMTP_STARTTLS:
                smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        return "sent"
    except Exception:  # noqa: BLE001 - delivery problems must not break business operations
        log.exception("SMTP delivery to %s failed", to)
        return "failed"
