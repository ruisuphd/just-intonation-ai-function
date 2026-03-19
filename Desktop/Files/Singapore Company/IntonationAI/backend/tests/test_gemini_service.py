"""Tests for the GeminiClient service."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services.llm.gemini import GeminiClient


def _make_mock_response(text: str) -> MagicMock:
    response = MagicMock()
    response.text = text
    return response


@pytest.fixture()
def gemini_client_instance():
    """Return a fresh GeminiClient with vertexai.init patched out."""
    with patch("app.services.llm.gemini.vertexai.init"):
        client = GeminiClient()
    return client


class TestGeminiClientTextOnly:
    """(a) Text-only invoke works."""

    def test_invoke_returns_model_text(self, gemini_client_instance):
        mock_response = _make_mock_response("Great tone!")
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with (
            patch("app.services.llm.gemini.vertexai.init"),
            patch(
                "app.services.llm.gemini.GenerativeModel",
                return_value=mock_model,
            ),
        ):
            messages = [{"role": "user", "content": "How is my pitch?"}]
            result = asyncio.get_event_loop().run_until_complete(
                gemini_client_instance.invoke(
                    system_prompt="You are a vocal coach.",
                    messages=messages,
                )
            )

        assert result == "Great tone!"

    def test_invoke_passes_system_instruction(self, gemini_client_instance):
        mock_response = _make_mock_response("OK")
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with (
            patch("app.services.llm.gemini.vertexai.init"),
            patch(
                "app.services.llm.gemini.GenerativeModel",
                return_value=mock_model,
            ) as MockModel,
        ):
            asyncio.get_event_loop().run_until_complete(
                gemini_client_instance.invoke(
                    system_prompt="Be concise.",
                    messages=[{"role": "user", "content": "Hello"}],
                )
            )
            _, kwargs = MockModel.call_args
            assert kwargs.get("system_instruction") == "Be concise."

    def test_invoke_maps_assistant_role_to_model(self, gemini_client_instance):
        """Non-user roles must be mapped to 'model' for Gemini."""
        from vertexai.generative_models import Content, Part

        mock_response = _make_mock_response("reply")
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        captured_contents: list = []

        def capture_generate(contents, **kwargs):
            captured_contents.extend(contents)
            return mock_response

        mock_model.generate_content.side_effect = capture_generate

        with (
            patch("app.services.llm.gemini.vertexai.init"),
            patch(
                "app.services.llm.gemini.GenerativeModel",
                return_value=mock_model,
            ),
        ):
            messages = [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
                {"role": "user", "content": "How are you?"},
            ]
            asyncio.get_event_loop().run_until_complete(
                gemini_client_instance.invoke(
                    system_prompt="sys",
                    messages=messages,
                )
            )

        roles = [c.role for c in captured_contents]
        assert roles == ["user", "model", "user"]


class TestGeminiClientAudioBytes:
    """(b) audio_bytes adds a Part to the last user message."""

    def test_audio_bytes_appended_to_last_user_message(self, gemini_client_instance):
        from vertexai.generative_models import Content, Part

        mock_response = _make_mock_response("Nice vibrato!")
        mock_model = MagicMock()

        captured_contents: list = []

        def capture_generate(contents, **kwargs):
            captured_contents.extend(contents)
            return mock_response

        mock_model.generate_content.side_effect = capture_generate

        with (
            patch("app.services.llm.gemini.vertexai.init"),
            patch(
                "app.services.llm.gemini.GenerativeModel",
                return_value=mock_model,
            ),
        ):
            messages = [{"role": "user", "content": "Analyse my singing"}]
            fake_audio = b"\x00\x01\x02\x03"
            result = asyncio.get_event_loop().run_until_complete(
                gemini_client_instance.invoke(
                    system_prompt="You are a vocal coach.",
                    messages=messages,
                    audio_bytes=fake_audio,
                )
            )

        assert result == "Nice vibrato!"
        assert len(captured_contents) == 1
        last_content: Content = captured_contents[-1]
        # The last user message should have 2 parts: text + audio
        assert len(last_content.parts) == 2

    def test_audio_bytes_not_added_to_non_last_or_non_user_message(
        self, gemini_client_instance
    ):
        """Audio should only be appended to the last message, and only if it's a user message."""
        from vertexai.generative_models import Content

        mock_response = _make_mock_response("reply")
        mock_model = MagicMock()

        captured_contents: list = []

        def capture_generate(contents, **kwargs):
            captured_contents.extend(contents)
            return mock_response

        mock_model.generate_content.side_effect = capture_generate

        with (
            patch("app.services.llm.gemini.vertexai.init"),
            patch(
                "app.services.llm.gemini.GenerativeModel",
                return_value=mock_model,
            ),
        ):
            # Last message is from assistant, not user
            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
            asyncio.get_event_loop().run_until_complete(
                gemini_client_instance.invoke(
                    system_prompt="sys",
                    messages=messages,
                    audio_bytes=b"\xFF\xFE",
                )
            )

        # The last content (assistant/model) should only have 1 part (text only)
        last_content: Content = captured_contents[-1]
        assert len(last_content.parts) == 1
