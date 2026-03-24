from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)
_firebase_initialized = False


def _init_firebase() -> None:
    global _firebase_initialized
    if _firebase_initialized:
        return
    try:
        import firebase_admin

        if firebase_admin._apps:
            _firebase_initialized = True
            return

        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            from firebase_admin import credentials

            cred = credentials.Certificate(settings.GOOGLE_APPLICATION_CREDENTIALS)
            firebase_admin.initialize_app(cred)
        elif settings.FIREBASE_PROJECT_ID:
            firebase_admin.initialize_app(options={"projectId": settings.FIREBASE_PROJECT_ID})
        else:
            return

        _firebase_initialized = True
    except Exception:
        logger.exception("Firebase init failed")


def _verify_token_sync(token: str) -> dict:
    from firebase_admin import auth

    decoded = auth.verify_id_token(token, check_revoked=True)
    return dict(decoded)


async def verify_firebase_token(token: str) -> dict:
    _init_firebase()
    if not settings.FIREBASE_PROJECT_ID:
        raise ValueError("FIREBASE_PROJECT_ID is required for auth. Set it in production.")
    try:
        return await asyncio.to_thread(_verify_token_sync, token)
    except Exception:
        raise ValueError("Invalid or expired token")


async def verify_app_check_token_string(token: str) -> dict[str, Any]:
    """Verify a Firebase App Check token (header or WebSocket payload). Raises ValueError on failure."""
    raw = (token or "").strip()
    if not raw:
        raise ValueError("Missing App Check token")
    _init_firebase()
    if not settings.FIREBASE_PROJECT_ID:
        raise ValueError("FIREBASE_PROJECT_ID is required for App Check")
    if not _firebase_initialized:
        raise ValueError("Firebase Admin is not initialized")
    from firebase_admin import app_check

    try:
        return await asyncio.to_thread(app_check.verify_token, raw)
    except Exception as e:
        logger.debug("App Check verify failed: %s", e)
        raise ValueError("Invalid App Check token") from e
