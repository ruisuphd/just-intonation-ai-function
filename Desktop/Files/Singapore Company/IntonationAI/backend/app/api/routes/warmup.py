from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_app_check_if_enforced
from app.api.upload_limits import MAX_WARMUP_AUDIO_BYTES, read_upload_bytes
from app.db.base import get_db
from app.db.firestore import firestore_db
from app.models import User, WarmupSession
from app.schemas.warmup import WarmupSessionResponse
from app.services.audio.analyser import audio_analyser
from app.services.entitlement import entitlement_service
from app.services.warmup.engine import warmup_engine

router = APIRouter(prefix="/warmup", tags=["warmup"])


@router.post("/start", response_model=WarmupSessionResponse)
async def start_warmup(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_pro = await entitlement_service.is_pro(db, user.id)
    session_data = warmup_engine.create_session(user_level=1, full_library=is_pro)
    db_session = WarmupSession(
        user_id=user.id,
        exercises_json=session_data["exercises"],
        scores_json=[],
    )
    db.add(db_session)
    await db.commit()
    await db.refresh(db_session)
    await firestore_db.ensure_warmup_session(str(db_session.id), user.firebase_uid)

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
    _app_check: None = Depends(require_app_check_if_enforced),
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

    audio_bytes = await read_upload_bytes(audio, MAX_WARMUP_AUDIO_BYTES)
    analysis = await audio_analyser.analyse(audio_bytes)

    session_dict = {
        "exercises": ws.exercises_json,
        "scores": ws.scores_json or [],
    }
    updated = await warmup_engine.score_and_advance(session_dict, exercise_id, analysis)

    sess = updated.get("session") or {}
    new_scores = sess.get("scores", [])
    ws.scores_json = new_scores
    await db.commit()

    latest_score = new_scores[-1] if new_scores else {}
    session_data = updated.get("session") or {}
    exercise = next(
        (e for e in session_data.get("exercises", []) if e.get("id") == exercise_id),
        None,
    )
    exercise_name = exercise.get("name", exercise_id) if exercise else exercise_id
    next_ex = updated.get("next_exercise")
    next_name = (
        next_ex.get("name")
        if isinstance(next_ex, dict)
        else (next_ex if isinstance(next_ex, str) else None)
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
