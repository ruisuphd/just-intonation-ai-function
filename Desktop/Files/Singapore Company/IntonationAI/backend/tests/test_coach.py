from unittest.mock import AsyncMock, patch

import pytest

from app.services.coach.guitar import GuitarCoach
from app.services.coach.piano import PianoCoach
from app.services.coach.vocal import VocalCoach


class TestVocalCoach:
    @pytest.mark.asyncio
    async def test_welcome_message(self):
        coach = VocalCoach()
        msg = await coach.get_welcome_message()
        assert isinstance(msg, str)
        assert len(msg) > 10

    @pytest.mark.asyncio
    async def test_welcome_with_skill_profile_mentions_prior_sessions(self):
        coach = VocalCoach()
        sp = {
            "recent_sessions": [
                {
                    "coach_type": "vocal",
                    "recap_snippet": "worked on breath",
                    "next_step_snippet": "sustain A4",
                    "metrics": {"pitch_stability": 0.7},
                }
            ]
        }
        msg = await coach.get_welcome_message(sp)
        assert "recent sessions" in msg.lower() or "sessions" in msg.lower()

    @pytest.mark.asyncio
    async def test_process_message_includes_session_stage_in_system_prompt(self):
        coach = VocalCoach()
        captured: dict = {}

        async def fake_invoke(*args, **kwargs):
            captured["system_prompt"] = kwargs.get("system_prompt", "")
            return "ok"

        history = [{"role": "user", "content": "first"}]
        with (
            patch(
                "app.services.coach.vocal.gemini_client.invoke",
                new_callable=AsyncMock,
                side_effect=fake_invoke,
            ),
            patch(
                "app.services.coach.vocal.retriever.retrieve_context",
                new_callable=AsyncMock,
                return_value="",
            ),
        ):
            await coach.process_message(
                "hello",
                None,
                history,
                session_stage_hint="Session pacing: TEST_STAGE_HINT_XYZ",
            )
        assert "TEST_STAGE_HINT_XYZ" in captured.get("system_prompt", "")


class TestPianoCoach:
    @pytest.mark.asyncio
    async def test_process_message_returns_reply(self):
        coach = PianoCoach()
        mock_reply = "Play C major with a firm finger, then release."
        with (
            patch(
                "app.services.coach.piano.gemini_client.invoke",
                new_callable=AsyncMock,
                return_value=mock_reply,
            ),
            patch(
                "app.services.coach.piano.retriever.retrieve_context",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "app.services.coach.piano.polly_client.synthesize",
                new_callable=AsyncMock,
                side_effect=Exception("skip TTS"),
            ),
        ):
            result = await coach.process_message("play C major", None, [])
        assert result["reply"] == mock_reply
        assert "reply" in result
        assert "audio_url" in result


class TestGuitarCoach:
    @pytest.mark.asyncio
    async def test_process_message_returns_reply(self):
        coach = GuitarCoach()
        mock_reply = "Try alternating down-up strums on each beat."
        with (
            patch(
                "app.services.coach.guitar.gemini_client.invoke",
                new_callable=AsyncMock,
                return_value=mock_reply,
            ),
            patch(
                "app.services.coach.guitar.retriever.retrieve_context",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "app.services.coach.guitar.polly_client.synthesize",
                new_callable=AsyncMock,
                side_effect=Exception("skip TTS"),
            ),
        ):
            result = await coach.process_message("strum pattern", None, [])
        assert result["reply"] == mock_reply
        assert "reply" in result
        assert "audio_url" in result


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
