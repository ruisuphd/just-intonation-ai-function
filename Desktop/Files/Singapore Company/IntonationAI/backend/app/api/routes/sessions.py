from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.base import get_db
from app.models import Session, User
from app.schemas.coach import CoachSessionResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/", response_model=list[CoachSessionResponse])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user.id)
        .order_by(Session.started_at.desc())
        .limit(50)
    )
    sessions = result.scalars().all()
    return [
        CoachSessionResponse(
            id=str(s.id),
            coach_type=s.coach_type,
            locale=s.locale or "en",
            started_at=s.started_at.isoformat(),
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            prompt_version=settings.COACH_PROMPT_VERSION,
        )
        for s in sessions
    ]
