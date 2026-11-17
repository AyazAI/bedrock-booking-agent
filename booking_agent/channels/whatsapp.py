from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

log = logging.getLogger("booking.whatsapp")
router = APIRouter()


def signature_ok(secret: str, body: bytes, header: str | None) -> bool:
    """Reject when the app secret is empty. A missing check must not accept posts."""

    if not secret or not header or not header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.removeprefix("sha256="), digest)


def session_for_sender(sender: str) -> str:
    return "wa-" + hashlib.sha256(sender.encode()).hexdigest()[:16]


@router.get("/api/whatsapp/webhook")
async def verify(request: Request) -> Response:
    settings = request.app.state.settings
    if not settings.whatsapp_enabled:
        raise HTTPException(status_code=404, detail="WhatsApp adapter is off")
    params = request.query_params
    token = params.get("hub.verify_token", "")
    if (
        params.get("hub.mode") == "subscribe"
        and settings.whatsapp_verify_token
        and hmac.compare_digest(token, settings.whatsapp_verify_token)
    ):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="verify failed")


@router.post("/api/whatsapp/webhook")
async def receive(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    if not settings.whatsapp_enabled:
        raise HTTPException(status_code=404, detail="WhatsApp adapter is off")
    body = await request.body()
    if not signature_ok(
        settings.whatsapp_app_secret,
        body,
        request.headers.get("x-hub-signature-256"),
    ):
        raise HTTPException(status_code=403, detail="bad signature")
    try:
        payload = json.loads(body.decode() or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="bad json") from exc
    replies: list[dict[str, str]] = []
    for item in _text_messages(payload):
        if request.app.state.conversations.seen_inbound(item["id"]):
            continue
        session_id, turn = request.app.state.conversations.turn(
            session_for_sender(item["sender"]),
            item["text"],
        )
        status = _deliver(
            settings.whatsapp_access_token,
            settings.whatsapp_phone_number_id,
            settings.whatsapp_graph_version,
            item["sender"],
            turn.reply,
        )
        request.app.state.conversations.mark_inbound(item["id"])
        replies.append({"status": status, "session_id": session_id, "reply": turn.reply})
        log.info("whatsapp turn status=%s tools=%s", status, len(turn.tool_calls))
    return {"replies": replies}


def _text_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for message in value.get("messages") or []:
                if message.get("type") != "text":
                    continue
                text = ((message.get("text") or {}).get("body") or "").strip()
                sender = str(message.get("from") or "")
                message_id = str(message.get("id") or "")
                if text and sender and message_id:
                    found.append({"id": message_id, "sender": sender, "text": text})
    return found


def _deliver(token: str, phone_number_id: str, version: str, to: str, text: str) -> str:
    if not token or not phone_number_id:
        return "dry_run"
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text[:4000]},
        },
        timeout=10,
    )
    response.raise_for_status()
    return "sent"
