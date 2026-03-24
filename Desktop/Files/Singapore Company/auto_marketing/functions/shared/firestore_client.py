from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import google.auth
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.cloud import firestore
from google.oauth2.credentials import Credentials

from shared.logger import get_logger

logger = get_logger("firestore")

_db: firestore.Client | None = None
_db_expires_at: datetime | None = None
_db_lock = Lock()


def _resolve_project_id(default_project: str | None = None) -> str | None:
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


def _local_gcloud_credentials(
    project: str | None,
) -> tuple[Credentials, str | None, datetime] | None:
    if _is_managed_runtime():
        return None
    if shutil.which("gcloud") is None:
        return None

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
    creds = Credentials(token=token)
    logger.warning(
        "firestore.using_gcloud_auth_fallback",
        extra={"project": project},
    )
    return creds, project, expires_at


def _client_kwargs() -> tuple[dict[str, Any], datetime | None]:
    project = _resolve_project_id()

    try:
        creds, default_project = google.auth.default()
        project = _resolve_project_id(default_project)

        if not getattr(creds, "valid", False) or getattr(creds, "expired", False):
            creds.refresh(Request())

        kwargs: dict[str, Any] = {}
        if project:
            kwargs["project"] = project
        kwargs["credentials"] = creds
        return kwargs, None
    except Exception as exc:
        fallback = None
        if isinstance(exc, RefreshError) or _is_reauth_error(exc):
            try:
                fallback = _local_gcloud_credentials(project)
            except Exception as fallback_exc:
                logger.warning(
                    "firestore.gcloud_auth_fallback_failed",
                    extra={"error": str(fallback_exc)},
                )

        if fallback is not None:
            creds, resolved_project, expires_at = fallback
            kwargs = {"credentials": creds}
            if resolved_project:
                kwargs["project"] = resolved_project
            return kwargs, expires_at

        if _is_reauth_error(exc):
            raise RuntimeError(
                "Google Application Default Credentials need reauthentication. "
                "Run `gcloud auth application-default login` or provide GOOGLE_APPLICATION_CREDENTIALS."
            ) from exc
        raise


def get_db() -> firestore.Client:
    global _db, _db_expires_at

    if _db is not None and (
        _db_expires_at is None or datetime.now(timezone.utc) < _db_expires_at
    ):
        return _db

    with _db_lock:
        if _db_expires_at is not None and datetime.now(timezone.utc) >= _db_expires_at:
            _db = None
            _db_expires_at = None
        if _db is None:
            kwargs, expires_at = _client_kwargs()
            _db = firestore.Client(**kwargs)
            _db_expires_at = expires_at
    return _db


def _resolve_collection(collection: str, tenant_id: str | None) -> str:
    if tenant_id is not None:
        if not tenant_id:
            raise ValueError("tenant_id must not be empty when provided")
        return f"tenants/{tenant_id}/{collection}"
    return collection


# ── Tenant helpers ────────────────────────────────────────────────────────────


def get_tenant(tenant_id: str) -> dict | None:
    if not tenant_id:
        raise ValueError("tenant_id is required")
    ref = get_db().collection("tenants").document(tenant_id)
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    data["id"] = snap.id
    return data


def create_tenant(tenant_id: str, profile: dict) -> None:
    if not tenant_id:
        raise ValueError("tenant_id is required")
    get_db().collection("tenants").document(tenant_id).set(profile)


def update_tenant(tenant_id: str, updates: dict) -> None:
    if not tenant_id:
        raise ValueError("tenant_id is required")
    get_db().collection("tenants").document(tenant_id).update(updates)


def query_tenants(
    filters: list[tuple[str, str, Any]] | None = None,
    limit: int | None = None,
    agency_id: str | None = None,
) -> list[dict]:
    _filters = filters or []
    if agency_id:
        _filters.append(("agency_id", "==", agency_id))
    return query_docs("tenants", filters=_filters, limit=limit, tenant_id=None)


# ── Generic CRUD ──────────────────────────────────────────────────────────────


def get_doc(
    collection: str, doc_id: str, *, tenant_id: str | None = None
) -> dict | None:
    path = _resolve_collection(collection, tenant_id)
    ref = get_db().collection(path).document(doc_id)
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    data["id"] = snap.id
    return data


def set_doc(
    collection: str, doc_id: str, data: dict, *, tenant_id: str | None = None
) -> None:
    path = _resolve_collection(collection, tenant_id)
    get_db().collection(path).document(doc_id).set(data)


def add_doc(
    collection: str,
    data: dict,
    doc_id: str | None = None,
    *,
    tenant_id: str | None = None,
) -> str:
    path = _resolve_collection(collection, tenant_id)
    if doc_id:
        get_db().collection(path).document(doc_id).set(data)
        return doc_id
    _, ref = get_db().collection(path).add(data)
    return ref.id


def create_doc_if_absent(
    collection: str, doc_id: str, data: dict, *, tenant_id: str | None = None
) -> bool:
    db = get_db()
    path = _resolve_collection(collection, tenant_id)
    ref = db.collection(path).document(doc_id)

    @firestore.transactional
    def _txn(transaction):
        snap = ref.get(transaction=transaction)
        if snap.exists:
            return False
        transaction.set(ref, data)
        return True

    return _txn(db.transaction())


