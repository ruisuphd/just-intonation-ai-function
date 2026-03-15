"""Engine for ingesting uploaded documents into tenant-scoped brand chunks."""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone

from shared.chunker import Chunker
from shared.embedder import Embedder
from shared.firestore_client import delete_doc, query_docs, set_doc, update_doc
from shared.logger import get_logger
from shared.models import BrandChunk
from shared.storage_client import download_bytes

logger = get_logger("engine.document_ingestion")


def _extract_text_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise ImportError("pypdf or PyPDF2 required for PDF extraction")

    reader = PdfReader(io.BytesIO(content))
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        parts.append(text)
    return "\n\n".join(parts).strip()


def _extract_text_plain(content: bytes) -> str:
    return content.decode("utf-8", errors="replace").strip()


def _delete_existing_chunks(tenant_id: str, document_id: str) -> None:
    chunks = query_docs(
        "brand_chunks",
        filters=[("document_id", "==", document_id)],
        tenant_id=tenant_id,
    )
    for c in chunks:
        doc_id = c.get("id")
        if doc_id:
            delete_doc("brand_chunks", doc_id, tenant_id=tenant_id)


def ingest_document(
    tenant_id: str,
    document_id: str,
    storage_path: str,
    file_type: str,
    doc_type: str = "other",
) -> dict:
    """Download document from GCS, extract text, chunk, embed, write to brand_chunks."""
    bucket = os.getenv("BRAND_DOCS_BUCKET", "")
    if not bucket:
        return {"ok": False, "error": "Storage not configured"}

    if not storage_path.startswith(f"gs://{bucket}/"):
        blob_path = storage_path
    else:
        blob_path = storage_path.replace(f"gs://{bucket}/", "")

    try:
        content = download_bytes(bucket, blob_path, tenant_id=None)
    except Exception as exc:
        logger.warning(
            "document_ingestion.download_failed",
            extra={"doc_id": document_id, "error": str(exc)},
        )
        update_doc(
            "documents",
            document_id,
            {"status": "error", "error_message": str(exc)},
            tenant_id=tenant_id,
        )
        return {"ok": False, "error": str(exc)}

    update_doc(
        "documents",
        document_id,
        {"status": "processing"},
        tenant_id=tenant_id,
    )

    file_type_lower = (file_type or "pdf").lower()
    if file_type_lower == "pdf":
        try:
            text = _extract_text_pdf(content)
        except Exception as exc:
            update_doc(
                "documents",
                document_id,
                {"status": "error", "error_message": str(exc)},
                tenant_id=tenant_id,
            )
            return {"ok": False, "error": str(exc)}
    else:
        text = _extract_text_plain(content)

    if not text or len(text) < 50:
        update_doc(
            "documents",
            document_id,
            {"status": "error", "error_message": "Extracted text too short or empty"},
            tenant_id=tenant_id,
        )
        return {"ok": False, "error": "Extracted text too short or empty"}

    chunker = Chunker(target_tokens=350, overlap_tokens=48, min_tokens=40)
    chunks = chunker.chunk(
        text=text, document_id=document_id, language="en", doc_type=doc_type
    )
    if not chunks:
        chunks = [
            BrandChunk(
                document_id=document_id,
                chunk_index=0,
                text=text[:2000],
                token_count=chunker._count(text[:2000]),
                language="en",
                doc_type=doc_type,
            )
        ]

    try:
        embedder = Embedder()
        embeddings = embedder.embed_texts(
            [c.text for c in chunks],
            task_type="RETRIEVAL_DOCUMENT",
        )
    except Exception as exc:
        logger.warning(
            "document_ingestion.embedding_skipped",
            extra={"doc_id": document_id, "error": str(exc)},
        )
        embeddings = [[] for _ in chunks]

    _delete_existing_chunks(tenant_id, document_id)

    for chunk, embedding in zip(chunks, embeddings, strict=True):
        chunk.embedding = embedding or []
        chunk_id = f"{document_id}-{chunk.chunk_index:03d}"
        set_doc(
            "brand_chunks",
            chunk_id,
            chunk.model_dump(mode="json"),
            tenant_id=tenant_id,
        )

    now = datetime.now(timezone.utc)
    update_doc(
        "documents",
        document_id,
        {
            "status": "indexed",
            "chunk_count": len(chunks),
            "processed_at": now,
            "error_message": None,
        },
        tenant_id=tenant_id,
    )

    logger.info(
        "document_ingestion.done",
        extra={
            "tenant_id": tenant_id,
            "document_id": document_id,
            "chunks": len(chunks),
        },
    )
    return {"ok": True, "chunks": len(chunks)}
