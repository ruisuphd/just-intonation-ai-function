from __future__ import annotations

from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from shared.embedder import Embedder
from shared.firestore_client import get_db
from shared.logger import get_logger

logger = get_logger("retriever")


class Retriever:
    def __init__(
        self,
        top_k: int = 8,
        distance_threshold: float = 0.3,
        tenant_id: str | None = None,
    ):
        self.top_k = top_k
        self.distance_threshold = distance_threshold
        self.tenant_id = tenant_id
        self._embedder = Embedder()

    @property
    def _collection_path(self) -> str:
        if self.tenant_id:
            return f"tenants/{self.tenant_id}/brand_chunks"
        return "brand_chunks"

    def _vector_search(
        self,
        embedding: list[float],
        language: str | None = None,
        top_k: int | None = None,
    ) -> list[dict]:
        db = get_db()
        k = top_k or self.top_k
        ref = db.collection(self._collection_path)

        if language:
            ref = ref.where("language", "==", language)

        vector_query = ref.find_nearest(
            vector_field="embedding",
            query_vector=Vector(embedding),
            distance_measure=DistanceMeasure.COSINE,
            limit=k,
            distance_result_field="distance",
        )

        results = []
        for snap in vector_query.get():
            data = snap.to_dict()
            data["id"] = snap.id
            data["_distance"] = data.pop("distance", None)
            data.pop("embedding", None)
            results.append(data)
        return results

    def _filter_and_dedup(self, results: list[dict]) -> list[dict]:
        filtered = [
            r
            for r in results
            if r.get("_distance") is not None
            and r["_distance"] <= self.distance_threshold
        ]

        best: dict[str, dict] = {}
        for r in filtered:
            did = r.get("document_id", "")
            if did not in best or r["_distance"] < best[did]["_distance"]:
                best[did] = r

        return sorted(best.values(), key=lambda r: r["_distance"])

    def retrieve(
        self,
        query_text: str,
        language: str = "en",
    ) -> tuple[list[dict], bool]:
        try:
            embedding = self._embedder.embed_text(
                query_text, task_type="RETRIEVAL_QUERY"
            )
            raw = self._vector_search(embedding, language=language)
            chunks = self._filter_and_dedup(raw)

            logger.info(
                "retriever.retrieve",
                extra={
                    "tenant_id": self.tenant_id or "root",
                    "language": language,
                    "raw": len(raw),
                    "kept": len(chunks),
                },
            )
            return chunks, False
        except Exception as exc:
            logger.warning(
                "retriever.fallback_empty",
                extra={
                    "tenant_id": self.tenant_id or "root",
                    "error": str(exc),
                },
            )
            return [], False

    def retrieve_with_language_fallback(
        self,
        query_text: str,
    ) -> tuple[list[dict], bool]:
        try:
            embedding = self._embedder.embed_text(
                query_text, task_type="RETRIEVAL_QUERY"
            )

            zh_raw = self._vector_search(embedding, language="zh")
            zh_chunks = self._filter_and_dedup(zh_raw)

            if len(zh_chunks) >= 3:
                logger.info(
                    "retriever.fallback",
                    extra={
                        "tenant_id": self.tenant_id or "root",
                        "zh": len(zh_chunks),
                        "fallback": False,
                    },
                )
                return zh_chunks, False

            all_raw = self._vector_search(embedding, language=None, top_k=self.top_k)
            all_chunks = self._filter_and_dedup(all_raw)

            zh_ids = {c["id"] for c in zh_chunks}
            en_fill = [c for c in all_chunks if c["id"] not in zh_ids]
            combined = zh_chunks + en_fill

            logger.info(
                "retriever.fallback",
                extra={
                    "tenant_id": self.tenant_id or "root",
                    "zh": len(zh_chunks),
                    "en_fill": len(en_fill),
                    "fallback": True,
                },
            )
            return combined, True
        except Exception as exc:
            logger.warning(
                "retriever.fallback_empty",
                extra={
                    "tenant_id": self.tenant_id or "root",
                    "method": "retrieve_with_language_fallback",
                    "error": str(exc),
                },
            )
            return [], False
