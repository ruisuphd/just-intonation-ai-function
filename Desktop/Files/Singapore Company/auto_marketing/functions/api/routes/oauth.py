"""OAuth routes for LinkedIn and X platform connections."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

import httpx

from api.middleware.auth import require_tenant
from shared.usage_limits import get_limits_for_tier
from shared.firestore_client import (
    add_doc,
    delete_doc,
    get_doc,
    get_tenant,
    update_tenant,
)
from shared.logger import get_logger
from shared.models import PlatformCredentials, TenantProfile
from shared.secrets import get_secret_or_env

logger = get_logger("api.oauth")


def _get_oauth_credential(field: str, secret_id: str, env_var: str) -> str | None:
    """Resolve OAuth credential from Firestore admin config → Secret Manager → env. Returns None if none found."""
    try:
        doc = get_doc("system_config", "oauth_credentials", tenant_id=None) or {}
        value = doc.get(field, "").strip()
        if value:
            return value
    except Exception:
        pass
    result = get_secret_or_env(secret_id=secret_id, env_var=env_var)
    return result if result else None


router = APIRouter(prefix="/api/oauth", tags=["oauth"])

LINKEDIN_AUTH = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_ME = "https://api.linkedin.com/v2/me"
X_AUTH = "https://twitter.com/i/oauth2/authorize"
X_TOKEN = "https://api.twitter.com/2/oauth2/token"
X_ME = "https://api.x.com/2/users/me"

# TTL for OAuth state documents (10 minutes)
OAUTH_STATE_TTL_MINUTES = 10


def _is_managed_runtime() -> bool:
    return bool(
        os.getenv("K_SERVICE")
        or os.getenv("FUNCTION_TARGET")
        or os.getenv("FUNCTION_NAME")
    )


def _get_state_signing_key() -> str:
    """Get a server-side secret for HMAC-signing OAuth state parameters."""
    key = get_secret_or_env(
        secret_id="oauth-state-secret", env_var="OAUTH_STATE_SECRET"
    )
    if key:
        return key
    if _is_managed_runtime():
        logger.error("oauth.missing_oauth_state_secret")
        raise HTTPException(
            status_code=503,
            detail="OAuth state secret is not configured for this deployment.",
        )
    return os.getenv("GCP_PROJECT_ID", "automark-dev-fallback")


def _oauth_state(tenant_id: str, nonce: str) -> str:
    signing_key = _get_state_signing_key()
    sig = hmac.new(
        signing_key.encode(), f"{tenant_id}:{nonce}".encode(), hashlib.sha256
    ).hexdigest()[:16]
    return f"{tenant_id}:{nonce}:{sig}"


def _verify_state(state: str, tenant_id: str) -> bool:
    parts = state.split(":")
    if len(parts) != 3:
        return False
    tid, nonce, sig = parts
    if tid != tenant_id:
        return False
    expected = _oauth_state(tenant_id, nonce)
    return hmac.compare_digest(state, expected)


def _store_oauth_state(
    state: str,
    owner_uid: str,
    tenant_id: str,
    code_verifier: str | None = None,
) -> None:
    """Store OAuth state with owner identity and TTL for verification on callback."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OAUTH_STATE_TTL_MINUTES)
    doc = {
        "state": state,
        "owner_uid": owner_uid,
        "tenant_id": tenant_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": expires_at,
    }
    if code_verifier:
        doc["code_verifier"] = code_verifier
    add_doc("oauth_pkce", doc, doc_id=state, tenant_id=None)


def _get_oauth_state(state: str) -> dict | None:
    """Retrieve and validate an OAuth state document. Returns None if expired."""
    doc = get_doc("oauth_pkce", state, tenant_id=None)
    if not doc:
        return None
    # Check TTL
    expires_at = doc.get("expires_at")
    if expires_at:
        if isinstance(expires_at, datetime):
            exp = (
                expires_at
                if expires_at.tzinfo
                else expires_at.replace(tzinfo=timezone.utc)
            )
        else:
            exp = datetime.now(timezone.utc)  # If unparseable, treat as expired
        if datetime.now(timezone.utc) > exp:
            # Clean up expired state
            delete_doc("oauth_pkce", state, tenant_id=None)
            return None
    return doc


