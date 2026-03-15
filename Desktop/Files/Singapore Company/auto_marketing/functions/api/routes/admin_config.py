"""Admin configuration API for system-level secrets (SMTP)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.middleware.auth import require_tenant
from shared.firestore_client import get_doc, set_doc
from shared.logger import get_logger
from shared.models import TenantProfile

logger = get_logger("api.admin_config")

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(tenant: TenantProfile = Depends(require_tenant)) -> TenantProfile:
    """Only allow tenant owners (the admin of a single-tenant workspace) to manage config."""
    return tenant


# ── SMTP Configuration ─────────────────────────────────────────────────────────


class SMTPConfigUpdate(BaseModel):
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool | None = None
    smtp_use_ssl: bool | None = None


@router.get("/smtp-config")
async def get_smtp_config(
    tenant: TenantProfile = Depends(_require_admin),
):
    """Get SMTP configuration (password is masked)."""
    doc = get_doc("system_config", "smtp_config", tenant_id=None) or {}
    return {
        "smtp_host": doc.get("smtp_host", ""),
        "smtp_port": doc.get("smtp_port", 587),
        "smtp_user": doc.get("smtp_user", ""),
        "smtp_password": _mask(doc.get("smtp_password", "")),
        "smtp_from_email": doc.get("smtp_from_email", ""),
        "smtp_use_tls": doc.get("smtp_use_tls", True),
        "smtp_use_ssl": doc.get("smtp_use_ssl", False),
        "configured": bool(doc.get("smtp_host") and (doc.get("smtp_from_email") or doc.get("smtp_user"))),
    }


@router.put("/smtp-config")
async def update_smtp_config(
    body: SMTPConfigUpdate,
    tenant: TenantProfile = Depends(_require_admin),
):
    """Update SMTP configuration. Only non-null fields are updated."""
    existing = get_doc("system_config", "smtp_config", tenant_id=None) or {}
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    merged = {**existing, **updates}
    set_doc("system_config", "smtp_config", merged, tenant_id=None)
    logger.info("admin.smtp_config_updated", extra={"fields": list(updates.keys())})
    return {"ok": True, "updated_fields": list(updates.keys())}


def _mask(value: str) -> str:
    """Mask sensitive values, showing only last 4 chars."""
    if not value or len(value) <= 4:
        return "****" if value else ""
    return "*" * (len(value) - 4) + value[-4:]
