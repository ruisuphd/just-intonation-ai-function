from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.firestore import firestore_db
from app.models import User, Session, SessionMessage
from app.schemas.coach import (
    CoachMessageResponse,
    CoachSessionCreate,
    CoachSessionResponse,
)
from app.services.coach.vocal import VocalCoach
from app.services.coach.piano import PianoCoach
from app.services.coach.guitar import GuitarCoach
from app.services.audio.analyser import audio_analyser
from app.services.audio.processor import webm_to_wav_bytes
from app.services.entitlement import entitlement_service
from app.services.stt.transcribe import transcribe_client
from app.services.llm.gemini import gemini_client
from app.services.llm.prompts import SESSION_RECAP_PROMPT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coach", tags=["coach"])

_coaches = {
    "vocal": VocalCoach(),
    "piano": PianoCoach(),
    "guitar": GuitarCoach(),
}


@router.post("/sessions", response_model=CoachSessionResponse)
async def create_session(
    body: CoachSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    coach = _coaches.get(body.coach_type)
    if not coach:
        raise HTTPException(400, f"Unknown coach type: {body.coach_type}")

    allowed, msg = await entitlement_service.check_coach_access(db, user.id)
    if not allowed:
        raise HTTPException(
            403,
            msg or "Upgrade to Pro for unlimited sessions.",
        )

    await entitlement_service.increment_coach_usage(db, user.id)

    session = Session(user_id=user.id, coach_type=body.coach_type)
    db.add(session)
    await db.flush()

    welcome = await coach.get_welcome_message()

    msg = SessionMessage(session_id=session.id, role="coach", content=welcome)
    db.add(msg)
    await db.commit()
    await db.refresh(session)

    await firestore_db.add_message(str(session.id), "coach", welcome)

    return CoachSessionResponse(
        id=str(session.id),
        coach_type=session.coach_type,
        started_at=session.started_at.isoformat(),
        ended_at=None,
    )


@router.post("/{session_id}/end")
async def end_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException
    from sqlalchemy import update
    from datetime import datetime

    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    messages = await firestore_db.get_messages(session_id)
    conversation = "\n".join(
        f"{m.get('role', '')}: {m.get('content', '')}" for m in messages
    )
    if not conversation.strip():
        return {"recap": "Session ended.", "next_step": "Start a new session to get feedback."}

    prompt = SESSION_RECAP_PROMPT.format(conversation=conversation)
    try:
        response = await gemini_client.invoke(
            system_prompt="You are a concise vocal coach.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
        )
    except Exception as e:
        logger.exception("Recap generation failed: %s", e)
        return {"recap": "Session ended.", "next_step": "Keep practicing!"}

    lines = [s.strip() for s in response.strip().split("\n") if s.strip()]
    recap = lines[0] if lines else "Session ended."
    next_step = lines[1] if len(lines) > 1 else "Keep practicing!"

    await firestore_db.save_session_recap(session_id, recap, next_step)
    await db.execute(
        update(Session).where(Session.id == session.id).values(ended_at=datetime.utcnow())
    )
    await db.commit()

    return {"recap": recap, "next_step": next_step}


@router.post("/{session_id}/message", response_model=CoachMessageResponse)
async def send_message(
    session_id: str,
    content: str = Form(...),
    audio: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    user_msg = SessionMessage(session_id=session.id, role="user", content=content)
    db.add(user_msg)

    await firestore_db.add_message(session_id, "user", content)

    history = await firestore_db.get_messages(session_id)
    if not history:
        history_result = await db.execute(
            select(SessionMessage)
            .where(SessionMessage.session_id == session.id)
            .order_by(SessionMessage.created_at)
        )
        history = [
            {"role": m.role, "content": m.content}
            for m in history_result.scalars().all()
        ]

    audio_analysis = None
    audio_bytes: bytes | None = None
    if audio and audio.filename:
        try:
            audio_bytes = await audio.read()
            if len(audio_bytes) >= 512 and await entitlement_service.is_pro(db, user.id):
                audio_analysis = await audio_analyser.analyse(audio_bytes)
                if session.coach_type == "vocal":
                    try:
                        stt_bytes = (
                            audio_bytes
                            if audio_bytes[:4] == b"RIFF"
                            else webm_to_wav_bytes(audio_bytes)
                        )
                        transcript = await transcribe_client.transcribe(
                            stt_bytes, sample_rate=44100
                        )
                        if transcript:
                            audio_analysis = {**audio_analysis, "transcript": transcript}
                    except Exception as e:
                        logger.debug("STT skipped: %s", e)
        except Exception as e:
            logger.exception("Audio analysis failed: %s", e)

    coach = _coaches.get(session.coach_type, _coaches["vocal"])
    is_pro = await entitlement_service.is_pro(db, user.id)
    if session.coach_type == "vocal":
        response = await coach.process_message(
            content, audio_analysis, history, use_rag=is_pro, audio_bytes=audio_bytes
        )
    else:
        response = await coach.process_message(content, audio_analysis, history)

    coach_msg = SessionMessage(
        session_id=session.id,
        role="coach",
        content=response["reply"],
        audio_url=response.get("audio_url"),
        analysis_json=response.get("analysis"),
    )
    db.add(coach_msg)
    await db.commit()

    await firestore_db.add_message(
        session_id, "coach", response["reply"],
        audio_url=response.get("audio_url"),
        analysis=response.get("analysis"),
    )

    return CoachMessageResponse(
        reply=response["reply"],
        audio_url=response.get("audio_url"),
        analysis=response.get("analysis"),
    )


@router.websocket("/stream/{session_id}")
async def coach_stream(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()
            try:
                analysis = await audio_analyser.analyse(data)
                await websocket.send_json({"type": "analysis", "data": analysis})
            except Exception as e:
                logger.error("Stream analysis error: %s", e)
                await websocket.send_json({"type": "error", "message": str(e)})
    except WebSocketDisconnect:
        logger.info("Coach stream disconnected for session %s", session_id)
