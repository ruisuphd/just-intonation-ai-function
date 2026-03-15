from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_ALLOWED_UPLOADS: dict[str, set[str]] = {
    "pdf": {"application/pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    "md": {"text/markdown", "text/plain"},
}


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    file_type: str
    content_type: str


def validate_upload(file: UploadFile, size: int) -> ValidatedUpload:
    filename = os.path.basename((file.filename or "").strip())
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed_types = _ALLOWED_UPLOADS.get(file_type)
    if not allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a PDF, DOCX, or Markdown file.",
        )

    content_type = (file.content_type or "").lower()
    if content_type and content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type for .{file_type} upload.",
        )

    safe_filename = filename.replace("/", "-").replace("\\", "-")
    return ValidatedUpload(
        filename=safe_filename,
        file_type=file_type,
        content_type=content_type or next(iter(allowed_types)),
    )
