from abc import ABC, abstractmethod
from typing import Any


class BaseCoach(ABC):
    coach_type: str

    @abstractmethod
    async def process_message(
        self,
        user_text: str,
        audio_analysis: dict | None,
        session_history: list[dict],
        *,
        use_rag: bool = True,
        audio_bytes: bytes | None = None,
        learner_context: str = "",
        command_hint: str = "",
        session_stage_hint: str = "",
        use_tts: bool = False,
        practice_mode: bool = True,
        locale: str = "en",
    ) -> dict:
        """Returns dict with keys: reply (str), audio_url (str|None), analysis (dict|None)"""
        ...

    @abstractmethod
    async def stream_message(
        self,
        user_text: str,
        audio_analysis: dict | None,
        session_history: list[dict],
        *,
        use_rag: bool = True,
        audio_bytes: bytes | None = None,
        learner_context: str = "",
        command_hint: str = "",
        session_stage_hint: str = "",
        practice_mode: bool = True,
        locale: str = "en",
    ):
        ...

    @abstractmethod
    async def get_welcome_message(
        self,
        skill_profile: dict[str, Any] | None = None,
        *,
        locale: str = "en",
    ) -> str: ...
