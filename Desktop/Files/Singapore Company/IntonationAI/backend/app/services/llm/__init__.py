from app.services.llm.bedrock import BedrockClient
from app.services.llm.prompts import (
    GUITAR_COACH_PROMPT,
    PIANO_COACH_PROMPT,
    VOCAL_COACH_PROMPT,
    WARMUP_COMMENTARY_PROMPT,
)

__all__ = [
    "BedrockClient",
    "VOCAL_COACH_PROMPT",
    "PIANO_COACH_PROMPT",
    "GUITAR_COACH_PROMPT",
    "WARMUP_COMMENTARY_PROMPT",
]
