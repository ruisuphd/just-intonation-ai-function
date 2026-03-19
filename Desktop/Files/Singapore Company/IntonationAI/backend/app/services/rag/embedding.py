"""Embedding service for RAG using sentence-transformers."""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"
_model: Any = None


def _get_model() -> Any:
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(_MODEL_NAME)
        except Exception as e:
            logger.warning("sentence-transformers not available, using fallback: %s", e)
            _model = False
    return _model if _model is not False else None


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts. Returns list of vectors."""
    model = _get_model()
    if model is None:
        return []
    return model.encode(texts, convert_to_numpy=True).tolist()


def embed_text(text: str) -> list[float]:
    """Embed a single text. Returns a vector."""
    results = embed_texts([text])
    return results[0] if results else []


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    import math

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def embed_texts_async(texts: list[str]) -> list[list[float]]:
    """Async wrapper for embedding (runs in thread pool)."""
    return await asyncio.to_thread(embed_texts, texts)


async def embed_text_async(text: str) -> list[float]:
    """Async wrapper for single text embedding."""
    return await asyncio.to_thread(embed_text, text)
