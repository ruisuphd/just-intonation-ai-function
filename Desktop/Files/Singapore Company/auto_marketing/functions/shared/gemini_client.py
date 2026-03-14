from __future__ import annotations

import asyncio
import json
import os
import random
import time
from typing import TypeVar

from pydantic import BaseModel

from shared.gcp_auth import get_google_credentials
from shared.logger import get_logger

logger = get_logger("gemini_client")

T = TypeVar("T", bound=BaseModel)

_FLASH_LITE = "gemini-3.1-flash-lite-preview"
_PRO = "gemini-3.1-pro-preview"
_FALLBACK_MODEL = "gemini-3-flash"

TASK_MODEL_MAP: dict[str, dict[str, str]] = {
    "intelligence_scorer": {"starter": _FLASH_LITE, "pro": _FLASH_LITE},
    "signal_classifier": {"starter": _FLASH_LITE, "pro": _FLASH_LITE},
    "icp_qualifier": {"starter": _FLASH_LITE, "pro": _PRO},
    "linkedin": {"starter": _FLASH_LITE, "pro": _PRO},
    "instagram": {"starter": _FLASH_LITE, "pro": _PRO},
    "x_twitter": {"starter": _FLASH_LITE, "pro": _PRO},
    "tiktok": {"starter": _FLASH_LITE, "pro": _PRO},
    "reddit_prompt": {"starter": _FLASH_LITE, "pro": _PRO},
    "xiaohongshu": {"starter": _FLASH_LITE, "pro": _PRO},
    "google_business_profile": {"starter": _FLASH_LITE, "pro": _PRO},
    "email_newsletter": {"starter": _FLASH_LITE, "pro": _PRO},
    "outreach": {"starter": _FLASH_LITE, "pro": _PRO},
    "quick_generate": {"starter": _FLASH_LITE, "pro": _PRO},
}

_MAX_RETRIES = 3
_BASE_DELAY = 2.0
_MAX_DELAY = 60.0


def _resolve_model(task_name: str, tier: str) -> str:
    tier_key = "pro" if tier == "pro" else "starter"
    mapping = TASK_MODEL_MAP.get(task_name)
    if mapping:
        return mapping[tier_key]
    return _FLASH_LITE


def _extract_json(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return json.loads(stripped)


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    exc_name = type(exc).__name__
    if exc_name in ("ResourceExhausted", "ServiceUnavailable"):
        return True
    if isinstance(status, int) and status in {429, 500, 503}:
        return True
    return False


class GeminiClient:
    def __init__(self):
        self.project_id = os.getenv("GCP_PROJECT_ID")
        self.region = os.getenv("GEMINI_REGION", "global")

    def _get_model(self, model_id: str, system_prompt: str):
        import vertexai
        from vertexai.generative_models import GenerativeModel

        creds, project, _ = get_google_credentials(require_quota_project=True)
        vertexai.init(
            project=project or self.project_id, location=self.region, credentials=creds
        )
        return GenerativeModel(model_id, system_instruction=[system_prompt])

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_model: type[T] | None = None,
        task_name: str = "",
        tier: str = "starter",
    ) -> T | str:
        from vertexai.generative_models import GenerationConfig

        model_id = _resolve_model(task_name, tier) if task_name else _FLASH_LITE
        model = self._get_model(model_id, system_prompt)
        config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json"
            if response_model is not None
            else "text/plain",
        )

        retry_count = 0
        last_exc: Exception | None = None

        while retry_count <= _MAX_RETRIES:
            t0 = time.monotonic()
            try:
                response = model.generate_content(
                    user_message, generation_config=config
                )
                latency_ms = round((time.monotonic() - t0) * 1000)
                text = response.text

                usage = getattr(response, "usage_metadata", None)
                tokens_in = getattr(usage, "prompt_token_count", 0) if usage else 0
                tokens_out = getattr(usage, "candidates_token_count", 0) if usage else 0

                logger.info(
                    "gemini.call",
                    extra={
                        "task_name": task_name or "unspecified",
                        "model": model_id,
                        "tier": tier,
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "latency_ms": latency_ms,
                        "retry_count": retry_count,
                    },
                )

                if response_model is not None:
                    parsed = _extract_json(text)
                    return response_model.model_validate(parsed)
                return text

            except Exception as exc:
                latency_ms = round((time.monotonic() - t0) * 1000)
                last_exc = exc

                if _is_retryable(exc) and retry_count < _MAX_RETRIES:
                    delay = min(
                        _BASE_DELAY * (2**retry_count) + random.uniform(0, 1),
                        _MAX_DELAY,
                    )
                    logger.warning(
                        "gemini.retry",
                        extra={
                            "task_name": task_name or "unspecified",
                            "model": model_id,
                            "error": str(exc),
                            "retry_count": retry_count + 1,
                            "delay_s": round(delay, 2),
                            "latency_ms": latency_ms,
                        },
                    )
                    await asyncio.sleep(delay)
                    retry_count += 1
                else:
                    logger.error(
                        "gemini.error",
                        extra={
                            "task_name": task_name or "unspecified",
                            "model": model_id,
                            "error": str(exc),
                            "latency_ms": latency_ms,
                            "retry_count": retry_count,
                        },
                    )
                    raise

        raise last_exc  # type: ignore[misc]
