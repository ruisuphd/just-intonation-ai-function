from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import get_current_user, require_app_check_if_enforced
from app.api.upload_limits import MAX_STANDALONE_AUDIO_BYTES, read_upload_bytes
from app.models import User
from app.schemas.audio import AudioAnalysisResponse
from app.services.audio.analyser import audio_analyser

router = APIRouter(prefix="/audio", tags=["audio"])


@router.post("/analyse", response_model=AudioAnalysisResponse)
async def analyse_audio(
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
    _app_check: None = Depends(require_app_check_if_enforced),
):
    audio_bytes = await read_upload_bytes(audio, MAX_STANDALONE_AUDIO_BYTES)
    result = await audio_analyser.analyse(audio_bytes)
    return AudioAnalysisResponse(**result)
