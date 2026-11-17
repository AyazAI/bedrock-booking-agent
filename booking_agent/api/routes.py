from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, HTTPException, Request

from booking_agent.api.schemas import ChatRequest, ChatResponse, ToolTraceModel
from booking_agent.bookings.catalog import describe_hours

log = logging.getLogger("booking.api")
router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "vector_backend": settings.vector_backend,
        "faq_chunks": request.app.state.knowledge.chunk_count,
        "whatsapp": "on" if settings.whatsapp_enabled else "off",
    }


@router.get("/api/meta")
def meta(request: Request) -> dict[str, object]:
    business = request.app.state.business
    return {
        "business_name": business.name,
        "disclaimer": business.disclaimer,
        "hours": describe_hours(business),
        "llm_provider": request.app.state.settings.llm_provider,
        "suggestions": list(business.suggestions),
        "services": [
            {"id": service.id, "name": service.name, "duration_min": service.duration_min}
            for service in business.services
        ],
    }


@router.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request) -> ChatResponse:
    text = body.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty message")
    session_id, turn = request.app.state.conversations.turn(body.session_id, text)
    log.info("chat tools=%s", ",".join(item.name for item in turn.tool_calls) or "-")
    return ChatResponse(
        session_id=session_id,
        reply=turn.reply,
        tool_calls=[
            ToolTraceModel(name=item.name, arguments=item.arguments, result=item.result)
            for item in turn.tool_calls
        ],
    )


@router.get("/api/bookings")
def bookings(request: Request) -> dict[str, object]:
    expected = request.app.state.settings.demo_api_key
    given = request.headers.get("x-demo-key", "")
    if not expected or not hmac.compare_digest(given, expected):
        raise HTTPException(status_code=401, detail="demo key required")
    return {"bookings": request.app.state.bookings.list_bookings()}
