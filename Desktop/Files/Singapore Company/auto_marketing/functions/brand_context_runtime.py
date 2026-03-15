from __future__ import annotations

import re
from datetime import datetime, timezone

import functions_framework
from flask import Request, jsonify

from shared.chunker import Chunker
from shared.embedder import Embedder
from shared.firestore_client import get_db
from shared.logger import get_logger
from shared.models import BrandChunk
from shared.models import BrandDocument

logger = get_logger("brand_context_runtime")


def _normalise_heading(line: str) -> str:
    cleaned = re.sub(r"[*`_#]", "", line).strip()
    cleaned = cleaned.replace("\\.", ".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.lower()


def _extract_sections(markdown_text: str, keywords: tuple[str, ...]) -> str:
    if not keywords:
        return markdown_text

    wanted = tuple(keyword.lower() for keyword in keywords)
    sections: list[str] = []
    current_heading = ""
    current_lines: list[str] = []

    def flush() -> None:
        if current_lines and any(keyword in current_heading for keyword in wanted):
            sections.append("\n".join(current_lines).strip())

    for line in markdown_text.splitlines():
        if line.startswith("#"):
            flush()
            current_heading = _normalise_heading(line)
            current_lines = [line]
            continue
        current_lines.append(line)

    flush()
    return "\n\n".join(section for section in sections if section)


def _cleanup_markdown(markdown_text: str) -> str:
    text = markdown_text.replace("\\.", ".")
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\n\|", "\n", text)
    text = text.replace("|", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _delete_existing_chunks(doc_id: str) -> None:
    db = get_db()
    snaps = list(
        db.collection("brand_chunks").where("document_id", "==", doc_id).stream()
    )
    if not snaps:
        return

    batch = db.batch()
    count = 0
    for snap in snaps:
        batch.delete(snap.reference)
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()


def _sync_material(material: dict) -> dict:
    doc_id = material["doc_id"]
    filename = material["filename"]
    doc_type = material["doc_type"]
    content = material["content"]
    section_keywords = tuple(material.get("section_keywords", []))

    selected_text = _extract_sections(content, section_keywords)
    cleaned_text = _cleanup_markdown(selected_text)
    if not cleaned_text:
        raise ValueError(f"No content extracted for {doc_id}")

    chunker = Chunker(target_tokens=350, overlap_tokens=48, min_tokens=40)
    chunks = chunker.chunk(
        text=cleaned_text,
        document_id=doc_id,
        language="en",
        doc_type=doc_type,
    )
    if not chunks:
        chunks = [
            BrandChunk(
                document_id=doc_id,
                chunk_index=0,
                text=cleaned_text,
                token_count=chunker._count(cleaned_text),
                language="en",
                doc_type=doc_type,
            )
        ]

    embedder = Embedder()
    embeddings = embedder.embed_texts(
        [chunk.text for chunk in chunks],
        task_type="RETRIEVAL_DOCUMENT",
    )

    _delete_existing_chunks(doc_id)

    db = get_db()
    batch = db.batch()
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        chunk.embedding = embedding
        ref = db.collection("brand_chunks").document(
            f"{doc_id}-{chunk.chunk_index:03d}"
        )
        batch.set(ref, chunk.model_dump())
    batch.commit()

    now = datetime.now(timezone.utc)
    doc = BrandDocument(
        filename=filename,
        storage_path=filename,
        file_type="md",
        file_size_bytes=len(content.encode("utf-8")),
        doc_type=doc_type,
        language="en",
        status="indexed",
        chunk_count=len(chunks),
        uploaded_by="runtime-sync",
        processed_at=now,
    )
    db.collection("brand_documents").document(doc_id).set(doc.model_dump())

    result = {"doc_id": doc_id, "doc_type": doc_type, "chunks": len(chunks)}
    logger.info("brand_context_runtime.material_done", extra=result)
    return result


@functions_framework.http
def sync_brand_context(request: Request):
    body = request.get_json(silent=True) or {}
    materials = body.get("materials") or []
    if not isinstance(materials, list) or not materials:
        return jsonify({"ok": False, "error": "materials array is required"}), 400

    try:
        results = [_sync_material(material) for material in materials]
    except Exception as exc:
        logger.error("brand_context_runtime.error", extra={"error": str(exc)})
        return jsonify({"ok": False, "error": str(exc)}), 500

    logger.info("brand_context_runtime.done", extra={"materials": len(results)})
    return jsonify({"ok": True, "materials": results}), 200
