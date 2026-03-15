from __future__ import annotations

import re

import tiktoken

from shared.models import BrandChunk

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class Chunker:
    def __init__(
        self,
        target_tokens: int = 512,
        overlap_tokens: int = 64,
        min_tokens: int = 50,
    ):
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self.min_tokens = min_tokens
        self._enc = tiktoken.get_encoding("cl100k_base")

    def _count(self, text: str) -> int:
        return len(self._enc.encode(text))

    def chunk(
        self,
        text: str,
        document_id: str,
        language: str,
        doc_type: str,
    ) -> list[BrandChunk]:
        sentences = _SENTENCE_RE.split(text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return []

        chunks: list[BrandChunk] = []
        parts: list[str] = []
        part_tokens = 0

        for sent in sentences:
            stok = self._count(sent)

            if parts and part_tokens + stok > self.target_tokens:
                chunk_text = " ".join(parts)
                chunks.append(
                    BrandChunk(
                        document_id=document_id,
                        chunk_index=len(chunks),
                        text=chunk_text,
                        token_count=self._count(chunk_text),
                        language=language,
                        doc_type=doc_type,
                    )
                )

                encoded = self._enc.encode(chunk_text)
                tail = (
                    encoded[-self.overlap_tokens :]
                    if len(encoded) > self.overlap_tokens
                    else encoded
                )
                overlap = self._enc.decode(tail)
                parts = [overlap]
                part_tokens = len(tail)

            parts.append(sent)
            part_tokens += stok

        if parts:
            chunk_text = " ".join(parts)
            tc = self._count(chunk_text)
            if tc >= self.min_tokens:
                chunks.append(
                    BrandChunk(
                        document_id=document_id,
                        chunk_index=len(chunks),
                        text=chunk_text,
                        token_count=tc,
                        language=language,
                        doc_type=doc_type,
                    )
                )

        return chunks
