from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawItem:
    source_url: str
    source_type: str
    source_name: str
    title: str
    raw_content: str
    published_at: datetime | None = None


class SourceAdapter(ABC):
    @abstractmethod
    async def fetch_items(self) -> list[RawItem]: ...
