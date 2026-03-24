from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from shared.gemini_client import (
    TASK_MODEL_MAP,
    GeminiClient,
    _extract_json,
    _resolve_model,
)
from shared.chat_schema import ChatStructuredReply
from shared.models import IntelligenceScoreResult


def test_resolve_model_known_task_base():
    assert (
        _resolve_model("intelligence_scorer", "starter")
        == "gemini-3.1-flash-lite-preview"
    )
    assert (
        _resolve_model("intelligence_scorer", "growth")
        == "gemini-3.1-flash-lite-preview"
    )


def test_resolve_model_known_task_pro():
    assert _resolve_model("linkedin", "pro") == "gemini-3.1-pro-preview"
    assert _resolve_model("icp_qualifier", "pro") == "gemini-3.1-pro-preview"


def test_resolve_model_unknown_task_defaults_to_flash_lite():
    assert _resolve_model("nonexistent_task", "pro") == "gemini-3.1-flash-lite-preview"


def test_resolve_model_flash_lite_tasks_same_on_both_tiers():
    for task in ("intelligence_scorer", "signal_classifier"):
        assert _resolve_model(task, "starter") == _resolve_model(task, "pro")


def test_task_model_map_completeness():
    expected_tasks = {
        "intelligence_scorer",
        "signal_classifier",
        "icp_qualifier",
        "linkedin",
        "instagram",
        "x_twitter",
        "tiktok",
        "reddit_prompt",
        "xiaohongshu",
        "google_business_profile",
        "email_newsletter",
        "outreach",
        "quick_generate",
        "marketing_chat",
        "json_repair",
    }
    assert set(TASK_MODEL_MAP.keys()) == expected_tasks


def test_extract_json_plain():
    assert _extract_json('{"key": "value"}') == {"key": "value"}


def test_extract_json_with_fences():
    raw = '```json\n{"key": "value"}\n```'
    assert _extract_json(raw) == {"key": "value"}


def test_extract_json_bad_input():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("not json at all")


@patch("shared.gemini_client.GeminiClient._get_model")
def test_generate_returns_text(mock_get_model):
    mock_response = MagicMock()
    mock_response.text = "Hello world"
    mock_response.usage_metadata = MagicMock(
        prompt_token_count=10, candidates_token_count=5
    )

    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response
    mock_get_model.return_value = mock_model

    client = GeminiClient()
    result = asyncio.run(
        client.generate("sys", "user", task_name="intelligence_scorer")
    )
    assert result == "Hello world"
    mock_model.generate_content.assert_called_once()


@patch("shared.gemini_client.GeminiClient._get_model")
def test_generate_parses_response_model(mock_get_model):
    payload = {
        "summary": "Test summary",
        "relevance_score": 0.8,
        "relevance_reasoning": "Good",
        "tags": ["ai"],
        "postability_score": 0.7,
        "suggested_angle": "angle",
        "why_now": "because",
    }
    mock_response = MagicMock()
    mock_response.text = json.dumps(payload)
    mock_response.usage_metadata = MagicMock(
        prompt_token_count=50, candidates_token_count=30
    )

    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response
    mock_get_model.return_value = mock_model

    client = GeminiClient()
    result = asyncio.run(
        client.generate(
            "sys",
            "user",
            response_model=IntelligenceScoreResult,
            task_name="intelligence_scorer",
        )
    )
    assert isinstance(result, IntelligenceScoreResult)
    assert result.summary == "Test summary"
    assert result.relevance_score == 0.8


@patch("shared.gemini_client.GeminiClient._get_model")
def test_generate_retries_on_resource_exhausted(mock_get_model):
    exc = Exception("rate limited")
    exc.code = 429

    mock_response = MagicMock()
    mock_response.text = "ok"
    mock_response.usage_metadata = None

    mock_model = MagicMock()
    mock_model.generate_content.side_effect = [exc, mock_response]
    mock_get_model.return_value = mock_model

    client = GeminiClient()
    result = asyncio.run(
        client.generate("sys", "user", task_name="intelligence_scorer")
    )
    assert result == "ok"
    assert mock_model.generate_content.call_count == 2


@patch("shared.gemini_client.GeminiClient._get_model")
def test_generate_raises_on_non_retryable(mock_get_model):
    exc = ValueError("bad request")

    mock_model = MagicMock()
    mock_model.generate_content.side_effect = exc
    mock_get_model.return_value = mock_model

    client = GeminiClient()
    with pytest.raises(ValueError, match="bad request"):
        asyncio.run(client.generate("sys", "user", task_name="intelligence_scorer"))
    assert mock_model.generate_content.call_count == 1


@patch.dict(os.environ, {"GEMINI_ENABLE_MODEL_FALLBACK": "1"}, clear=False)
@patch("shared.gemini_client.GeminiClient._get_model")
def test_generate_fallback_model_after_primary_failure(mock_get_model):
    bad = MagicMock()
    bad.generate_content.side_effect = RuntimeError("primary hard fail")

    ok_payload = {
        "reply": "hello",
        "settings_to_update": {},
        "suggested_questions": ["Q1?"],
    }
    good = MagicMock()
    good_response = MagicMock()
    good_response.text = json.dumps(ok_payload)
    good_response.usage_metadata = None
    good.generate_content.return_value = good_response

    def get_model(model_id: str, _sp: str):
        if model_id == "gemini-3-flash":
            return good
        return bad

    mock_get_model.side_effect = get_model

    client = GeminiClient()
    result = asyncio.run(
        client.generate(
            "sys",
            "user",
            response_model=ChatStructuredReply,
            task_name="marketing_chat",
            enable_json_repair=False,
        )
    )
    assert isinstance(result, ChatStructuredReply)
    assert result.reply == "hello"
    assert bad.generate_content.call_count >= 1
    assert good.generate_content.call_count == 1


@patch("shared.gemini_client.GeminiClient._get_model")
def test_generate_json_repair_after_malformed(mock_get_model):
    payload = {
        "reply": "fixed",
        "settings_to_update": {},
        "suggested_questions": [],
    }
    bad_resp = MagicMock()
    bad_resp.text = "```json\nnot valid\n```"
    bad_resp.usage_metadata = None
    good_resp = MagicMock()
    good_resp.text = json.dumps(payload)
    good_resp.usage_metadata = None

    mock_model = MagicMock()
    mock_model.generate_content.side_effect = [bad_resp, good_resp]
    mock_get_model.return_value = mock_model

    client = GeminiClient()
    result = asyncio.run(
        client.generate(
            "sys",
            "user",
            response_model=ChatStructuredReply,
            task_name="marketing_chat",
        )
    )
    assert isinstance(result, ChatStructuredReply)
    assert result.reply == "fixed"
    assert mock_model.generate_content.call_count == 2
