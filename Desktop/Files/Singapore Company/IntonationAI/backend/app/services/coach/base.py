from abc import ABC, abstractmethod


class BaseCoach(ABC):
    coach_type: str

    @abstractmethod
    async def process_message(
        self,
        user_text: str,
        audio_analysis: dict | None,
        session_history: list[dict],
    ) -> dict:
        """Returns dict with keys: reply (str), audio_url (str|None), analysis (dict|None)"""
        ...

    @abstractmethod
    async def get_welcome_message(self) -> str:
        ...
