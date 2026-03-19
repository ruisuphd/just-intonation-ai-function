import asyncio
import logging
from typing import Any

from google.cloud import firestore

from app.core.config import settings

logger = logging.getLogger(__name__)


class FirestoreDB:
    def __init__(self) -> None:
        self._client: firestore.Client | None = None
        if settings.gcp_project:
            try:
                self._client = firestore.Client(project=settings.gcp_project)
            except Exception as e:
                logger.warning("Firestore client init failed: %s", e)
        else:
            logger.info("Firestore disabled (no gcp_project in dev mode)")

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        audio_url: str | None = None,
        analysis: dict | None = None,
    ) -> str:
        if not self._client:
            logger.warning("Firestore not configured")
            return ""

        def _add() -> str:
            ref = self._client.collection("sessions").document(session_id).collection("messages").document()
            data: dict[str, Any] = {
                "role": role,
                "content": content,
                "created_at": firestore.SERVER_TIMESTAMP,
            }
            if audio_url is not None:
                data["audio_url"] = audio_url
            if analysis is not None:
                data["analysis"] = analysis
            ref.set(data)
            return ref.id

        return await asyncio.to_thread(_add)

    async def get_messages(self, session_id: str, limit: int = 100) -> list[dict]:
        if not self._client:
            logger.warning("Firestore not configured")
            return []

        def _query() -> list[dict]:
            docs = (
                self._client.collection("sessions")
                .document(session_id)
                .collection("messages")
                .order_by("created_at", direction=firestore.Query.ASCENDING)
                .limit(limit)
                .stream()
            )
            out = []
            for d in docs:
                data = d.to_dict()
                out.append(
                    {
                        "id": d.id,
                        "role": data.get("role", ""),
                        "content": data.get("content", ""),
                        "audio_url": data.get("audio_url"),
                        "analysis": data.get("analysis"),
                        "created_at": data.get("created_at"),
                    }
                )
            return out

        return await asyncio.to_thread(_query)

    async def save_session_recap(self, session_id: str, recap: str, next_step: str) -> None:
        if not self._client:
            return

        def _save() -> None:
            ref = self._client.collection("sessions").document(session_id)
            ref.set(
                {"recap": recap, "next_step": next_step, "ended_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )

        await asyncio.to_thread(_save)

    async def save_warmup_score(self, session_id: str, exercise_id: str, score: dict) -> str:
        if not self._client:
            logger.warning("Firestore not configured")
            return ""

        def _save() -> str:
            ref = (
                self._client.collection("warmup_sessions")
                .document(session_id)
                .collection("scores")
                .document()
            )
            data: dict[str, Any] = {
                "exercise_id": exercise_id,
                **score,
                "created_at": firestore.SERVER_TIMESTAMP,
            }
            ref.set(data)
            return ref.id

        return await asyncio.to_thread(_save)

    async def get_warmup_scores(self, session_id: str) -> list[dict]:
        if not self._client:
            logger.warning("Firestore not configured")
            return []

        def _query() -> list[dict]:
            docs = (
                self._client.collection("warmup_sessions")
                .document(session_id)
                .collection("scores")
                .order_by("created_at", direction=firestore.Query.ASCENDING)
                .stream()
            )
            return [{"id": d.id, **d.to_dict()} for d in docs]

        return await asyncio.to_thread(_query)


firestore_db = FirestoreDB()
