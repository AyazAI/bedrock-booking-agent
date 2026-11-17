from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from booking_agent import __version__
from booking_agent.agent.tools import build_executor
from booking_agent.api.routes import router as api_router
from booking_agent.bookings.catalog import load_business
from booking_agent.bookings.service import BookingService
from booking_agent.channels.whatsapp import router as whatsapp_router
from booking_agent.clock import Clock, SystemClock
from booking_agent.config import Settings, get_settings, project_root
from booking_agent.conversations import ConversationStore
from booking_agent.db import init_db, make_engine, make_session_factory
from booking_agent.llm.factory import build_provider
from booking_agent.rag.knowledge import build_knowledge

log = logging.getLogger("booking")


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    clock = clock or SystemClock()
    knowledge_dir = settings.resolve_path(settings.knowledge_dir)
    business = load_business(knowledge_dir)
    database_url = _absolute_sqlite(settings)
    Path(settings.resolve_path(settings.chroma_path)).mkdir(parents=True, exist_ok=True)
    if database_url.startswith("sqlite:///"):
        sqlite_path = database_url.removeprefix("sqlite:///")
        if sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(database_url)
    init_db(engine)
    factory = make_session_factory(engine)
    bookings = BookingService(factory, business, clock, seed_demo=settings.seed_demo)
    knowledge = build_knowledge(
        knowledge_dir=knowledge_dir,
        business=business,
        backend=settings.vector_backend,
        chroma_path=str(settings.resolve_path(settings.chroma_path)),
        database_url=database_url,
        dims=settings.embedding_dims,
        threshold=settings.faq_score_threshold,
    )
    provider = build_provider(settings, business, clock)
    conversations = ConversationStore(
        factory,
        provider,
        build_executor(bookings, knowledge),
        business,
        settings.max_tool_steps,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        knowledge.index()
        bookings.seed()
        log.info(
            "ready provider=%s vector=%s whatsapp=%s",
            settings.llm_provider,
            settings.vector_backend,
            settings.whatsapp_enabled,
        )
        yield

    app = FastAPI(
        title="Northline booking assistant",
        version=__version__,
        summary="Sample appointment desk with tool calling and local FAQ retrieval.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.business = business
    app.state.bookings = bookings
    app.state.knowledge = knowledge
    app.state.conversations = conversations
    app.include_router(api_router)
    app.include_router(whatsapp_router)

    static_dir = project_root() / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return app


def _absolute_sqlite(settings: Settings) -> str:
    url = settings.database_url
    prefix = "sqlite:///"
    if not url.startswith(prefix) or url.endswith(":memory:"):
        return url
    path = url.removeprefix(prefix)
    if path.startswith("/") or (len(path) > 2 and path[1] == ":"):
        return url
    return prefix + str(settings.resolve_path(path))


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


_configure_logging()


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return create_app()
    raise AttributeError(name)
