from __future__ import annotations

import asyncio
import logging

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
        return {"uid": "dev-user", "email": "dev@localhost", "name": "Dev User"}
    try:
        return await asyncio.to_thread(_verify_token_sync, token)
    except Exception:
        raise ValueError("Invalid or expired token")
