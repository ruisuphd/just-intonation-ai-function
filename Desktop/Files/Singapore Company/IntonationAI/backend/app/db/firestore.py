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
        owner_uid: str | None = None,
        coach_type: str | None = None,
    ) -> str:
        if not self._client:
            logger.warning("Firestore not configured")
            return ""

        def _add() -> str:
            session_ref = self._client.collection("sessions").document(session_id)
            session_meta: dict[str, Any] = {}
            if owner_uid is not None:
                session_meta["owner_uid"] = owner_uid
            if coach_type is not None:
                session_meta["coach_type"] = coach_type
            if session_meta:
                session_ref.set(session_meta, merge=True)
            ref = session_ref.collection("messages").document()
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

    async def update_message_audio_url(
        self,
        session_id: str,
        message_doc_id: str,
        audio_url: str,
    ) -> None:
        if not self._client or not message_doc_id:
            return

        def _upd() -> None:
            ref = (
                self._client.collection("sessions")
                .document(session_id)
                .collection("messages")
                .document(message_doc_id)
            )
            ref.update({"audio_url": audio_url})

        try:
            await asyncio.to_thread(_upd)
        except Exception as e:
            logger.warning("Firestore update_message_audio_url failed: %s", e)

    async def ensure_warmup_session(self, session_id: str, owner_uid: str) -> None:
        if not self._client:
            logger.warning("Firestore not configured")
            return

        def _ensure() -> None:
            ref = self._client.collection("warmup_sessions").document(session_id)
            ref.set({"owner_uid": owner_uid}, merge=True)

        await asyncio.to_thread(_ensure)

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

    async def get_messages_recent(self, session_id: str, *, limit: int) -> list[dict]:
        """Last ``limit`` messages in chronological order (for LLM context and recaps)."""
        if not self._client:
            logger.warning("Firestore not configured")
            return []

        def _query() -> list[dict]:
            docs = (
                self._client.collection("sessions")
                .document(session_id)
                .collection("messages")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
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
            out.reverse()
            return out

        return await asyncio.to_thread(_query)

    async def record_telemetry_event(
        self,
        *,
        event_type: str,
        firebase_uid: str | None,
        payload: dict[str, Any],
    ) -> str:
        if not self._client:
            logger.debug("Firestore telemetry skipped (no client)")
            return ""

        def _write() -> str:
            ref = self._client.collection("telemetry_events").document()
            data: dict[str, Any] = {
                "event_type": event_type,
                "payload": payload,
                "created_at": firestore.SERVER_TIMESTAMP,
            }
            if firebase_uid:
                data["firebase_uid"] = firebase_uid
            ref.set(data)
            return ref.id

        try:
            return await asyncio.to_thread(_write)
        except Exception as e:
            logger.warning("Telemetry Firestore write failed: %s", e)
            return ""

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

    async def get_session_meta(self, session_id: str) -> dict[str, Any]:
        if not self._client:
            return {}

        def _get() -> dict[str, Any]:
            doc = self._client.collection("sessions").document(session_id).get()
            return doc.to_dict() or {}

        return await asyncio.to_thread(_get)

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