def _consume_oauth_state(state: str) -> dict | None:
    """Retrieve and delete an OAuth state document (one-time use)."""
    doc = _get_oauth_state(state)
    if doc:
        delete_doc("oauth_pkce", state, tenant_id=None)
    return doc


@router.get("/linkedin/authorize")
async def linkedin_authorize(
    request: Request,
    tenant: TenantProfile = Depends(require_tenant),
):
    tier = getattr(request.state, "tenant_tier", "starter")
    limits = get_limits_for_tier(tier)
    max_connections = limits["max_platform_connections"]
    connected = len(tenant.platform_credentials or {})
    if connected >= max_connections:
        raise HTTPException(
            status_code=429,
            detail=f"Platform connection limit reached ({max_connections}). Upgrade to Pro.",
        )

    client_id = _get_oauth_credential(
        "linkedin_client_id", "linkedin-client-id", "LINKEDIN_CLIENT_ID"
    )
    if not client_id:
        raise HTTPException(
            status_code=501,
            detail="LinkedIn OAuth not configured. Contact the administrator to configure OAuth credentials.",
        )

    api_url = os.getenv("API_URL") or os.getenv("APP_URL", "http://localhost:8080")
    redirect_uri = f"{api_url.rstrip('/')}/api/oauth/linkedin/callback"
    nonce = secrets.token_urlsafe(16)
    state = _oauth_state(tenant.tenant_id, nonce)

    # Store state with owner identity for callback verification
    _store_oauth_state(
        state=state,
        owner_uid=request.state.uid,
        tenant_id=tenant.tenant_id,
    )

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "openid profile email w_member_social",
    }
    url = f"{LINKEDIN_AUTH}?{urllib.parse.urlencode(params)}"
    return {"redirect_url": url}


