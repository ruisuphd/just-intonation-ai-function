import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.models import Session, User, WarmupSession

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _resolve_tz(name: str | None) -> ZoneInfo:
    if name:
        try:
            return ZoneInfo(name.strip())
        except Exception:
            pass
    return ZoneInfo("UTC")


def _local_date(ts: datetime, tz: ZoneInfo) -> date:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(tz).date()


@router.get("/stats")
async def get_dashboard_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    timezone_name: str | None = Query(None, alias="timezone"),
) -> dict[str, Any]:
    tz = _resolve_tz(timezone_name)
    today = datetime.now(tz).date()

    coach_result = await db.execute(
        select(func.count(Session.id)).where(Session.user_id == user.id)
    )
    total_sessions = coach_result.scalar() or 0

    warmup_result = await db.execute(
        select(func.count(WarmupSession.id)).where(WarmupSession.user_id == user.id)
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
        scores_list = row
        if isinstance(scores_list, list):
            for s in scores_list:
                if isinstance(s, dict) and "overall_score" in s:
                    try:
                        all_scores.append(float(s["overall_score"]))
                    except (TypeError, ValueError):
                        pass
        elif scores_list is not None:
            logger.warning(
                "warmup scores_json has unexpected type for user=%s: %s",
                user.id,
                type(scores_list).__name__,
            )
    avg_score = round(sum(all_scores) / len(all_scores) * 100) if all_scores else None

    session_starts = await db.execute(select(Session.started_at).where(Session.user_id == user.id))
    warmup_starts = await db.execute(
        select(WarmupSession.started_at).where(WarmupSession.user_id == user.id)
    )
    all_dates: set[date] = set()
    for ts in session_starts.scalars().all():
        if ts is not None:
            all_dates.add(_local_date(ts, tz))
    for ts in warmup_starts.scalars().all():
        if ts is not None:
            all_dates.add(_local_date(ts, tz))

    streak = 0
    if today in all_dates:
        check = today
        while check in all_dates:
            streak += 1
            check -= timedelta(days=1)

    week_start = _week_start(today)
    week_start_local = datetime.combine(week_start, datetime.min.time(), tzinfo=tz)
    week_end_local = week_start_local + timedelta(days=7)

    week_sessions_r = await db.execute(
        select(func.count(Session.id)).where(
            Session.user_id == user.id,
            Session.started_at >= week_start_local,
            Session.started_at < week_end_local,
        )
    )
    sessions_this_week = week_sessions_r.scalar() or 0
    warmup_week_r = await db.execute(
        select(func.count(WarmupSession.id)).where(
            WarmupSession.user_id == user.id,
            WarmupSession.started_at >= week_start_local,
            WarmupSession.started_at < week_end_local,
        )
    )
    warmups_this_week = warmup_week_r.scalar() or 0
    practice_minutes_estimate = int((sessions_this_week + warmups_this_week) * 12)

    weekly_goal = 30
    sp = user.skill_profile_json
    if isinstance(sp, dict) and sp.get("weekly_practice_minutes_goal") is not None:
        try:
            weekly_goal = max(5, min(300, int(sp["weekly_practice_minutes_goal"])))
        except (TypeError, ValueError):
            pass

    return {
        "total_sessions": total_sessions,
        "warmup_sessions": warmup_count,
        "average_score": avg_score,
        "practice_streak_days": streak,
        "weekly_practice_minutes_goal": weekly_goal,
        "weekly_practice_minutes_estimate": practice_minutes_estimate,
    }
