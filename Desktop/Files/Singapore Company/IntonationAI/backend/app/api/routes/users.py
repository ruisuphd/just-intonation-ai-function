from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.models import CurriculumNode, User, UserProgress
from app.schemas.user import UserProfileUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    badge_result = await db.execute(
        select(CurriculumNode.title, CurriculumNode.slug, CurriculumNode.tier)
        .join(UserProgress, UserProgress.node_id == CurriculumNode.id)
        .where(
            UserProgress.user_id == user.id,
            UserProgress.status == "mastered",
        )
        .order_by(CurriculumNode.sort_order)
    )
    badges = [f"{title} · {tier} ({slug})" for title, slug, tier in badge_result.all() if slug]
    return UserResponse(
        id=str(user.id),
        email=user.email or "",
        display_name=user.display_name or "",
        preferred_locale=user.preferred_locale,
        voice_profile=user.voice_profile_json,
        skill_profile=user.skill_profile_json,
        badges=badges,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.skill_profile is not None:
        user.skill_profile_json = body.skill_profile
    if "preferred_locale" in body.model_fields_set:
        user.preferred_locale = body.preferred_locale
    await db.commit()
    await db.refresh(user)
    return await get_me(user=user, db=db)
