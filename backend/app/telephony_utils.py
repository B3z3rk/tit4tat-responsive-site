"""Minimal Twilio Voice bridge-calling, configured entirely through
environment variables so no credentials ever need to live in source control.

Without TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_FROM_NUMBER set,
place_bridge_call() logs what it would have done instead of placing a real
call - the tap-to-call feature still works, just simulated (see
routers/emergency.py).

Uses Twilio's REST API directly over urllib rather than the official SDK,
to avoid an extra dependency for what's a single POST request. The dial
instructions (TwiML) are passed inline as a request parameter rather than
fetched from a callback URL, so this works even though this server isn't
reachable from the public internet.
"""

import base64
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger("tit4tat.telephony")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")


def place_bridge_call(caller_phone: str, callee_phone: str) -> bool:
    """Rings caller_phone; once answered, bridges in callee_phone so the two
    real phones are connected to each other. Returns True only if Twilio
    accepted the request - not proof the call was answered or connected."""
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER):
        logger.info(
            "Twilio not configured - logging instead of placing a real call. "
            "Would ring %s, then bridge in %s.",
            caller_phone, callee_phone,
        )
        return False

    twiml = f"<Response><Dial>{callee_phone}</Dial></Response>"
    body = urllib.parse.urlencode({
        "To": caller_phone,
        "From": TWILIO_FROM_NUMBER,
        "Twiml": twiml,
    }).encode("utf-8")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Calls.json"
    request = urllib.request.Request(url, data=body, method="POST")
    credentials = base64.b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()).decode()
    request.add_header("Authorization", f"Basic {credentials}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
        return True
    except Exception:
        logger.exception("Failed to place bridge call from %s to %s", caller_phone, callee_phone)
        return False
