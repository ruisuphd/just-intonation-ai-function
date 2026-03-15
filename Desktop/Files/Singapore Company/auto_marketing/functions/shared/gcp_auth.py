from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import google.auth
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from shared.logger import get_logger

logger = get_logger("gcp_auth")


def resolve_project_id(default_project: str | None = None) -> str | None:
    return (
        os.getenv("GCP_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCLOUD_PROJECT")
        or default_project
    )


def _is_managed_runtime() -> bool:
    return bool(
        os.getenv("K_SERVICE")
        or os.getenv("FUNCTION_TARGET")
        or os.getenv("FUNCTION_NAME")
    )


def _is_reauth_error(exc: Exception) -> bool:
    return "reauthentication is needed" in str(exc).lower()


def _with_quota_project(credentials, quota_project_id: str | None):
    if not quota_project_id:
        return credentials

    current = getattr(credentials, "quota_project_id", None)
    if current == quota_project_id:
        return credentials

    attach = getattr(credentials, "with_quota_project", None)
    if callable(attach):
        try:
            return attach(quota_project_id)
        except Exception:
            return credentials
    return credentials


def _local_gcloud_credentials(
    project_id: str | None,
    *,
    quota_project_id: str | None,
) -> tuple[Credentials, str | None, datetime]:
    if _is_managed_runtime():
        raise RuntimeError("gcloud fallback is only available for local development")
    if shutil.which("gcloud") is None:
        raise RuntimeError("gcloud CLI is not available")

    try:
        completed = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RefreshError(
            f"Unable to refresh access token from gcloud: {exc}"
        ) from exc

    token = completed.stdout.strip()
    if not token:
        raise RefreshError("gcloud auth print-access-token returned an empty token")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=50)
    creds = Credentials(token=token, quota_project_id=quota_project_id)
    logger.warning(
        "gcp_auth.using_gcloud_auth_fallback",
        extra={"project": project_id, "quota_project_id": quota_project_id},
    )
    return creds, project_id, expires_at


def get_google_credentials(
    *,
    require_quota_project: bool = False,
) -> tuple[Credentials, str | None, datetime | None]:
    project_id = resolve_project_id()

    try:
        creds, default_project = google.auth.default()
        project_id = resolve_project_id(default_project)
        quota_project_id = project_id if require_quota_project else None
        creds = _with_quota_project(creds, quota_project_id)

        if not getattr(creds, "valid", False) or getattr(creds, "expired", False):
            creds.refresh(Request())

        return creds, project_id, None
    except Exception as exc:
        if isinstance(exc, RefreshError) or _is_reauth_error(exc):
            try:
                quota_project_id = project_id if require_quota_project else None
                return _local_gcloud_credentials(
                    project_id,
                    quota_project_id=quota_project_id,
                )
            except Exception as fallback_exc:
                logger.warning(
                    "gcp_auth.gcloud_fallback_failed",
                    extra={"error": str(fallback_exc)},
                )

        if _is_reauth_error(exc):
            quota_hint = (
                f" and `gcloud auth application-default set-quota-project {project_id}`"
                if require_quota_project and project_id
                else ""
            )
            raise RuntimeError(
                "Google Application Default Credentials need reauthentication. "
                f"Run `gcloud auth application-default login`{quota_hint}, "
                "or provide GOOGLE_APPLICATION_CREDENTIALS."
            ) from exc
        raise
