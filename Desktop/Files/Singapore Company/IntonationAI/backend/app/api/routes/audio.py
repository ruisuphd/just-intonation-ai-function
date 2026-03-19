from fastapi import APIRouter, Depends, UploadFile, File

from app.api.deps import get_current_user
from app.models import User
from app.schemas.audio import AudioAnalysisResponse
from app.services.audio.analyser import audio_analyser

router = APIRouter(prefix="/audio", tags=["audio"])


@router.post("/analyse", response_model=AudioAnalysisResponse)
async def analyse_audio(
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    audio_bytes = await audio.read()
    result = await audio_analyser.analyse(audio_bytes)
    return AudioAnalysisResponse(**result)
