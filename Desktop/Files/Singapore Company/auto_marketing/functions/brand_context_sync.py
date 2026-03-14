from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from google.cloud import firestore
from google.oauth2.credentials import Credentials

from shared.chunker import Chunker
from shared.embedder import Embedder
from shared.logger import get_logger
from shared.models import BrandChunk
from shared.models import BrandDocument

logger = get_logger("brand_context_sync")

ROOT_DIR = Path(__file__).resolve().parent.parent
_db: firestore.Client | None = None


@dataclass(frozen=True)
class MaterialSpec:
    doc_id: str
    path: Path
    doc_type: str
    section_keywords: tuple[str, ...] = ()


MATERIAL_SPECS = (
    MaterialSpec(
        doc_id="brand-service-overview",
        path=ROOT_DIR / "Intonation_Labs_Business_Plan_2026_Revised.docx.md",
        doc_type="service_description",
        section_keywords=(
            "executive summary",
            "company overview",
            "founder profile & competitive advantage",
            "consulting strategy",
            "generative ai & agentic ai service line",
        ),
    ),
    MaterialSpec(
        doc_id="brand-icp-and-markets",
        path=ROOT_DIR / "Intonation_Labs_Business_Plan_2026_Revised.docx.md",
        doc_type="icp_definition",
        section_keywords=(
            "market analysis",
            "consulting strategy",
            "marketing & go-to-market strategy",
        ),
    ),
    MaterialSpec(
        doc_id="brand-founder-voice",
        path=ROOT_DIR / "Rui_Su-CV.md",
        doc_type="brand_voice",
    ),
    MaterialSpec(
        doc_id="brand-proof-points",
        path=ROOT_DIR / "Intonation_Labs_Business_Plan_2026_Revised.docx.md",
        doc_type="case_study",
        section_keywords=(
            "founder profile & competitive advantage",
            "product strategy (intonationai)",
            "technical architecture",
        ),
    ),
    MaterialSpec(
        doc_id="consulting-qualification-playbook",
        path=ROOT_DIR / "SOP_CON_Consulting_Delivery.md",
        doc_type="icp_definition",
        section_keywords=(
            "sop-con-001",
            "sop-con-006",
        ),
    ),
    MaterialSpec(
        doc_id="consulting-outreach-guide",
        path=ROOT_DIR / "SOP_CON_Consulting_Delivery.md",
        doc_type="outreach_guide",
        section_keywords=(
            "sop-con-001",
            "sop-con-004",
            "sop-con-007",
        ),
    ),
)


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
    db = _get_script_db()
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


def _get_script_db() -> firestore.Client:
    global _db
    if _db is not None:
        return _db

    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"],
        text=True,
    ).strip()
    credentials = Credentials(token=token)
    env_project = os.getenv("GCP_PROJECT_ID")
    _db = firestore.Client(
        project=env_project,
        credentials=credentials,
    )
    return _db


def _sync_material(spec: MaterialSpec) -> dict:
    raw_text = spec.path.read_text(encoding="utf-8")
    selected_text = _extract_sections(raw_text, spec.section_keywords)
    cleaned_text = _cleanup_markdown(selected_text)
    if not cleaned_text:
        raise ValueError(f"No content extracted for {spec.doc_id}")

    chunker = Chunker(target_tokens=350, overlap_tokens=48, min_tokens=40)
    chunks = chunker.chunk(
        text=cleaned_text,
        document_id=spec.doc_id,
        language="en",
        doc_type=spec.doc_type,
    )
    if not chunks:
        chunks = [
            BrandChunk(
                document_id=spec.doc_id,
                chunk_index=0,
                text=cleaned_text,
                token_count=chunker._count(cleaned_text),
                language="en",
                doc_type=spec.doc_type,
            )
        ]

    try:
        embedder = Embedder()
        embeddings = embedder.embed_texts(
            [chunk.text for chunk in chunks],
            task_type="RETRIEVAL_DOCUMENT",
        )
    except Exception as exc:
        logger.warning(
            "brand_context_sync.embedding_skipped",
            extra={"doc_id": spec.doc_id, "error": str(exc)},
        )
        embeddings = [[] for _ in chunks]

    _delete_existing_chunks(spec.doc_id)

    db = _get_script_db()
    batch = db.batch()
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        chunk.embedding = embedding
        ref = db.collection("brand_chunks").document(
            f"{spec.doc_id}-{chunk.chunk_index:03d}"
        )
        batch.set(ref, chunk.model_dump())
    batch.commit()

    doc = BrandDocument(
        filename=spec.path.name,
        storage_path=str(spec.path.relative_to(ROOT_DIR)),
        file_type="md",
        file_size_bytes=len(raw_text.encode("utf-8")),
        doc_type=spec.doc_type,
        language="en",
        status="indexed",
        chunk_count=len(chunks),
        uploaded_by="cursor-sync",
    )
    db.collection("brand_documents").document(spec.doc_id).set(doc.model_dump())

    result = {
        "doc_id": spec.doc_id,
        "doc_type": spec.doc_type,
        "chunks": len(chunks),
    }
    logger.info("brand_context_sync.material_done", extra=result)
    return result


def main() -> None:
    logger.info("brand_context_sync.start", extra={"materials": len(MATERIAL_SPECS)})
    results = [_sync_material(spec) for spec in MATERIAL_SPECS]
    logger.info("brand_context_sync.done", extra={"results": results})


if __name__ == "__main__":
    main()
