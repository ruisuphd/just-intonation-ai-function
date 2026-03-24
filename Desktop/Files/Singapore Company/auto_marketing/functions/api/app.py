"""FastAPI application for IntoMarketing SaaS API."""

from __future__ import annotations

import os
import re
import time
import traceback
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from api.routes import (
    account,
    admin_config,
    analytics,
    billing,
    calendar as calendar_routes,
    chat as chat_routes,
    dashboard as dashboard_routes,
    documents,
    drafts,
    health,
    intelligence,
    leads,
    legal as legal_routes,
    newsletters,
    notifications,
    oauth,
    onboarding,
    outreach,
    pipeline as pipeline_routes,
    settings,
)
from api.routes.usage import router as usage_router
from api.middleware.auth import rate_limit_identity_key
from shared.errors import (
    INTERNAL,
    RATE_LIMITED,
    VALIDATION_ERROR,
    build_error_body,
    status_to_error_code,
    validation_fields_from_errors,
)
from shared.logger import clear_trace_id, get_logger, set_trace_id
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
    for origin in re.split(
        r"[,\s]+", os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    )
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


# First http middleware = outermost (runs first): trace_id for all downstream layers.
@app.middleware("http")
async def trace_context_middleware(request: Request, call_next):
    incoming = request.headers.get("x-request-id") or request.headers.get(
        "X-Request-ID"
    )
    tid = (incoming or "").strip() or uuid.uuid4().hex[:16]
    set_trace_id(tid)
    request.state.trace_id = tid
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = tid
        return response
    finally:
        clear_trace_id()


# ── Rate limiter (Redis-backed with in-memory fallback) ──────────────────────

# Paths with stricter rate limits (max requests per window)
_RATE_LIMIT_CONFIG: dict[str, tuple[int, int]] = {
    # path_prefix: (max_requests, window_seconds)
    "/api/chat": (10, 60),
    "/api/drafts/quick-generate": (5, 60),
    "/api/newsletters/generate": (5, 60),
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
    if path in ("/billing/webhook", "/webhooks/stripe"):
        return await call_next(request)

    user_key = rate_limit_identity_key(request)

    if not _check_rate_limit(user_key, path):
        trace_id = getattr(request.state, "trace_id", None) or uuid.uuid4().hex[:16]
        logger.warning(
            "api.rate_limited",
            extra={
                "path": path,
                "user_key_suffix": user_key[-8:],
                "trace_id": trace_id,
            },
        )
        body = build_error_body(
            error_code=RATE_LIMITED,
            detail="Too many requests. Please try again later.",
            trace_id=trace_id,
            status_code=429,
        )
        response = JSONResponse(status_code=429, content=body)
        response.headers["X-Request-ID"] = trace_id
        for key, value in _cors_headers_for_request(request).items():
            response.headers[key] = value
        return response

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


def _cors_headers_for_request(request: Request) -> dict[str, str]:
    """Return CORS headers so error responses remain readable in the browser."""
    origin = request.headers.get("origin")
    if origin and origin in allowed_origins:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Request-ID",
        }
    return {}


def _error_json_response(
    request: Request, status_code: int, body: dict
) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content=body)
    for key, value in _cors_headers_for_request(request).items():
        response.headers[key] = value
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    trace_id = getattr(request.state, "trace_id", None)
    code = status_to_error_code(exc.status_code)
    body = build_error_body(
        error_code=code,
        detail=exc.detail,
        trace_id=trace_id,
        status_code=exc.status_code,
    )
    return _error_json_response(request, exc.status_code, body)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    trace_id = getattr(request.state, "trace_id", None)
    fields = validation_fields_from_errors(exc.errors())
    body = build_error_body(
        error_code=VALIDATION_ERROR,
        detail="Request validation failed",
        trace_id=trace_id,
        fields=fields,
        status_code=422,
    )
    return _error_json_response(request, 422, body)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all handler so unhandled errors still return a JSON body with CORS headers."""
    tb = traceback.format_exc()
    logger.error(
        "api.unhandled_exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error": str(exc),
            "traceback": tb,
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:
        pass
    trace_id = getattr(request.state, "trace_id", None)
    content = build_error_body(
        error_code=INTERNAL,
        detail="Internal server error",
        trace_id=trace_id,
        status_code=500,
    )
    if os.getenv("DEBUG_API_ERRORS", "").lower() in ("1", "true", "yes"):
        content["debug"] = str(exc)
        content["traceback"] = tb.split("\n")
    response = JSONResponse(status_code=500, content=content)
    for key, value in _cors_headers_for_request(request).items():
        response.headers[key] = value
    return response


app.include_router(health.router)
app.include_router(legal_routes.router)
app.include_router(account.router)
app.include_router(admin_config.router)
app.include_router(chat_routes.router)
app.include_router(oauth.router)
app.include_router(pipeline_routes.router)
app.include_router(onboarding.router)
app.include_router(billing.router)
# Canonical URL for Stripe Dashboard webhooks (same handler as POST /billing/webhook)
app.add_api_route(
    "/webhooks/stripe",
    billing.stripe_webhook,
    methods=["POST"],
    tags=["webhooks"],
)
app.include_router(drafts.router)
app.include_router(calendar_routes.router)
app.include_router(analytics.router)
app.include_router(intelligence.router)
app.include_router(leads.router)
app.include_router(notifications.router)
app.include_router(outreach.router)
app.include_router(documents.router)
app.include_router(settings.router)
app.include_router(dashboard_routes.router)
app.include_router(newsletters.router)
app.include_router(usage_router)
