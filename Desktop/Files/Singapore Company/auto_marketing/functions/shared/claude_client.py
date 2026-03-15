"""Backward-compatibility shim. Use GeminiClient from shared.gemini_client directly."""

from shared.gemini_client import GeminiClient as ClaudeClient  # noqa: F401
from shared.gemini_client import GeminiClient  # noqa: F401

__all__ = ["ClaudeClient", "GeminiClient"]
