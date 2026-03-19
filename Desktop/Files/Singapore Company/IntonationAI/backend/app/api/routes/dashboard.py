from datetime import date, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.models import Session, User, WarmupSession

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    coach_result = await db.execute(
        select(func.count(Session.id)).where(Session.user_id == user.id)
    )
    total_sessions = coach_result.scalar() or 0

    warmup_result = await db.execute(
        select(func.count(WarmupSession.id)).where(
            WarmupSession.user_id == user.id
        )
    )
    warmup_count = warmup_result.scalar() or 0

    warmup_scores_result = await db.execute(
        select(WarmupSession.scores_json).where(
            WarmupSession.user_id == user.id,
            WarmupSession.scores_json.isnot(None),
        )
    )
    all_scores: list[float] = []
    for row in warmup_scores_result.scalars().all():
        if row and row[0]:
            for s in row[0]:
                if isinstance(s, dict) and "overall_score" in s:
                    all_scores.append(float(s["overall_score"]))
    avg_score = (
        round(sum(all_scores) / len(all_scores) * 100)
        if all_scores
        else None
    )

    session_dates_result = await db.execute(
        select(func.date(Session.started_at)).where(
            Session.user_id == user.id
        ).distinct()
    )
    warmup_dates_result = await db.execute(
        select(func.date(WarmupSession.started_at)).where(
            WarmupSession.user_id == user.id
        ).distinct()
    )
    coach_dates = {r[0] for r in session_dates_result.scalars().all() if r[0]}
    warmup_dates = {r[0] for r in warmup_dates_result.scalars().all() if r[0]}
    all_dates = coach_dates | warmup_dates

    streak = 0
    today = date.today()
    if today in all_dates:
        check = today
        while check in all_dates:
            streak += 1
            check -= timedelta(days=1)

    return {
        "total_sessions": total_sessions,
        "warmup_sessions": warmup_count,
        "average_score": avg_score,
        "practice_streak_days": streak,
    }
