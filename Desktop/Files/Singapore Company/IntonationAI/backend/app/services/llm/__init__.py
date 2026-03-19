from app.services.llm.bedrock import BedrockClient, bedrock_client
from app.services.llm.prompts import (
    GUITAR_COACH_PROMPT,
    PIANO_COACH_PROMPT,
    VOCAL_COACH_PROMPT,
    WARMUP_COMMENTARY_PROMPT,
)

__all__ = [
    "BedrockClient",
    "bedrock_client",
    "VOCAL_COACH_PROMPT",
    "PIANO_COACH_PROMPT",
    "GUITAR_COACH_PROMPT",
    "WARMUP_COMMENTARY_PROMPT",
]
