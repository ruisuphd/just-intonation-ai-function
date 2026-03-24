from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import threading
import time
from queue import Queue
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from shared.gcp_auth import get_google_credentials
from shared.logger import get_logger

logger = get_logger("gemini_client")

T = TypeVar("T", bound=BaseModel)

_FLASH_LITE = "gemini-3.1-flash-lite-preview"
_PRO = "gemini-3.1-pro-preview"
_FALLBACK_MODEL = "gemini-3-flash"

_FALLBACK_TASK_NAMES = frozenset({"marketing_chat", "quick_generate"})

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
    "marketing_chat": {"starter": _FLASH_LITE, "pro": _FLASH_LITE},
    "json_repair": {"starter": _FLASH_LITE, "pro": _FLASH_LITE},
}

_MAX_RETRIES = 3
_BASE_DELAY = 2.0
_MAX_DELAY = 60.0

_MODEL_CACHE_MAX = 48

_vertex_lock = threading.Lock()
_vertex_initialized: tuple[str, str] | None = None

_model_lock = threading.Lock()
_model_cache: dict[tuple[str, str], Any] = {}


def _system_prompt_digest(system_prompt: str) -> str:
    return hashlib.sha256(system_prompt.encode()).hexdigest()[:32]


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


def _model_fallback_enabled(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    v = os.getenv("GEMINI_ENABLE_MODEL_FALLBACK", "").strip().lower()
    return v in ("1", "true", "yes")


def _capture_healing_event(message: str, **tags: str) -> None:
    try:
        import sentry_sdk

        with sentry_sdk.new_scope() as scope:
            for k, v in tags.items():
                scope.set_tag(k, v)
            scope.capture_message(message, level="warning")
    except Exception:
        pass


def _ensure_vertex_initialized(project_id: str | None, region: str) -> None:
    global _vertex_initialized

    creds, project, _ = get_google_credentials(require_quota_project=True)
    resolved_project = project or project_id
    if not resolved_project:
        raise RuntimeError(
            "GCP_PROJECT_ID (or quota project) is required for Vertex AI"
        )

    key = (resolved_project, region)
    with _vertex_lock:
        if _vertex_initialized == key:
            return
        import vertexai

        vertexai.init(project=resolved_project, location=region, credentials=creds)
        _vertex_initialized = key


class GeminiClient:
    def __init__(self):
        self.project_id = os.getenv("GCP_PROJECT_ID")
        self.region = os.getenv("GEMINI_REGION", "global")

    def _get_model(self, model_id: str, system_prompt: str):
        from vertexai.generative_models import GenerativeModel

        _ensure_vertex_initialized(self.project_id, self.region)
        cache_key = (model_id, _system_prompt_digest(system_prompt))
        with _model_lock:
            cached = _model_cache.get(cache_key)
            if cached is not None:
                return cached
            model = GenerativeModel(model_id, system_instruction=[system_prompt])
            if len(_model_cache) >= _MODEL_CACHE_MAX:
                _model_cache.pop(next(iter(_model_cache)))
            _model_cache[cache_key] = model
            return model

    async def _repair_structured_output(
        self,
        raw_text: str,
        validation_error: str,
        response_model: type[T],
        tier: str,
    ) -> T | None:
        schema_hint = json.dumps(response_model.model_json_schema(), default=str)[:6000]
        system = (
            "You fix broken JSON. Output ONLY a single JSON object, no markdown fences, "
            "no commentary. The output must satisfy this JSON Schema:\n" + schema_hint
        )
        user = f"Validation error:\n{validation_error[:800]}\n\nBroken model output:\n{raw_text[:12000]}"
        try:
            return await self.generate(
                system,
                user,
                response_model=response_model,
                task_name="json_repair",
                tier=tier,
                temperature=0.2,
                max_tokens=1024,
                enable_json_repair=False,
                enable_model_fallback=False,
            )
        except Exception:
            return None

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
        enable_json_repair: bool | None = None,
        enable_model_fallback: bool | None = None,
    ) -> T | str:
        from vertexai.generative_models import GenerationConfig

        if enable_json_repair is None:
            do_repair = response_model is not None
        else:
            do_repair = enable_json_repair and response_model is not None

        fb_allowed = _model_fallback_enabled(enable_model_fallback)
        primary_id = _resolve_model(task_name, tier) if task_name else _FLASH_LITE
        models_to_try = [primary_id]
        if (
            fb_allowed
            and task_name in _FALLBACK_TASK_NAMES
            and primary_id != _FALLBACK_MODEL
        ):
            models_to_try.append(_FALLBACK_MODEL)

        last_exc: Exception | None = None

        for model_idx, model_id in enumerate(models_to_try):
            model = self._get_model(model_id, system_prompt)
            config = GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json"
                if response_model is not None
                else "text/plain",
            )

            for retry_count in range(_MAX_RETRIES + 1):
                t0 = time.monotonic()
                try:

                    def _call() -> Any:
                        return model.generate_content(
                            user_message, generation_config=config
                        )

                    response = await asyncio.to_thread(_call)
                    latency_ms = round((time.monotonic() - t0) * 1000)
                    text = response.text

                    usage = getattr(response, "usage_metadata", None)
                    tokens_in = getattr(usage, "prompt_token_count", 0) if usage else 0
                    tokens_out = (
                        getattr(usage, "candidates_token_count", 0) if usage else 0
                    )

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
                            "model_fallback": model_idx > 0,
                        },
                    )

                    if response_model is None:
                        if model_idx > 0:
                            _capture_healing_event(
                                "gemini.model_fallback_success",
                                task_name=task_name or "unspecified",
                                model=model_id,
                            )
                        return text

                    try:
                        parsed = _extract_json(text)
                        validated = response_model.model_validate(parsed)
                        if model_idx > 0:
                            _capture_healing_event(
                                "gemini.model_fallback_success",
                                task_name=task_name or "unspecified",
                                model=model_id,
                            )
                        return validated
                    except (json.JSONDecodeError, ValidationError) as parse_exc:
                        if do_repair:
                            repaired = await self._repair_structured_output(
                                text,
                                str(parse_exc),
                                response_model,
                                tier,
                            )
                            if repaired is not None:
                                logger.warning(
                                    "gemini.json_repair_success",
                                    extra={
                                        "task_name": task_name or "unspecified",
                                        "model": model_id,
                                    },
                                )
                                _capture_healing_event(
                                    "gemini.json_repair_success",
                                    task_name=task_name or "unspecified",
                                    model=model_id,
                                )
                                if model_idx > 0:
                                    _capture_healing_event(
                                        "gemini.model_fallback_success",
                                        task_name=task_name or "unspecified",
                                        model=model_id,
                                    )
                                return repaired
                        logger.error(
                            "chat.parse_repair_failed",
                            extra={
                                "task_name": task_name or "unspecified",
                                "model": model_id,
                                "error": str(parse_exc),
                            },
                        )
                        _capture_healing_event(
                            "chat.parse_repair_failed",
                            task_name=task_name or "unspecified",
                            model=model_id,
                        )
                        raise parse_exc

                except (json.JSONDecodeError, ValidationError):
                    raise

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
                        if model_idx < len(models_to_try) - 1:
                            logger.warning(
                                "gemini.trying_fallback_model",
                                extra={
                                    "task_name": task_name or "unspecified",
                                    "from_model": model_id,
                                    "to_model": models_to_try[model_idx + 1],
                                },
                            )
                            _capture_healing_event(
                                "gemini.model_fallback_attempt",
                                task_name=task_name or "unspecified",
                                from_model=model_id,
                                to_model=models_to_try[model_idx + 1],
                            )
                        break

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("gemini.generate: exhausted without result")

    async def generate_stream_text(
        self,
        system_prompt: str,
        user_message: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        task_name: str = "",
        tier: str = "starter",
        response_mime_json: bool = False,
    ):
        """Yield text chunks from Vertex; does not block the event loop."""
        from vertexai.generative_models import GenerationConfig

        model_id = _resolve_model(task_name, tier) if task_name else _FLASH_LITE
        model = self._get_model(model_id, system_prompt)
        config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json"
            if response_mime_json
            else "text/plain",
        )

        out: Queue[str | BaseException | None] = Queue()

        def producer() -> None:
            try:
                stream = model.generate_content(
                    user_message,
                    generation_config=config,
                    stream=True,
                )
                for chunk in stream:
                    t = getattr(chunk, "text", None)
                    if t:
                        out.put(t)
                out.put(None)
            except BaseException as exc:
                out.put(exc)

        threading.Thread(target=producer, daemon=True).start()

        while True:
            item = await asyncio.to_thread(out.get)
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            yield item
