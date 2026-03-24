import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    audio,
    auth,
    billing,
    coach,
    curriculum,
    dashboard,
    health,
    notifications,
    sessions,
    songs,
    telemetry,
    users,
    warmup,
)
from app.core.config import settings
from app.db.base import async_session_maker, init_db
from app.http_errors import install_canonical_unhandled_middleware, register_exception_handlers
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.simple_rate_limit import SimpleRateLimitMiddleware
from app.observability import configure_logging, init_sentry, instrument_tracing
from app.services.curriculum_seed import ensure_curriculum_seeded
from app.services.rag.knowledge_base import seed_knowledge_base
from app.services.songs_seed import ensure_songs_seeded

configure_logging()
init_sentry()

logger = logging.getLogger(__name__)


def _assert_production_config() -> None:
    if not settings.is_production:
        return
    if not settings.FIREBASE_PROJECT_ID:
        raise RuntimeError("FIREBASE_PROJECT_ID is required when ENVIRONMENT=production")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _assert_production_config()
    await init_db()
    try:
        await asyncio.to_thread(seed_knowledge_base)
    except Exception as e:
        logger.warning("Knowledge base seed failed (RAG may use keyword fallback): %s", e)
    async with async_session_maker() as db:
        await ensure_curriculum_seeded(db)
        await ensure_songs_seeded(db)
        await db.commit()
    yield


_docs = None if settings.is_production else "/docs"
_redoc = None if settings.is_production else "/redoc"

app = FastAPI(
    title="IntonationAI",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=_docs,
    redoc_url=_redoc,
)

_cors_origins = [settings.FRONTEND_URL]
if not settings.is_production:
    _cors_origins.append("http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SimpleRateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
install_canonical_unhandled_middleware(app)

app.include_router(health.router)

_API_PREFIXES = ("/api", "/api/v1")
for _prefix in _API_PREFIXES:
    app.include_router(auth.router, prefix=_prefix)
    app.include_router(users.router, prefix=_prefix)
    app.include_router(coach.router, prefix=_prefix)
    app.include_router(audio.router, prefix=_prefix)
    app.include_router(warmup.router, prefix=_prefix)
    app.include_router(sessions.router, prefix=_prefix)
    app.include_router(dashboard.router, prefix=_prefix)
    app.include_router(billing.router, prefix=_prefix)
    app.include_router(curriculum.router, prefix=_prefix)
    app.include_router(songs.router, prefix=_prefix)
    app.include_router(notifications.router, prefix=_prefix)
    app.include_router(telemetry.router, prefix=_prefix)

register_exception_handlers(app)
instrument_tracing(app)
