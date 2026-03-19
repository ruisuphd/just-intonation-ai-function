"""
Knowledge base for RAG. Supports vector search (embeddings) with keyword fallback.
"""

import logging
import re
from pathlib import Path

from app.services.rag.embedding import cosine_similarity, embed_text

logger = logging.getLogger(__name__)

CHUNK_WORDS = 500
OVERLAP_WORDS = 50


def _chunk_text(
    text: str, chunk_size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS
) -> list[str]:
    words = text.split()
    if len(words) <= chunk_size:
        return [text] if words else []
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return chunks


class KnowledgeBase:
    def __init__(self) -> None:
        self._documents: list[dict] = []
        self._embeddings: list[list[float]] = []
        self._use_vectors = False

    def add_document(self, text: str, metadata: dict | None = None) -> None:
        doc = {"text": text.strip(), "metadata": metadata or {}}
        self._documents.append(doc)
        try:
            emb = embed_text(text.strip())
            if emb:
                self._embeddings.append(emb)
                self._use_vectors = True
            else:
                self._embeddings.append([])
        except Exception as e:
            logger.debug("Embedding failed for chunk: %s", e)
            self._embeddings.append([])

    def add_from_file(self, file_path: str) -> int:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"{file_path} not found")
        content = path.read_text(encoding="utf-8", errors="replace")
        chunks = _chunk_text(content)
        base_meta = {"source": str(path)}
        for chunk in chunks:
            self.add_document(chunk, base_meta.copy())
        return len(chunks)

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        if len(self._documents) == 0:
            return []

        if self._use_vectors:
            try:
                query_emb = embed_text(query)
                if query_emb:
                    scored: list[tuple[dict, float]] = []
                    for doc, emb in zip(self._documents, self._embeddings):
                        if emb:
                            sim = cosine_similarity(query_emb, emb)
                            scored.append((doc, sim))
                    if scored:
                        scored.sort(key=lambda x: x[1], reverse=True)
                        return [
                            {"text": d["text"], "metadata": d["metadata"], "score": s}
                            for d, s in scored[:top_k]
                        ]
            except Exception as e:
                logger.debug("Vector search failed, falling back to keyword: %s", e)

        query_words = set(re.findall(r"\w+", query.lower()))
        if not query_words:
            return []
        scored: list[tuple[dict, float]] = []
        for doc in self._documents:
            chunk_words = set(re.findall(r"\w+", doc["text"].lower()))
            matches = len(query_words & chunk_words)
            score = matches / len(query_words) if query_words else 0.0
            scored.append((doc, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            {"text": d["text"], "metadata": d["metadata"], "score": s}
            for d, s in scored[:top_k]
        ]

    def __len__(self) -> int:
        return len(self._documents)


knowledge_base = KnowledgeBase()


def _seed_knowledge_base() -> None:
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data"
    for filename in ("vocal_pedagogy.md", "piano_pedagogy.md", "guitar_pedagogy.md"):
        path = data_dir / filename
        if path.exists():
            knowledge_base.add_from_file(str(path))


_seed_knowledge_base()
