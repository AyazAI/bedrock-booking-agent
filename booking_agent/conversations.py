from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from booking_agent.agent.loop import Turn, history_from_rows, run_turn
from booking_agent.agent.prompts import system_prompt
from booking_agent.agent.tools import TOOL_SPECS, ToolExecutor
from booking_agent.bookings.catalog import Business
from booking_agent.db import ChatMessageRow, ChatSessionRow, InboundMessageRow, session_scope
from booking_agent.llm.base import ChatMessage, LLMProvider

_SESSION = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class ConversationStore:
    def __init__(
        self,
        factory: sessionmaker[Session],
        provider: LLMProvider,
        execute: ToolExecutor,
        business: Business,
        max_steps: int,
    ) -> None:
        self._factory = factory
        self._provider = provider
        self._execute = execute
        self._business = business
        self._max_steps = max_steps

    def turn(self, session_id: str | None, text: str) -> tuple[str, Turn]:
        session_id = _clean_session(session_id)
        history = self._history(session_id)
        result = run_turn(
            provider=self._provider,
            execute=self._execute,
            specs=TOOL_SPECS,
            history=history,
            user_text=text,
            system=system_prompt(self._business),
            max_steps=self._max_steps,
        )
        self._save(session_id, result)
        return session_id, result

    def seen_inbound(self, message_id: str) -> bool:
        with session_scope(self._factory) as session:
            return session.get(InboundMessageRow, message_id) is not None

    def mark_inbound(self, message_id: str) -> None:
        with session_scope(self._factory) as session:
            if session.get(InboundMessageRow, message_id) is None:
                session.add(InboundMessageRow(message_id=message_id, received_at=_now()))

    def _history(self, session_id: str) -> list[ChatMessage]:
        with session_scope(self._factory) as session:
            rows = session.scalars(
                select(ChatMessageRow)
                .where(ChatMessageRow.session_id == session_id)
                .order_by(ChatMessageRow.id)
            ).all()
            tail = rows[-12:]
            return history_from_rows([(row.role, row.content) for row in tail])

    def _save(self, session_id: str, result: Turn) -> None:
        with session_scope(self._factory) as session:
            if session.get(ChatSessionRow, session_id) is None:
                session.add(ChatSessionRow(id=session_id, created_at=_now()))
            for message in result.new_messages:
                if message.role not in {"user", "assistant"} or not message.content:
                    continue
                if message.role == "assistant" and message.tool_calls:
                    continue
                session.add(
                    ChatMessageRow(
                        session_id=session_id,
                        role=message.role,
                        content=message.content,
                        created_at=_now(),
                    )
                )


def _clean_session(session_id: str | None) -> str:
    if session_id and _SESSION.match(session_id):
        return session_id
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
