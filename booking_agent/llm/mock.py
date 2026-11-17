from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from booking_agent.bookings.catalog import Business
from booking_agent.clock import Clock
from booking_agent.llm.base import ChatMessage, Completion, ToolCall

_CODE = re.compile(r"\b(NL-\d{4})\b", re.IGNORECASE)
_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_AMPM = re.compile(r"\b(\d{1,2})\s*(am|pm)\b", re.IGNORECASE)
_ISO_DAY = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_NAME = re.compile(r"\bfor\s+([A-Za-z][A-Za-z' -]{0,40})")
_NOT_A_NAME = {"tomorrow", "today", "me", "us", "an", "a", "the"}
_BOOK = ("book", "reserve", "schedule", "appointment")
_AVAIL = ("available", "availability", "opening", "openings", "free", "slots")
_FAQ = (
    "policy",
    "hours",
    "open",
    "price",
    "cost",
    "pay",
    "payment",
    "address",
    "location",
    "where",
    "bring",
    "expect",
    "cancellation",
)
_GREETING = ("hi", "hello", "hey", "good morning", "good afternoon")


class MockProvider:
    """Deterministic desk clerk. Tool results are repeated, not invented."""

    name = "mock"

    def __init__(self, business: Business, clock: Clock) -> None:
        self._business = business
        self._clock = clock
        self._calls = 0

    def complete(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> Completion:
        allowed = {spec["name"] for spec in tools}
        last = messages[-1]
        if last.role == "tool":
            followup = self._tool_followup(messages, allowed)
            if followup:
                return Completion(text="", tool_calls=followup, provider=self.name)
            return Completion(text=self._after_tool(messages), tool_calls=[], provider=self.name)
        user_text = _last_user_text(messages)
        tool_calls = self._first_tools(user_text, allowed)
        if tool_calls:
            return Completion(text="", tool_calls=tool_calls, provider=self.name)
        return Completion(text=self._plain(user_text), tool_calls=[], provider=self.name)

    def _first_tools(self, text: str, allowed: set[str]) -> list[ToolCall]:
        parsed = self._parse(text)
        if parsed["code"] and "cancel" in text.lower() and "cancel_booking" in allowed:
            return [self._call("cancel_booking", {"confirmation_code": parsed["code"]})]
        if _is_booking(text):
            if parsed["service"] is None:
                return []
            if parsed["date"] is None:
                return []
            if "check_availability" not in allowed:
                return []
            return [
                self._call(
                    "check_availability",
                    {"service": parsed["service"], "date": parsed["date"]},
                )
            ]
        if _is_faq(text) and "search_faq" in allowed:
            return [self._call("search_faq", {"query": text.strip()})]
        return []

    def _tool_followup(self, messages: list[ChatMessage], allowed: set[str]) -> list[ToolCall]:
        last = messages[-1]
        if last.name != "check_availability":
            return []
        payload = json.loads(last.content)
        parsed = self._parse(_last_user_text(messages))
        if not _wants_to_book(_last_user_text(messages)):
            return []
        if not payload.get("ok") or payload.get("closed"):
            return []
        wanted = parsed["time"]
        name = parsed["name"]
        slots = payload.get("slots") or []
        if not wanted or not name or wanted not in slots or "create_booking" not in allowed:
            return []
        return [
            self._call(
                "create_booking",
                {
                    "service": parsed["service"],
                    "date": parsed["date"],
                    "time": wanted,
                    "customer_name": name,
                },
            )
        ]

    def _after_tool(self, messages: list[ChatMessage]) -> str:
        last = messages[-1]
        payload = json.loads(last.content)
        if last.name == "check_availability":
            user_text = _last_user_text(messages)
            return _availability_text(payload, self._parse(user_text), _wants_to_book(user_text))
        if last.name == "create_booking":
            return _create_text(payload)
        if last.name == "cancel_booking":
            return _cancel_text(payload)
        if last.name == "search_faq":
            return _faq_text(payload)
        return "I could not complete that."

    def _parse(self, text: str) -> dict[str, str | None]:
        today = self._clock.now().astimezone(ZoneInfo(self._business.timezone)).date()
        return {
            "service": _service_name(text, self._business),
            "date": _date(text, today),
            "time": _time(text),
            "name": _name(text),
            "code": _code(text),
        }

    def _call(self, name: str, arguments: dict[str, Any]) -> ToolCall:
        self._calls += 1
        return ToolCall(id=f"call_{name}_{self._calls}", name=name, arguments=arguments)

    def _plain(self, text: str) -> str:
        lowered = text.strip().lower()
        if any(lowered == greeting or lowered.startswith(greeting + " ") for greeting in _GREETING):
            names = ", ".join(service.name for service in self._business.services)
            return (
                f"Hello, this is {self._business.name}'s appointment desk. "
                f"I can check times, book {names}, cancel with a confirmation code, "
                f"or answer from the studio notes. {self._business.disclaimer}"
            )
        parsed = self._parse(text)
        if _is_booking(text) and parsed["service"] is None:
            names = ", ".join(service.name for service in self._business.services)
            return f"Which service should I check? I have {names}."
        if _is_booking(text) and parsed["date"] is None:
            return "Which day should I check? You can say tomorrow or a date like 2026-11-19."
        if "cancel" in lowered and parsed["code"] is None:
            return "Send the confirmation code, for example cancel NL-1001."
        return (
            f"I can check open times, book a visit, cancel with a confirmation code, "
            f"or answer from the studio notes. {self._business.disclaimer}"
        )


def _last_user_text(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _is_booking(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _BOOK) or any(word in lowered for word in _AVAIL)


def _wants_to_book(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _BOOK)


def _is_faq(text: str) -> bool:
    lowered = text.lower()
    if "policy" in lowered or "cancellation" in lowered:
        return True
    if _is_booking(text):
        return False
    return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in _FAQ)


def _service_name(text: str, business: Business) -> str | None:
    service = business.resolve_service(text)
    if service is None:
        return None
    return service.name


def _date(text: str, today: date) -> str | None:
    match = _ISO_DAY.search(text)
    if match:
        return match.group(1)
    lowered = text.lower()
    if "tomorrow" in lowered:
        return (today + timedelta(days=1)).isoformat()
    if "today" in lowered:
        return today.isoformat()
    return None


def _time(text: str) -> str | None:
    match = _CLOCK.search(text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    ampm = _AMPM.search(text)
    if not ampm:
        return None
    hour = int(ampm.group(1))
    if hour < 1 or hour > 12:
        return None
    if ampm.group(2).lower() == "pm" and hour != 12:
        hour += 12
    if ampm.group(2).lower() == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:00"


def _name(text: str) -> str | None:
    match = _NAME.search(text)
    if not match:
        return None
    name = " ".join(match.group(1).strip(" .").split())
    if name.lower() in _NOT_A_NAME:
        return None
    return name


def _code(text: str) -> str | None:
    match = _CODE.search(text)
    if not match:
        return None
    return match.group(1).upper()


def _availability_text(
    payload: dict[str, Any],
    parsed: dict[str, str | None],
    wants_book: bool,
) -> str:
    if not payload.get("ok"):
        return "I could not check that service and date."
    if payload.get("closed"):
        nxt = payload.get("next_open_date")
        return (
            f"{payload.get('service')} is closed on {payload.get('date')}. "
            f"The next open day is {nxt}."
        )
    slots = payload.get("slots") or []
    if not slots:
        return f"There are no open times on {payload.get('date')}."
    wanted = parsed.get("time")
    listed = ", ".join(str(slot) for slot in list(slots)[:8])
    if wanted and wanted not in slots:
        return f"{wanted} is not free on {payload.get('date')}. Open times include {listed}."
    if wants_book and wanted and wanted in slots and parsed.get("name") is None:
        return f"{wanted} is free on {payload.get('date')}. What name should I put on the booking?"
    return f"Open times on {payload.get('date')} include {listed}."


def _create_text(payload: dict[str, Any]) -> str:
    if not payload.get("ok"):
        if payload.get("error") == "overlap":
            return (
                f"{payload.get('time')} on {payload.get('date')} was just taken. "
                "Ask me for open times again."
            )
        return "I could not save that booking."
    return (
        f"Booked {payload['service']} for {payload['customer_name']} "
        f"on {payload['date']} at {payload['time']}. "
        f"Confirmation {payload['code']}."
    )


def _cancel_text(payload: dict[str, Any]) -> str:
    if not payload.get("ok"):
        return f"I can't find confirmation code {payload.get('code')}."
    if payload.get("already"):
        return f"{payload['code']} was already cancelled."
    return f"Cancelled {payload['code']}."


def _faq_text(payload: dict[str, Any]) -> str:
    results = payload.get("results") or []
    if not payload.get("matched") or not results:
        return "I don't have that in the studio notes. The studio will need to confirm."
    return str(results[0]["answer"])
