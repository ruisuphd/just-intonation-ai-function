"""FastAPI application for IntoMarketing SaaS API."""

from __future__ import annotations

import os
import re
import time

import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from api.routes import (
    account,
    admin_config,
    analytics,
    billing,
    calendar as calendar_routes,
    chat as chat_routes,
    documents,
    drafts,
    health,
    intelligence,
    leads,
    newsletters,
    oauth,
    onboarding,
    outreach,
    settings,
)
from api.routes.usage import router as usage_router
from shared.logger import get_logger
from shared.redis_client import rate_limit_check


def _init_sentry() -> None:
    sentry_dsn = os.getenv("SENTRY_DSN")
    if not sentry_dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
    )


_init_sentry()

app = FastAPI(title="IntoMarketing API", version="1.0.0")
logger = get_logger("api.app")

allowed_origins = [
    origin.strip()
    for origin in re.split(r"[,\s]+", os.getenv("ALLOWED_ORIGINS", "http://localhost:3000"))
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Rate limiter (Redis-backed with in-memory fallback) ──────────────────────

# Paths with stricter rate limits (max requests per window)
_RATE_LIMIT_CONFIG: dict[str, tuple[int, int]] = {
    # path_prefix: (max_requests, window_seconds)
    "/api/chat": (10, 60),
    "/api/drafts/quick-generate": (5, 60),
    "/api/newsletters/generate": (3, 60),
    "/billing/checkout": (5, 60),
    "/api/oauth/": (10, 60),
}

_DEFAULT_RATE_LIMIT = (60, 60)  # 60 requests per minute for other endpoints


def _check_rate_limit(user_key: str, path: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    max_requests, window = _DEFAULT_RATE_LIMIT
    for prefix, config in _RATE_LIMIT_CONFIG.items():
        if path.startswith(prefix):
            max_requests, window = config
            break

    return rate_limit_check(user_key, path, max_requests, window)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Skip rate limiting for health checks and static assets
    path = request.url.path
    if path in ("/", "/api/health", "/favicon.ico", "/robots.txt"):
        return await call_next(request)

    # Skip for webhooks (Stripe verifies via signature)
    if path == "/billing/webhook":
        return await call_next(request)

    # Use Authorization header as user key, fallback to IP
    auth_header = request.headers.get("authorization", "")
    if auth_header:
        user_key = auth_header[-16:]  # Last 16 chars of token as key
    else:
        user_key = request.client.host if request.client else "unknown"

    if not _check_rate_limit(user_key, path):
        logger.warning(
            "api.rate_limited",
            extra={"path": path, "user_key_suffix": user_key[-8:]},
        )
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please try again later."},
        )

    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started_at = time.monotonic()
    response = await call_next(request)
    logger.info(
        "api.request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": round((time.monotonic() - started_at) * 1000),
        },
    )
    return response


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "intomarketing-api"}


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/robots.txt")
async def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all handler so unhandled errors still return a JSON body with CORS headers."""
    logger.error(
        "api.unhandled_exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(health.router)
app.include_router(account.router)
app.include_router(admin_config.router)
app.include_router(chat_routes.router)
app.include_router(oauth.router)
app.include_router(onboarding.router)
app.include_router(billing.router)
app.include_router(drafts.router)
app.include_router(calendar_routes.router)
app.include_router(analytics.router)
app.include_router(intelligence.router)
app.include_router(leads.router)
app.include_router(outreach.router)
app.include_router(documents.router)
app.include_router(settings.router)
app.include_router(newsletters.router)
app.include_router(usage_router)
