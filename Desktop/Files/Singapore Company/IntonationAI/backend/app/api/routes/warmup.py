from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.models import User, WarmupSession
from app.schemas.warmup import WarmupSessionResponse, WarmupScoreSchema
from app.services.entitlement import entitlement_service
from app.services.warmup.engine import warmup_engine
from app.services.audio.analyser import audio_analyser

router = APIRouter(prefix="/warmup", tags=["warmup"])


@router.post("/start", response_model=WarmupSessionResponse)
async def start_warmup(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_essential = await entitlement_service.is_essential(db, user.id)
    session_data = warmup_engine.create_session(
        user_level=1, full_library=is_essential
    )
    db_session = WarmupSession(
        user_id=user.id,
        exercises_json=session_data["exercises"],
        scores_json=[],
    )
    db.add(db_session)
    await db.commit()
    await db.refresh(db_session)

    return WarmupSessionResponse(
        id=str(db_session.id),
        exercises=session_data["exercises"],
        scores=[],
        started_at=db_session.started_at.isoformat(),
        completed_at=None,
    )


@router.post("/{session_id}/score")
async def score_exercise(
    session_id: str,
    exercise_id: str = Form(...),
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    result = await db.execute(
        select(WarmupSession).where(
            WarmupSession.id == session_id,
            WarmupSession.user_id == user.id,
        )
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(404, "Warmup session not found")

    audio_bytes = await audio.read()
    analysis = await audio_analyser.analyse(audio_bytes)

    session_dict = {
        "exercises": ws.exercises_json,
        "scores": ws.scores_json or [],
    }
    updated = await warmup_engine.score_and_advance(session_dict, exercise_id, analysis)

    ws.scores_json = updated["scores"]
    await db.commit()

    latest_score = updated["scores"][-1] if updated["scores"] else {}
    session_data = updated.get("session") or {}
    exercise = next(
        (e for e in session_data.get("exercises", []) if e.get("id") == exercise_id),
        None,
    )
    exercise_name = exercise.get("name", exercise_id) if exercise else exercise_id
    next_ex = updated.get("next_exercise")
    next_name = (
        next_ex.get("name") if isinstance(next_ex, dict) else
        (next_ex if isinstance(next_ex, str) else None)
    )
    commentary = await warmup_engine.get_commentary(
        exercise_name=exercise_name,
        score=latest_score,
        next_exercise_name=next_name,
    )

    return {
        "score": latest_score,
        "commentary": commentary,
        "next_exercise": updated.get("next_exercise"),
    }
