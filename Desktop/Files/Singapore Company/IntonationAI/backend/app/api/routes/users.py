from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.models import User
from app.schemas.user import UserResponse, UserProfileUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse(
        id=str(user.id),
        email=user.email or "",
        display_name=user.display_name or "",
        voice_profile=user.voice_profile_json,
        skill_profile=user.skill_profile_json,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.skill_profile is not None:
        user.skill_profile_json = body.skill_profile
    await db.commit()
    await db.refresh(user)
    return UserResponse(
        id=str(user.id),
        email=user.email or "",
        display_name=user.display_name or "",
        voice_profile=user.voice_profile_json,
        skill_profile=user.skill_profile_json,
    )