def update_doc(
    collection: str, doc_id: str, data: dict, *, tenant_id: str | None = None
) -> None:
    path = _resolve_collection(collection, tenant_id)
    get_db().collection(path).document(doc_id).update(data)


def delete_doc(collection: str, doc_id: str, *, tenant_id: str | None = None) -> None:
    path = _resolve_collection(collection, tenant_id)
    get_db().collection(path).document(doc_id).delete()


def query_docs(
    collection: str,
    filters: list[tuple[str, str, Any]] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    *,
    tenant_id: str | None = None,
) -> list[dict]:
    """Query documents. For paginated results, use query_docs_paginated."""
    docs, _ = query_docs_paginated(
        collection,
        filters=filters,
        order_by=order_by,
        limit=limit,
        tenant_id=tenant_id,
    )
    return docs


def query_docs_paginated(
    collection: str,
    filters: list[tuple[str, str, Any]] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    *,
    tenant_id: str | None = None,
    start_after_id: str | None = None,
) -> tuple[list[dict], str | None]:
    """Query documents with cursor-based pagination. Returns (docs, next_cursor).
    Pass next_cursor as start_after_id for the next page. next_cursor is None when
    there are no more results."""
    path = _resolve_collection(collection, tenant_id)
    ref: Any = get_db().collection(path)
    for field, op, value in filters or []:
        ref = ref.where(field, op, value)
    if order_by:
        direction = (
            firestore.Query.DESCENDING
            if order_by.startswith("-")
            else firestore.Query.ASCENDING
        )
        field_name = order_by.lstrip("-")
        ref = ref.order_by(field_name, direction=direction)
    if start_after_id:
        cursor_ref = get_db().collection(path).document(start_after_id)
        cursor_snap = cursor_ref.get()
        if cursor_snap.exists:
            ref = ref.start_after(cursor_snap)
    use_pagination = limit is not None and limit > 0
    fetch_limit = (limit + 1) if use_pagination else 10000
    ref = ref.limit(fetch_limit)

    results = []
    for snap in ref.stream():
        doc = snap.to_dict()
        doc["id"] = snap.id
        results.append(doc)

    next_cursor = None
    if use_pagination and len(results) > limit:
        next_cursor = results[limit]["id"]
        results = results[:limit]

    return results, next_cursor


def count_docs(
    collection: str,
    filters: list[tuple[str, str, Any]] | None = None,
    *,
    tenant_id: str | None = None,
) -> int:
    """Return document count for a query (Firestore aggregation)."""
    path = _resolve_collection(collection, tenant_id)
    ref: Any = get_db().collection(path)
    for field, op, value in filters or []:
        ref = ref.where(field, op, value)
    results = ref.count().get()
    if not results:
        return 0
    return int(results[0].value)


def increment_field(
    collection: str,
    doc_id: str,
    field: str,
    amount: int = 1,
    *,
    tenant_id: str | None = None,
) -> int:
    db = get_db()
    path = _resolve_collection(collection, tenant_id)
    ref = db.collection(path).document(doc_id)

    @firestore.transactional
    def _txn(transaction):
        snap = ref.get(transaction=transaction)
        current = snap.to_dict().get(field, 0) if snap.exists else 0
        new_value = current + amount
        transaction.update(ref, {field: new_value})
        return new_value

    return _txn(db.transaction())


def batch_write(operations: list[dict]) -> None:
    """Execute batch writes. Each operation dict has keys:
    action: "set" | "update" | "delete"
    collection: str
    doc_id: str
    data: dict (not needed for delete)
    tenant_id: str | None (optional)
    """
    db = get_db()
    batch = db.batch()
    for op in operations:
        path = _resolve_collection(op["collection"], op.get("tenant_id"))
        ref = db.collection(path).document(op["doc_id"])
        action = op["action"]
        if action == "set":
            batch.set(ref, op["data"])
        elif action == "update":
            batch.update(ref, op["data"])
        elif action == "delete":
            batch.delete(ref)
        else:
            raise ValueError(f"Unknown batch action: {action}")
    batch.commit()


def query_collection_group(
    collection: str,
    filters: list[tuple[str, str, Any]] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Query across all subcollections with the given name (collection group query).

    Returns documents with 'id' and 'tenant_id' (extracted from parent path).
    Requires a Firestore collection group index.
    """
    ref: Any = get_db().collection_group(collection)
    for field, op, value in filters or []:
        ref = ref.where(field, op, value)
    if order_by:
        direction = (
            firestore.Query.DESCENDING
            if order_by.startswith("-")
            else firestore.Query.ASCENDING
        )
        field_name = order_by.lstrip("-")
        ref = ref.order_by(field_name, direction=direction)
    if limit:
        ref = ref.limit(limit)

    results = []
    for snap in ref.stream():
        doc = snap.to_dict()
        doc["id"] = snap.id
        # Extract tenant_id from parent path: tenants/{tenant_id}/collection
        path_parts = snap.reference.path.split("/")
        if len(path_parts) >= 2 and path_parts[0] == "tenants":
            doc["tenant_id"] = path_parts[1]
        results.append(doc)
    return results
