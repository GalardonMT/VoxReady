"""Outgoing webhook dispatcher with HMAC-SHA256 signature and retries."""
import asyncio
import hashlib
import hmac
import json
import logging
import uuid

import httpx

from app.config import Settings
from app.utils import iso, utcnow

logger = logging.getLogger("voxready.webhooks")


def build_event_payload(
    event_type: str,
    session_id: uuid.UUID,
    analysis_id: uuid.UUID,
    status: str,
    report_ready: bool,
    failure_reason: str | None = None,
) -> dict:
    payload = {
        "eventType": event_type,
        "sessionId": str(session_id),
        "analysisId": str(analysis_id),
        "status": status,
        "reportReady": report_ready,
        "occurredAt": iso(utcnow()),
    }
    if failure_reason:
        payload["failureReason"] = failure_reason
    return payload


async def dispatch_webhook(settings: Settings, payload: dict) -> None:
    """POST the event to every configured endpoint with retries/backoff."""
    endpoints = settings.webhook_endpoint_list
    if not endpoints:
        return
    body = json.dumps(payload).encode()
    signature = hmac.new(
        settings.webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "x-voxready-signature": f"sha256={signature}",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in endpoints:
            for attempt in range(settings.webhook_max_retries):
                try:
                    response = await client.post(url, content=body, headers=headers)
                    if response.status_code < 300:
                        break
                    logger.warning(
                        "Webhook %s respondió %s (intento %s)",
                        url, response.status_code, attempt + 1,
                    )
                except httpx.HTTPError as exc:
                    logger.warning(
                        "Webhook %s falló: %s (intento %s)", url, exc, attempt + 1
                    )
                if attempt + 1 < settings.webhook_max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))


def fire_and_forget(settings: Settings, payload: dict) -> None:
    """Schedule webhook delivery without blocking the caller."""
    try:
        asyncio.create_task(dispatch_webhook(settings, payload))
    except RuntimeError:
        logger.warning("No hay event loop activo; webhook descartado.")
