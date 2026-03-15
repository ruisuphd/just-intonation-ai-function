from __future__ import annotations

import os

from google.cloud import secretmanager

from shared.logger import get_logger

logger = get_logger("secrets")

_client: secretmanager.SecretManagerServiceClient | None = None
_cache: dict[str, str] = {}


def _get_client() -> secretmanager.SecretManagerServiceClient:
    global _client
    if _client is None:
        _client = secretmanager.SecretManagerServiceClient()
    return _client


def get_secret(secret_id: str, version: str = "latest") -> str:
    if secret_id in _cache:
        return _cache[secret_id]

    project = os.getenv("GCP_PROJECT_ID")
    name = f"projects/{project}/secrets/{secret_id}/versions/{version}"

    try:
        response = _get_client().access_secret_version(request={"name": name})
        value = response.payload.data.decode("utf-8")
        _cache[secret_id] = value
        logger.info("secrets.accessed", extra={"secret_id": secret_id})
        return value
    except Exception as exc:
        logger.error("secrets.error", extra={"secret_id": secret_id, "error": str(exc)})
        raise


def get_secret_or_env(
    *,
    secret_id: str,
    env_var: str,
    version: str = "latest",
    default: str | None = None,
) -> str | None:
    env_value = os.getenv(env_var)
    if env_value:
        return env_value

    try:
        return get_secret(secret_id, version=version)
    except Exception:
        logger.warning(
            "secrets.fallback_to_default",
            extra={"secret_id": secret_id, "env_var": env_var},
        )
        return default
