"""Forward contact-form messages to the Google Apps Script web app.

The Apps Script (integrations/google-apps-script) appends them to a Google
Sheet used as a lightweight helpdesk and sends notification/auto-reply emails.

Apps Script web apps cannot read request headers, so authenticity is proven
inside the body: `signature = HMAC-SHA256(secret, f"{timestamp}.{payload}")`.
The script rejects bad signatures and timestamps older than 5 minutes.
"""

import hashlib
import hmac
import json
import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def sign(payload: str, timestamp: int, secret: str) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256).hexdigest()


def build_envelope(data: dict, secret: str, timestamp: int | None = None) -> dict:
    timestamp = timestamp or int(time.time())
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return {"payload": payload, "timestamp": timestamp, "signature": sign(payload, timestamp, secret)}


def forward_contact_message(data: dict) -> None:
    """Runs as a BackgroundTask; failures are logged, never raised to the client."""
    if not settings.GAS_WEBHOOK_URL:
        return

    envelope = build_envelope(data, settings.GAS_SHARED_SECRET)
    try:
        # Apps Script answers with a 302 to googleusercontent.com, hence follow_redirects.
        response = httpx.post(settings.GAS_WEBHOOK_URL, json=envelope, timeout=15, follow_redirects=True)
        result = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Contact relay to Apps Script failed")
        return

    if result.get("ok"):
        logger.info("Contact message relayed", extra={"ticket_id": result.get("ticketId")})
    else:
        logger.warning("Apps Script rejected contact message", extra={"error": result.get("error")})
