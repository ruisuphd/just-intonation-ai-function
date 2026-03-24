import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import verify_app_check_token_string, verify_firebase_token
from app.db.base import get_db
from app.models import User

logger = logging.getLogger(__name__)


async def get_current_user(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token",
        )
    try:
        claims = await verify_firebase_token(token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e) or "Invalid or expired token",
        ) from e
    except Exception as e:
        logger.warning("Firebase token verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from e
    firebase_uid = claims.get("uid")
    if not firebase_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
        )
    result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
    user = result.scalar_one_or_none()
    if user:
        return user
    email = claims.get("email") or ""
    display_name = claims.get("name") or claims.get("email") or ""
    await db.execute(
        insert(User)
        .values(
            firebase_uid=firebase_uid,
            email=email,
            display_name=display_name,
        )
        .on_conflict_do_nothing(index_elements=["firebase_uid"])
    )
    await db.flush()
    result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User provisioning failed",
        )
    return user


async def require_app_check_if_enforced(
    x_firebase_appcheck: Annotated[str | None, Header(alias="X-Firebase-AppCheck")] = None,
) -> None:
    if not settings.FIREBASE_APP_CHECK_ENFORCE:
        return
    try:
        await verify_app_check_token_string(x_firebase_appcheck or "")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e) or "App Check verification failed",
        ) from e
