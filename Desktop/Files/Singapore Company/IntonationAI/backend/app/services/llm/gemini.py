import asyncio
import json
import logging
import queue
import re
import threading

import vertexai
from vertexai.generative_models import Content, GenerativeModel, Part

from app.core.config import settings
from app.services.resilience.circuit_breaker import SlidingWindowBreaker

logger = logging.getLogger(__name__)

_gemini_breaker = SlidingWindowBreaker(
    failure_threshold=settings.GEMINI_CIRCUIT_FAILURE_THRESHOLD,
    open_seconds=settings.GEMINI_CIRCUIT_OPEN_SEC,
)

_TECHNIQUE_PROMPTS = {
    "piano": """You are a piano technique analyst. From the image(s), assess hand position, wrist angle, finger curvature, posture.
Respond with ONLY valid JSON: {"issues": [{"area": str, "detail": str}], "technique_score": number 0-1, "summary": str}.
If the frame does not show hands clearly, use empty issues and technique_score 0.5.""",
    "guitar": """You are a guitar technique analyst. From the image(s), assess fretting hand, thumb placement, wrist, strumming arm posture.
Respond with ONLY valid JSON: {"issues": [{"area": str, "detail": str}], "technique_score": number 0-1, "summary": str}.
If hands are not visible, use empty issues and technique_score 0.5.""",
    "vocal": """You are a vocal technique analyst. From the image(s), assess jaw openness, posture, visible shoulder/neck tension.
Respond with ONLY valid JSON: {"issues": [{"area": str, "detail": str}], "technique_score": number 0-1, "summary": str}.
If the face/posture is not visible, use empty issues and technique_score 0.5.""",
}


