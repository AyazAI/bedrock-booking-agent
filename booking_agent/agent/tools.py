from __future__ import annotations

from collections.abc import Callable
from typing import Any

from booking_agent.bookings.service import BookingService
from booking_agent.rag.knowledge import KnowledgeBase

ToolExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "check_availability",
        "description": "List open start times for a service on one date. Date is YYYY-MM-DD.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["service", "date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_booking",
        "description": (
            "Save a booking after check_availability showed that start time as free. "
            "Time is HH:MM in the studio timezone."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "date": {"type": "string"},
                "time": {"type": "string"},
                "customer_name": {"type": "string"},
            },
            "required": ["service", "date", "time", "customer_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cancel_booking",
        "description": "Cancel a booking by its confirmation code.",
        "parameters": {
            "type": "object",
            "properties": {
                "confirmation_code": {"type": "string"},
            },
            "required": ["confirmation_code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_faq",
        "description": (
            "Find a studio note that answers a factual question. "
            "If matched is false, the notes do not answer it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]


def build_executor(bookings: BookingService, knowledge: KnowledgeBase) -> ToolExecutor:
    def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "check_availability":
                return bookings.check_availability(
                    str(arguments.get("service", "")),
                    str(arguments.get("date", "")),
                )
            if name == "create_booking":
                return bookings.create_booking(
                    str(arguments.get("service", "")),
                    str(arguments.get("date", "")),
                    str(arguments.get("time", "")),
                    str(arguments.get("customer_name", "")),
                )
            if name == "cancel_booking":
                return bookings.cancel_booking(str(arguments.get("confirmation_code", "")))
            if name == "search_faq":
                return knowledge.search(str(arguments.get("query", "")))
        except Exception as exc:  # noqa: BLE001 — tools must return a payload, not crash the turn
            return {"ok": False, "error": "tool_failed", "detail": type(exc).__name__}
        return {"ok": False, "error": "unknown_tool", "name": name}

    return execute
