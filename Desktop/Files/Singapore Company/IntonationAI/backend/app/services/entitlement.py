from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models import Subscription, Usage

FREE_COACH_SESSIONS_PER_WEEK = 3


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


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
        now = datetime.now(timezone.utc)
        end = sub.current_period_end
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return sub if end >= now else None

    async def is_essential(self, db: AsyncSession, user_id: UUID) -> bool:
        sub = await self._get_active_subscription(db, user_id)
        return sub is not None and sub.plan in ("essential", "pro")

    async def is_pro(self, db: AsyncSession, user_id: UUID) -> bool:
        sub = await self._get_active_subscription(db, user_id)
        return sub is not None and sub.plan == "pro"

    async def can_use_lyria(self, db: AsyncSession, user_id: UUID) -> bool:
        return await self.is_pro(db, user_id)

    async def remaining_free_sessions(
        self, db: AsyncSession, user_id: UUID
    ) -> int:
        if await self.is_essential(db, user_id):
            return -1
        week_start = _week_start(date.today())
        result = await db.execute(
            select(Usage).where(
                Usage.user_id == user_id, Usage.period_start == week_start
            )
        )
        row = result.scalar_one_or_none()
        used = row.coach_sessions_count if row else 0
        return max(0, FREE_COACH_SESSIONS_PER_WEEK - used)

    async def increment_coach_usage(
        self, db: AsyncSession, user_id: UUID
    ) -> None:
        if await self.is_essential(db, user_id):
            return
        week_start = _week_start(date.today())
        stmt = insert(Usage).values(
            user_id=user_id,
            period_start=week_start,
            coach_sessions_count=1,
        ).on_conflict_do_update(
            constraint="uq_usage_user_period",
            set_={"coach_sessions_count": Usage.coach_sessions_count + 1},
        )
        await db.execute(stmt)

    async def check_coach_access(
        self, db: AsyncSession, user_id: UUID, coach_type: str | None = None
    ) -> tuple[bool, str | None]:
        if await self.is_essential(db, user_id):
            return True, None
        if coach_type in ("piano", "guitar"):
            return False, "Piano and guitar coaches require Essential or Pro. Upgrade to unlock."
        remaining = await self.remaining_free_sessions(db, user_id)
        if remaining > 0:
            return True, None
        return False, "Free tier limit reached. Upgrade for unlimited sessions."


entitlement_service = EntitlementService()