class GeminiClient:
    def __init__(self) -> None:
        if not settings.gcp_project:
            raise ValueError("GOOGLE_CLOUD_PROJECT or FIREBASE_PROJECT_ID must be set")
        vertexai.init(
            project=settings.gcp_project,
            location=settings.VERTEX_AI_LOCATION,
        )

    def _contents_for_messages(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int,
        audio_bytes: bytes | None,
    ) -> tuple[GenerativeModel, list[Content], dict]:
        model = GenerativeModel(
            settings.GEMINI_MODEL,
            system_instruction=system_prompt,
        )
        contents: list[Content] = []
        for i, msg in enumerate(messages):
            role = "user" if msg.get("role") == "user" else "model"
            text = msg.get("content", "")
            parts: list[Part] = [Part.from_text(text)]
            is_last = i == len(messages) - 1
            if audio_bytes and is_last and msg.get("role") == "user":
                parts.append(Part.from_data(audio_bytes, "audio/wav"))
            contents.append(Content(role=role, parts=parts))
        generation_config = {"max_output_tokens": max_tokens}
        return model, contents, generation_config

    async def invoke(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 1024,
        audio_bytes: bytes | None = None,
    ) -> str:
        model, contents, generation_config = self._contents_for_messages(
            system_prompt, messages, max_tokens, audio_bytes
        )

        def _generate() -> str:
            response = model.generate_content(
                contents,
                generation_config=generation_config,
            )
            return response.text

        if not _gemini_breaker.allow():
            return (
                "Our AI coach is cooling down after a busy moment. "
                "Please wait a minute and try again."
            )

        try:
            out = await asyncio.wait_for(
                asyncio.to_thread(_generate),
                timeout=settings.COACH_LLM_TIMEOUT_SEC,
            )
            _gemini_breaker.record_success()
            return out
        except TimeoutError:
            logger.warning("Gemini invoke timed out after %ss", settings.COACH_LLM_TIMEOUT_SEC)
            _gemini_breaker.record_failure()
            return (
                "The coach is taking longer than usual. "
                "Try a shorter clip or send again in a moment."
            )
        except Exception as e:
            logger.exception("Gemini invoke failed: %s", e)
            _gemini_breaker.record_failure()
            return "The coach hit a snag. Please try again in a moment."

    async def invoke_stream(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 1024,
        audio_bytes: bytes | None = None,
    ):
        model, contents, generation_config = self._contents_for_messages(
            system_prompt, messages, max_tokens, audio_bytes
        )

        if not _gemini_breaker.allow():
            yield (
                "Our AI coach is cooling down after a busy moment. "
                "Please wait a minute and try again."
            )
            return

        q: queue.Queue = queue.Queue(maxsize=64)
        err_holder: list[BaseException] = []

        def producer() -> None:
            try:
                stream = model.generate_content(
                    contents,
                    generation_config=generation_config,
                    stream=True,
                )
                for chunk in stream:
                    text = getattr(chunk, "text", None) or ""
                    if text:
                        q.put(("t", text))
                q.put(("d", None))
            except BaseException as e:
                err_holder.append(e)
                q.put(("d", None))

        threading.Thread(target=producer, daemon=True).start()
        loop = asyncio.get_event_loop()
        deadline = loop.time() + settings.COACH_LLM_TIMEOUT_SEC
        while True:
            timeout = max(0.0, deadline - loop.time())
            try:
                kind, val = await asyncio.wait_for(
                    asyncio.to_thread(q.get),
                    timeout=timeout,
                )
            except TimeoutError:
                logger.warning(
                    "Gemini stream timed out after %ss",
                    settings.COACH_LLM_TIMEOUT_SEC,
                )
                _gemini_breaker.record_failure()
                yield (
                    "The coach is taking longer than usual. "
                    "Try a shorter clip or send again in a moment."
                )
                return
            if kind == "t":
                yield val
            elif kind == "d":
                break
        if err_holder:
            _gemini_breaker.record_failure()
            logger.exception("Gemini stream failed: %s", err_holder[0])
            yield "The coach hit a snag. Please try again in a moment."
            return
        _gemini_breaker.record_success()

    async def analyse_technique_frames(
        self,
        instrument: str,
        jpeg_frames: list[bytes],
        max_tokens: int = 512,
    ) -> dict:
        prompt = _TECHNIQUE_PROMPTS.get(
            instrument,
            _TECHNIQUE_PROMPTS["piano"],
        )
        model = GenerativeModel(
            settings.GEMINI_MODEL,
            system_instruction=prompt,
        )
        parts: list[Part] = [Part.from_text("Analyse these practice frames.")]
        for raw in jpeg_frames[:6]:
            parts.append(Part.from_data(raw, "image/jpeg"))

        contents = [Content(role="user", parts=parts)]
        generation_config = {"max_output_tokens": max_tokens}

        def _gen() -> dict:
            response = model.generate_content(contents, generation_config=generation_config)
            text = (response.text or "").strip()
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                return {
                    "technique_feedback": {"issues": [], "summary": text[:500]},
                    "technique_score": 0.5,
                }
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                return {
                    "technique_feedback": {"issues": [], "summary": text[:500]},
                    "technique_score": 0.5,
                }
            score = data.get("technique_score", 0.5)
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = 0.5
            score = max(0.0, min(1.0, score))
            return {
                "technique_feedback": {
                    "issues": data.get("issues") or [],
                    "summary": data.get("summary") or "",
                },
                "technique_score": score,
            }

        if not _gemini_breaker.allow():
            return {
                "technique_feedback": {
                    "issues": [],
                    "summary": "Technique analysis temporarily unavailable.",
                },
                "technique_score": 0.5,
            }

        try:
            out = await asyncio.wait_for(
                asyncio.to_thread(_gen),
                timeout=settings.COACH_LLM_TIMEOUT_SEC,
            )
            _gemini_breaker.record_success()
            return out
        except TimeoutError:
            logger.warning("Gemini vision timed out after %ss", settings.COACH_LLM_TIMEOUT_SEC)
            _gemini_breaker.record_failure()
            return {
                "technique_feedback": {"issues": [], "summary": "Technique analysis timed out."},
                "technique_score": 0.5,
            }
        except Exception as e:
            logger.exception("Gemini vision failed: %s", e)
            _gemini_breaker.record_failure()
            return {
                "technique_feedback": {"issues": [], "summary": "Technique analysis unavailable."},
                "technique_score": 0.5,
            }


_gemini_instance: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    global _gemini_instance
    if _gemini_instance is None:
        _gemini_instance = GeminiClient()
    return _gemini_instance


class _GeminiClientProxy:
    def __getattr__(self, name: str):
        return getattr(get_gemini_client(), name)


gemini_client = _GeminiClientProxy()