@router.get("/linkedin/callback")
async def linkedin_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        raise HTTPException(status_code=400, detail=f"LinkedIn auth error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    # Verify state and retrieve stored owner identity
    state_doc = _consume_oauth_state(state)
    if not state_doc:
        raise HTTPException(
            status_code=400, detail="Expired or invalid state; restart OAuth flow"
        )

    tenant_id = state_doc.get("tenant_id", "")
    if not _verify_state(state, tenant_id):
        raise HTTPException(status_code=400, detail="Invalid state")

    tenant_doc = get_tenant(tenant_id)
    if not tenant_doc:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Verify the callback is for the same user who initiated the flow
    stored_uid = state_doc.get("owner_uid", "")
    tenant_owner_uid = tenant_doc.get("owner_uid", "")
    if stored_uid != tenant_owner_uid:
        logger.warning(
            "oauth.linkedin_uid_mismatch",
            extra={"tenant_id": tenant_id, "stored_uid": stored_uid},
        )
        raise HTTPException(status_code=403, detail="OAuth flow ownership mismatch")

    client_id = _get_oauth_credential(
        "linkedin_client_id", "linkedin-client-id", "LINKEDIN_CLIENT_ID"
    )
    client_secret = _get_oauth_credential(
        "linkedin_client_secret", "linkedin-client-secret", "LINKEDIN_CLIENT_SECRET"
    )
    if not client_id or not client_secret:
        raise HTTPException(status_code=501, detail="LinkedIn OAuth not configured")

    api_url = os.getenv("API_URL") or os.getenv("APP_URL", "http://localhost:8080")
    redirect_uri = f"{api_url.rstrip('/')}/api/oauth/linkedin/callback"

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            LINKEDIN_TOKEN,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if token_resp.status_code != 200:
        logger.warning(
            "oauth.linkedin_token_failed", extra={"status": token_resp.status_code}
        )
        raise HTTPException(status_code=400, detail="Failed to exchange LinkedIn code")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=400, detail="No access token in LinkedIn response"
        )

    async with httpx.AsyncClient() as client:
        me_resp = await client.get(
            LINKEDIN_ME,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    author_urn = "urn:li:person:unknown"
    if me_resp.status_code == 200:
        me_data = me_resp.json()
        lid = me_data.get("id", "")
        if lid:
            author_urn = f"urn:li:person:{lid}"

    expires_at = datetime.now(timezone.utc) + timedelta(days=60)
    creds = PlatformCredentials(
        access_token=access_token,
        refresh_token=token_data.get("refresh_token"),
        expires_at=expires_at,
        platform_id=author_urn,
    )
    platform_creds = tenant_doc.get("platform_credentials") or {}
    platform_creds["linkedin"] = creds.model_dump(mode="json")
    update_tenant(tenant_id, {"platform_credentials": platform_creds})

    logger.info("oauth.linkedin_connected", extra={"tenant_id": tenant_id})
    app_url = os.getenv("APP_URL", "http://localhost:3000")
    settings_url = f"{app_url.rstrip('/')}/settings"
    return RedirectResponse(url=settings_url, status_code=302)


@router.get("/x/authorize")
async def x_authorize(
    request: Request,
    tenant: TenantProfile = Depends(require_tenant),
):
    tier = getattr(request.state, "tenant_tier", "starter")
    limits = get_limits_for_tier(tier)
    max_connections = limits["max_platform_connections"]
    connected = len(tenant.platform_credentials or {})
    if connected >= max_connections:
        raise HTTPException(
            status_code=429,
            detail=f"Platform connection limit reached ({max_connections}). Upgrade to Pro.",
        )

    client_id = _get_oauth_credential("x_client_id", "x-client-id", "X_CLIENT_ID")
    if not client_id:
        raise HTTPException(
            status_code=501,
            detail="X OAuth not configured. Contact the administrator to configure OAuth credentials.",
        )

    api_url = os.getenv("API_URL") or os.getenv("APP_URL", "http://localhost:8080")
    redirect_uri = f"{api_url.rstrip('/')}/api/oauth/x/callback"
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge_b64 = base64.urlsafe_b64encode(code_challenge).rstrip(b"=").decode()
    nonce = secrets.token_urlsafe(16)
    state = _oauth_state(tenant.tenant_id, nonce)

    # Store state with owner identity and PKCE verifier
    _store_oauth_state(
        state=state,
        owner_uid=request.state.uid,
        tenant_id=tenant.tenant_id,
        code_verifier=code_verifier,
    )

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "tweet.read tweet.write users.read offline.access",
        "code_challenge": code_challenge_b64,
        "code_challenge_method": "S256",
        "state": state,
    }
    url = f"{X_AUTH}?{urllib.parse.urlencode(params)}"
    return {"redirect_url": url}


