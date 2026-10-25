"""Minimal PayPal Orders v2 client (sandbox by default)."""

import logging
import re
from decimal import ROUND_HALF_UP, Decimal

import httpx

from app.core.config import settings
from app.core.exceptions import BadRequestError

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(15.0)
# PayPal order ids are short upper-case alphanumerics; anything else must not reach the URL path.
PAYPAL_ORDER_ID = re.compile(r"^[A-Z0-9]{8,36}$")


def vnd_to_usd(amount_vnd: Decimal) -> str:
    """PayPal does not support VND, so orders are charged in USD at a fixed rate."""
    usd = Decimal(amount_vnd) / Decimal(settings.USD_VND_RATE)
    return str(usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def get_access_token() -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{settings.PAYPAL_API_URL}/v1/oauth2/token",
            auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET),
            data={"grant_type": "client_credentials"},
        )
    if response.status_code != 200:
        logger.error("PayPal auth failed", extra={"status": response.status_code})
        raise BadRequestError("Could not authenticate with PayPal")
    return response.json()["access_token"]


async def create_order(internal_order_id: int, amount_vnd: Decimal) -> dict:
    token = await get_access_token()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{settings.PAYPAL_API_URL}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "reference_id": str(internal_order_id),
                        "amount": {"currency_code": "USD", "value": vnd_to_usd(amount_vnd)},
                    }
                ],
            },
        )
    if response.status_code != 201:
        logger.error("PayPal create order failed", extra={"status": response.status_code, "body": response.text})
        raise BadRequestError("PayPal API Error")
    return response.json()


async def capture_order(paypal_order_id: str) -> dict:
    """Capture a payment the buyer has approved in the PayPal popup."""
    if not PAYPAL_ORDER_ID.fullmatch(paypal_order_id):
        raise BadRequestError("Invalid PayPal order id")
    token = await get_access_token()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{settings.PAYPAL_API_URL}/v2/checkout/orders/{paypal_order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    if response.status_code not in (200, 201):
        logger.warning("PayPal capture failed", extra={"status": response.status_code, "body": response.text})
        return {"status": "FAILED", "details": response.json()}
    return response.json()
