from __future__ import annotations

from typing import Any

from google.cloud import firestore

from shared.logger import get_logger

logger = get_logger("firestore")

_db: firestore.Client | None = None


def get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def get_doc(collection: str, doc_id: str) -> dict | None:
    ref = get_db().collection(collection).document(doc_id)
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    data["id"] = snap.id
    return data


def set_doc(collection: str, doc_id: str, data: dict) -> None:
    get_db().collection(collection).document(doc_id).set(data)


def add_doc(collection: str, data: dict, doc_id: str | None = None) -> str:
    if doc_id:
        get_db().collection(collection).document(doc_id).set(data)
        return doc_id
    _, ref = get_db().collection(collection).add(data)
    return ref.id


def create_doc_if_absent(collection: str, doc_id: str, data: dict) -> bool:
    db = get_db()
    ref = db.collection(collection).document(doc_id)

    @firestore.transactional
    def _txn(transaction):
        snap = ref.get(transaction=transaction)
        if snap.exists:
            return False
        transaction.set(ref, data)
        return True

    return _txn(db.transaction())


def update_doc(collection: str, doc_id: str, data: dict) -> None:
    get_db().collection(collection).document(doc_id).update(data)


def delete_doc(collection: str, doc_id: str) -> None:
    get_db().collection(collection).document(doc_id).delete()


def query_docs(
    collection: str,
    filters: list[tuple[str, str, Any]] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    ref: Any = get_db().collection(collection)
    for field, op, value in (filters or []):
        ref = ref.where(field, op, value)
    if order_by:
        direction = firestore.Query.DESCENDING if order_by.startswith("-") else firestore.Query.ASCENDING
        field_name = order_by.lstrip("-")
        ref = ref.order_by(field_name, direction=direction)
    if limit:
        ref = ref.limit(limit)

    results = []
    for snap in ref.stream():
        doc = snap.to_dict()
        doc["id"] = snap.id
        results.append(doc)
    return results


def increment_field(
    collection: str,
    doc_id: str,
    field: str,
    amount: int = 1,
) -> int:
    db = get_db()
    ref = db.collection(collection).document(doc_id)

    @firestore.transactional
    def _txn(transaction):
        snap = ref.get(transaction=transaction)
        current = snap.to_dict().get(field, 0) if snap.exists else 0
        new_value = current + amount
        transaction.update(ref, {field: new_value})
        return new_value

    return _txn(db.transaction())


def batch_write(operations: list[dict]) -> None:
    """Execute batch writes.

    Each operation dict has keys:
        action: "set" | "update" | "delete"
        collection: str
        doc_id: str
        data: dict (not needed for delete)
    """
    db = get_db()
    batch = db.batch()
    for op in operations:
        ref = db.collection(op["collection"]).document(op["doc_id"])
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
