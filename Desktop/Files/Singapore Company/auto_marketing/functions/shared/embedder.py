from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal

from shared.gcp_auth import get_google_credentials
from shared.logger import get_logger

logger = get_logger("embedder")

_DEFAULT_MODEL = "gemini-embedding-001"
_DEFAULT_DIMENSION = 2048
_MAX_BATCH = 250

TaskType = Literal[
    "RETRIEVAL_DOCUMENT",
    "RETRIEVAL_QUERY",
    "SEMANTIC_SIMILARITY",
]


class Embedder:
    def __init__(self):
        self.model_name = os.getenv("EMBEDDING_MODEL", _DEFAULT_MODEL)
        self.dimension = int(os.getenv("EMBEDDING_DIMENSION", _DEFAULT_DIMENSION))
        self._model = None
        self._input_cls = None
        self._credentials_expires_at: datetime | None = None

    def _get_model(self):
        if self._model is None or (
            self._credentials_expires_at is not None
            and datetime.now(timezone.utc) >= self._credentials_expires_at
        ):
            import vertexai
            from vertexai.language_models import TextEmbeddingModel
            from vertexai.language_models import TextEmbeddingInput

            creds, project, expires_at = get_google_credentials(
                require_quota_project=True
            )
            location = os.getenv("GCP_REGION", "asia-southeast1")
            vertexai.init(project=project, location=location, credentials=creds)
            self._model = TextEmbeddingModel.from_pretrained(self.model_name)
            self._input_cls = TextEmbeddingInput
            self._credentials_expires_at = expires_at
        return self._model

    def embed_texts(
        self,
        texts: list[str],
        task_type: TaskType = "RETRIEVAL_DOCUMENT",
    ) -> list[list[float]]:
        if not texts:
            return []

        model = self._get_model()
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), _MAX_BATCH):
            batch = texts[i : i + _MAX_BATCH]
            if task_type and self._input_cls is not None:
                inputs = [
                    self._input_cls(text=text, task_type=task_type) for text in batch
                ]
            else:
                inputs = batch
            results = model.get_embeddings(
                inputs,
                output_dimensionality=self.dimension,
                auto_truncate=True,
            )
            all_embeddings.extend(e.values for e in results)

        logger.info(
            "embedder.batch",
            extra={
                "model": self.model_name,
                "count": len(texts),
                "dimension": self.dimension,
                "task_type": task_type,
            },
        )
        return all_embeddings

    def embed_text(
        self,
        text: str,
        task_type: TaskType = "RETRIEVAL_QUERY",
    ) -> list[float]:
        results = self.embed_texts([text], task_type=task_type)
        return results[0]