@router.get("/x/callback")
async def x_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        raise HTTPException(status_code=400, detail=f"X auth error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    # Verify state and retrieve stored owner identity + PKCE verifier
    state_doc = _consume_oauth_state(state)
    if not state_doc:
        raise HTTPException(
            status_code=400, detail="Expired or invalid state; restart OAuth flow"
        )

    code_verifier = state_doc.get("code_verifier")
    if not code_verifier:
        raise HTTPException(
            status_code=400, detail="Missing PKCE verifier; restart OAuth flow"
        )

    tenant_id = state_doc.get("tenant_id", "")
    if not _verify_state(state, tenant_id):
        raise HTTPException(status_code=400, detail="Invalid state")

    tenant_doc = get_tenant(tenant_id)
    if not tenant_doc:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Verify the callback is for the same user who initiated the flow
    stored_uid = state_doc.get("owner_uid", "")
    tenant_owner_uid = tenant_doc.get("owner_uid", "")
    if stored_uid != tenant_owner_uid:
        logger.warning(
            "oauth.x_uid_mismatch",
            extra={"tenant_id": tenant_id, "stored_uid": stored_uid},
        )
        raise HTTPException(status_code=403, detail="OAuth flow ownership mismatch")

    client_id = _get_oauth_credential("x_client_id", "x-client-id", "X_CLIENT_ID")
    client_secret = _get_oauth_credential(
        "x_client_secret", "x-client-secret", "X_CLIENT_SECRET"
    )
    if not client_id or not client_secret:
        raise HTTPException(status_code=501, detail="X OAuth not configured")

    api_url = os.getenv("API_URL") or os.getenv("APP_URL", "http://localhost:8080")
    redirect_uri = f"{api_url.rstrip('/')}/api/oauth/x/callback"

    basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            X_TOKEN,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic_auth}",
            },
        )
    if token_resp.status_code != 200:
        logger.warning("oauth.x_token_failed", extra={"status": token_resp.status_code})
        raise HTTPException(status_code=400, detail="Failed to exchange X code")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token in X response")

    # Fetch the actual X user ID instead of storing the scope string
    x_user_id = "x_user_unknown"
    try:
        async with httpx.AsyncClient() as client:
            me_resp = await client.get(
                X_ME,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if me_resp.status_code == 200:
            me_data = me_resp.json()
            x_user_id = me_data.get("data", {}).get("id", x_user_id)
    except Exception as exc:
        logger.warning("oauth.x_me_failed", extra={"error": str(exc)})

    expires_in = token_data.get("expires_in", 7200)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    creds = PlatformCredentials(
        access_token=access_token,
        refresh_token=token_data.get("refresh_token"),
        expires_at=expires_at,
        platform_id=x_user_id,
    )
    platform_creds = tenant_doc.get("platform_credentials") or {}
    platform_creds["x_twitter"] = creds.model_dump(mode="json")
    update_tenant(tenant_id, {"platform_credentials": platform_creds})

    logger.info("oauth.x_connected", extra={"tenant_id": tenant_id})
    app_url = os.getenv("APP_URL", "http://localhost:3000")
    settings_url = f"{app_url.rstrip('/')}/settings"
    return RedirectResponse(url=settings_url, status_code=302)


@router.get("/status")
async def oauth_status(tenant: TenantProfile = Depends(require_tenant)):
    creds = tenant.platform_credentials or {}
    linkedin_cred = creds.get("linkedin") or {}
    x_cred = creds.get("x_twitter") or {}
    linkedin_expires_at = linkedin_cred.get("expires_at")
    x_expires_at = x_cred.get("expires_at")
    return {
        "linkedin": bool(linkedin_cred.get("access_token")),
        "x_twitter": bool(x_cred.get("access_token")),
        "linkedin_expires_at": linkedin_expires_at.isoformat()
        if linkedin_expires_at and hasattr(linkedin_expires_at, "isoformat")
        else (str(linkedin_expires_at) if linkedin_expires_at else None),
        "x_twitter_expires_at": x_expires_at.isoformat()
        if x_expires_at and hasattr(x_expires_at, "isoformat")
        else (str(x_expires_at) if x_expires_at else None),
    }


class DisconnectRequest(BaseModel):
    platform: str


@router.post("/disconnect")
async def oauth_disconnect(
    body: DisconnectRequest,
    tenant: TenantProfile = Depends(require_tenant),
):
    platform = (body.platform or "").strip().lower()
    if platform not in ("linkedin", "x_twitter"):
        raise HTTPException(
            status_code=400,
            detail="Invalid platform. Use linkedin or x_twitter.",
        )
    creds = dict(tenant.platform_credentials or {})
    if platform in creds:
        del creds[platform]
        update_tenant(tenant.tenant_id, {"platform_credentials": creds})
        logger.info(
            "oauth.disconnected",
            extra={"tenant_id": tenant.tenant_id, "platform": platform},
        )
    return {"ok": True, "platform": platform}
