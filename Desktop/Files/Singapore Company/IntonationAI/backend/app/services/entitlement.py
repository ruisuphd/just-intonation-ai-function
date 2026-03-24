from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subscription, Usage

FREE_COACH_SESSIONS_PER_WEEK = 3


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _resolve_tz(name: str | None) -> ZoneInfo:
    if name:
        try:
            return ZoneInfo(name.strip())
        except Exception:
            pass
    return ZoneInfo("UTC")


def _usage_week_start(timezone_name: str | None) -> date:
    tz = _resolve_tz(timezone_name)
    today = datetime.now(tz).date()
    return _week_start(today)


class EntitlementService:
    async def _get_active_subscription(
        self, db: AsyncSession, user_id: UUID
    ) -> Subscription | None:
        result = await db.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.stripe_sub_id.isnot(None),
            )
        )
        sub = result.scalar_one_or_none()
        if not sub or not sub.current_period_end:
            return None
        now = datetime.now(UTC)
        end = sub.current_period_end
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        return sub if end >= now else None

    async def is_pro(self, db: AsyncSession, user_id: UUID) -> bool:
        sub = await self._get_active_subscription(db, user_id)
        return sub is not None and sub.plan == "pro"

    async def can_use_lyria(self, db: AsyncSession, user_id: UUID) -> bool:
        return await self.is_pro(db, user_id)

    async def remaining_free_sessions(
        self,
        db: AsyncSession,
        user_id: UUID,
        *,
        timezone_name: str | None = None,
    ) -> int:
        if await self.is_pro(db, user_id):
            return -1
        week_start = _usage_week_start(timezone_name)
        result = await db.execute(
            select(Usage).where(Usage.user_id == user_id, Usage.period_start == week_start)
        )
        row = result.scalar_one_or_none()
        used = row.coach_sessions_count if row else 0
        return max(0, FREE_COACH_SESSIONS_PER_WEEK - used)

    async def increment_coach_usage(
        self,
        db: AsyncSession,
        user_id: UUID,
        *,
        timezone_name: str | None = None,
    ) -> None:
        if await self.is_pro(db, user_id):
            return
        week_start = _usage_week_start(timezone_name)
        stmt = (
            insert(Usage)
            .values(
                user_id=user_id,
                period_start=week_start,
                coach_sessions_count=1,
            )
            .on_conflict_do_update(
                constraint="uq_usage_user_period",
                set_={"coach_sessions_count": Usage.coach_sessions_count + 1},
            )
        )
        await db.execute(stmt)

    async def check_coach_access(
        self,
        db: AsyncSession,
        user_id: UUID,
        coach_type: str | None = None,
        *,
        timezone_name: str | None = None,
    ) -> tuple[bool, str | None]:
        if await self.is_pro(db, user_id):
            return True, None
        if coach_type in ("piano", "guitar"):
            return False, "Piano and guitar coaches require Pro. Upgrade to unlock."
        remaining = await self.remaining_free_sessions(db, user_id, timezone_name=timezone_name)
        if remaining > 0:
            return True, None
        return False, "Free tier limit reached. Upgrade to Pro for unlimited sessions."

    async def reserve_coach_session(
        self,
        db: AsyncSession,
        user_id: UUID,
        coach_type: str,
        *,
        timezone_name: str | None = None,
    ) -> tuple[bool, str | None]:
        """Atomically check free-tier limits and increment usage (call within one transaction)."""
        if await self.is_pro(db, user_id):
            return True, None
        if coach_type in ("piano", "guitar"):
            return False, "Piano and guitar coaches require Pro. Upgrade to unlock."
        week_start = _usage_week_start(timezone_name)
        await db.execute(
            insert(Usage)
            .values(
                user_id=user_id,
                period_start=week_start,
                coach_sessions_count=0,
            )
            .on_conflict_do_nothing(constraint="uq_usage_user_period")
        )
        await db.flush()
        result = await db.execute(
            select(Usage)
            .where(Usage.user_id == user_id, Usage.period_start == week_start)
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if not row:
            return False, "Unable to reserve session."
        used = row.coach_sessions_count or 0
        if used >= FREE_COACH_SESSIONS_PER_WEEK:
            return False, "Free tier limit reached. Upgrade to Pro for unlimited sessions."
        row.coach_sessions_count = used + 1
        await db.flush()
        return True, None


entitlement_service = EntitlementService()
