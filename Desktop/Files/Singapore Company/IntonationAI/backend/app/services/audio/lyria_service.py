"""
Vertex AI Lyria backing track generation.
Falls back to pre-recorded metronome when Lyria fails or times out.
"""

import asyncio
import base64
import json
import logging
import uuid

import google.auth
import google.auth.transport.requests

from app.core.config import settings
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

LYRIA_MODEL = "lyria-002"
FALLBACK_BACKING_PATH = "backing/fallback/metronome.mp3"
REQUEST_TIMEOUT = 15


async def generate_backing_track(
    tempo_bpm: int,
    key: str,
    style: str,
    duration_seconds: int = 30,
) -> str:
    prompt = (
        f"{tempo_bpm} BPM {style} backing track in {key}, "
        f"instrumental only, {duration_seconds} seconds"
    )

    try:
        return await asyncio.wait_for(
            _call_lyria(prompt),
            timeout=REQUEST_TIMEOUT,
        )
    except TimeoutError:
        logger.warning("Lyria request timed out after %ds", REQUEST_TIMEOUT)
        return await _fallback_url()
    except Exception as e:
        logger.exception("Lyria generation failed: %s", e)
        return await _fallback_url()


async def _call_lyria(prompt: str) -> str:
    def _predict() -> bytes:
        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        token = credentials.token

        url = (
            f"https://{settings.VERTEX_AI_LOCATION}-aiplatform.googleapis.com/v1/"
            f"projects/{settings.gcp_project}/locations/{settings.VERTEX_AI_LOCATION}"
            f"/publishers/google/models/{LYRIA_MODEL}:predict"
        )
        body = {
            "instances": [{"prompt": prompt, "negative_prompt": "vocals, lyrics"}],
            "parameters": {"sample_count": 1},
        }

        import urllib.request

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())

        predictions = data.get("predictions", [])
        if not predictions:
            raise ValueError("No predictions returned")
        audio_b64 = predictions[0].get("audioContent")
        if not audio_b64:
            raise ValueError("No audioContent in prediction")
        return base64.b64decode(audio_b64)

    wav_bytes = await asyncio.to_thread(_predict)
    key = f"backing/{uuid.uuid4()}.wav"
    return await storage_service.upload(wav_bytes, key, "audio/wav")


async def _fallback_url() -> str:
    if not storage_service._client or not storage_service._bucket_name:
        return ""
    try:
        from datetime import timedelta

        bucket = storage_service._client.bucket(storage_service._bucket_name)
        blob = bucket.blob(FALLBACK_BACKING_PATH)
        if blob.exists():
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=1),
                method="GET",
            )
    except Exception as e:
        logger.debug("Fallback metronome URL failed: %s", e)
    return ""
