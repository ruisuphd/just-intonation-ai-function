import asyncio
import logging

from google.cloud import texttospeech

logger = logging.getLogger(__name__)


class CloudTTSClient:
    def __init__(self) -> None:
        self._client = texttospeech.TextToSpeechClient()

    async def synthesize(
        self,
        text: str,
        voice_name: str = "en-US-Chirp3-HD-Charon",
        output_format: str = "mp3",
    ) -> bytes:
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name=voice_name,
        )
        if output_format.lower() == "wav":
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            )
        else:
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
            )

        def _synthesize() -> bytes:
            response = self._client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            )
            return response.audio_content

        try:
            return await asyncio.to_thread(_synthesize)
        except Exception as e:
            logger.exception("Cloud TTS synthesize failed: %s", e)
            raise


cloud_tts_client = CloudTTSClient()
polly_client = cloud_tts_client
PollyClient = CloudTTSClient
