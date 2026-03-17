"""Firebase Auth middleware for FastAPI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from shared.firestore_client import create_tenant, query_docs, update_tenant
from shared.redis_client import cache_get, cache_set
from shared.entitlements import (
    is_internal_test_email,
    normalize_email,
    resolve_access,
)
from shared.logger import get_logger
from shared.models import TenantProfile

logger = get_logger("auth_middleware")

_bearer = HTTPBearer(auto_error=False)


def _verify_firebase_token(token: str) -> dict:
    import firebase_admin
    from firebase_admin import auth as firebase_auth

    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    return firebase_auth.verify_id_token(token)


def _build_default_tenant(uid: str, email: str) -> dict[str, Any]:
    normalized_email = normalize_email(email)
    return {
        "tenant_id": f"auto-{uid[:16]}",
        "owner_uid": uid,
        "owner_email": normalized_email,
        "company_name": "",
        "industry": "Other",
        "description": "",
        "subscription_tier": "starter",
        "subscription_status": "active",
        "daily_digest_email": normalized_email,
        "created_at": datetime.now(timezone.utc),
        "is_internal": is_internal_test_email(email),
    }


def _profile_updates(profile: TenantProfile, email: str) -> dict[str, Any]:
    normalized_email = normalize_email(email)
    updates: dict[str, Any] = {}

    if normalized_email and profile.owner_email != normalized_email:
        updates["owner_email"] = normalized_email

    if normalized_email and not profile.daily_digest_email:
        updates["daily_digest_email"] = normalized_email

    if is_internal_test_email(email) and not profile.is_internal:
        updates["is_internal"] = True

    return updates


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    try:
        decoded = _verify_firebase_token(credentials.credentials)
    except Exception as exc:
        logger.warning("auth.invalid_token", extra={"error": str(exc)})
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    uid = decoded.get("uid", "")
    email = decoded.get("email", "")

    # ── Try cache first for tenant lookup ─────────────────────────────────
    cache_key = f"tenant:uid:{uid}"
    tenant: dict[str, Any] | None = cache_get(cache_key)

    if tenant is None:
        tenant_docs = query_docs("tenants", filters=[("owner_uid", "==", uid)], limit=1)
        tenant = tenant_docs[0] if tenant_docs else None

        if not tenant:
            profile_data = _build_default_tenant(uid, email)
            create_tenant(profile_data["tenant_id"], profile_data)
            tenant = {**profile_data, "id": profile_data["tenant_id"]}
            logger.info(
                "auth.auto_tenant_created",
                extra={"tenant_id": profile_data["tenant_id"], "uid": uid},
            )

        cache_set(cache_key, tenant, ttl_seconds=300)

    profile = TenantProfile.model_validate(tenant)
    updates = _profile_updates(profile, email)
    if updates:
        update_tenant(profile.tenant_id, updates)
        tenant = {**tenant, **updates}
        profile = TenantProfile.model_validate(tenant)
        cache_set(cache_key, tenant, ttl_seconds=300)

    access = resolve_access(profile)
    request.state.bypass_billing = access.access_source == "internal"
    request.state.tenant_tier = access.effective_tier
    request.state.access_source = access.access_source
    request.state.starter_access_expires_at = access.starter_access_expires_at
    request.state.has_paid_subscription = access.has_paid_subscription
    request.state.tenant_id = profile.tenant_id
    request.state.tenant = profile

    request.state.uid = uid
    request.state.email = email
    return {"uid": uid, "email": email}


def require_tenant(
    request: Request, _user: dict = Depends(get_current_user)
) -> TenantProfile:
    if not request.state.tenant:
        raise HTTPException(
            status_code=403,
            detail="No tenant found for this account. Complete onboarding first.",
        )
    return request.state.tenant


def require_access(*tiers: str):
    """Dependency factory: raises 403 if the effective tenant tier is not allowed."""

    def _check(
        request: Request, _tenant: TenantProfile = Depends(require_tenant)
    ) -> TenantProfile:
        if request.state.tenant_tier not in tiers:
            raise HTTPException(
                status_code=403,
                detail=f"This feature requires one of: {', '.join(tiers)}. Current tier: {request.state.tenant_tier}",
            )
        return _tenant

    return _check


def require_subscription(*tiers: str):
    return require_access(*tiers)
