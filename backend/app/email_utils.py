"""Minimal SMTP email sending, configured entirely through environment
variables so no credentials ever need to live in source control.

Without SMTP_HOST set, send_email() logs the message instead of sending it -
the account-setup-link flow (see routers/auth.py's setup_password /
routers/admin.py's approve_user) still works end-to-end for local/dev use,
just via the server log instead of an inbox.
"""

import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger("tit4tat.email")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME or "no-reply@tit4tat.local")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() != "false"


def send_email(to: str, subject: str, body: str) -> bool:
    """Returns True if the message was actually handed to an SMTP server,
    False if it was only logged (SMTP not configured) or sending failed."""
    if not SMTP_HOST:
        logger.info("SMTP not configured - logging email instead of sending.\nTo: %s\nSubject: %s\n\n%s", to, subject, body)
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USERNAME and SMTP_PASSWORD:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to], msg.as_string())
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False
