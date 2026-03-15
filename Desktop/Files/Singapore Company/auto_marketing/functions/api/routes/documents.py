"""Brand documents API: list, upload, delete."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from api.middleware.auth import require_access
from shared.firestore_client import add_doc, delete_doc, query_docs
from shared.logger import get_logger
from shared.models import TenantProfile
from shared.storage_client import delete_blob, upload_bytes
from shared.upload_validation import validate_upload

logger = get_logger("api.documents")

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
async def list_documents(
    tenant: TenantProfile = Depends(require_access("starter", "pro")),
):
    docs = query_docs("documents", order_by="-uploaded_at", tenant_id=tenant.tenant_id)
    return {"documents": docs}


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form("other"),
    tenant: TenantProfile = Depends(require_access("starter", "pro")),
):
    content = await file.read()
    validated = validate_upload(file, len(content))

    bucket = os.getenv("BRAND_DOCS_BUCKET", "")
    if not bucket:
        raise HTTPException(status_code=500, detail="Storage not configured")

    blob_path = f"documents/{validated.filename}"
    gs_path = upload_bytes(
        bucket,
        blob_path,
        content,
        content_type=validated.content_type,
        tenant_id=tenant.tenant_id,
    )

    doc_data = {
        "filename": validated.filename,
        "storage_path": gs_path,
        "file_type": validated.file_type,
        "file_size_bytes": len(content),
        "doc_type": doc_type or "other",
        "status": "uploaded",
        "uploaded_at": datetime.now(timezone.utc),
    }
    doc_id = add_doc("documents", doc_data, tenant_id=tenant.tenant_id)

    try:
        from engines.document_ingestion import ingest_document

        ingest_document(
            tenant_id=tenant.tenant_id,
            document_id=doc_id,
            storage_path=gs_path,
            file_type=validated.file_type,
            doc_type=doc_type or "other",
        )
    except Exception as exc:
        logger.warning(
            "documents.ingestion_start_failed",
            extra={"doc_id": doc_id, "error": str(exc)},
        )

    return {"ok": True, "document_id": doc_id}


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    tenant: TenantProfile = Depends(require_access("starter", "pro")),
):
    from shared.firestore_client import get_doc

    doc = get_doc("documents", doc_id, tenant_id=tenant.tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    bucket = os.getenv("BRAND_DOCS_BUCKET", "")
    storage_path = doc.get("storage_path", "")
    if bucket and storage_path:
        blob = storage_path.replace(f"gs://{bucket}/", "")
        try:
            delete_blob(bucket, blob)
        except Exception:
            pass

    delete_doc("documents", doc_id, tenant_id=tenant.tenant_id)
    return {"ok": True}
