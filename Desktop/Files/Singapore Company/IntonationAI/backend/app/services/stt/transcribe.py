import asyncio
import logging
from collections.abc import AsyncIterator

from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech

from app.core.config import settings

logger = logging.getLogger(__name__)


class CloudSTTClient:
    def __init__(self) -> None:
        project_id = settings.gcp_project
        if not project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT or FIREBASE_PROJECT_ID must be set")
        self._client = SpeechClient()
        self._recognizer = (
            f"projects/{project_id}/locations/{settings.GCP_REGION}/recognizers/_"
        )

    async def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate: int = 44100,
        language: str = "en-US",
    ) -> str:
        if audio_bytes[:4] == b"RIFF":
            decoding_config = cloud_speech.RecognitionConfig(
                auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                language_codes=[language],
                model="chirp_2",
            )
        else:
            decoding_config = cloud_speech.RecognitionConfig(
                explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
                    encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=sample_rate,
                ),
                language_codes=[language],
                model="chirp_2",
            )

        def _recognize() -> str:
            response = self._client.recognize(
                recognizer=self._recognizer,
                config=decoding_config,
                content=audio_bytes,
            )
            parts: list[str] = []
            for result in response.results:
                for alt in result.alternatives:
                    if alt.transcript:
                        parts.append(alt.transcript)
            return " ".join(parts)

        try:
            return await asyncio.to_thread(_recognize)
        except Exception as e:
            logger.exception("Cloud STT transcribe failed: %s", e)
            raise

    async def transcribe_streaming(self, audio_chunks: AsyncIterator[bytes]) -> None:
        raise NotImplementedError(
            "TODO: Implement streaming transcription via gRPC bidirectional StreamingRecognize"
        )


cloud_stt_client = CloudSTTClient()
transcribe_client = cloud_stt_client
TranscribeClient = CloudSTTClient
