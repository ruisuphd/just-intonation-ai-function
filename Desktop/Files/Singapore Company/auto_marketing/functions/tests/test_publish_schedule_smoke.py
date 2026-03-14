from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from api.routes import analytics as analytics_routes
from api.routes import drafts
from engines import analytics_gatherer, publisher
from shared.models import TenantProfile


class FirestoreSmokeStore:
    def __init__(self):
        self.tenants: dict[str, dict] = {}
        self.collections: dict[str, dict[str, dict[str, dict]]] = {}

    def _tenant_bucket(self, tenant_id: str) -> dict[str, dict]:
        return self.collections.setdefault(tenant_id, {})

    def get_doc(self, collection: str, doc_id: str, tenant_id: str | None = None):
        if tenant_id is None:
            if collection == "tenants":
                return self.tenants.get(doc_id)
            return None
        return self._tenant_bucket(tenant_id).get(collection, {}).get(doc_id)

    def get_tenant(self, tenant_id: str):
        return self.tenants.get(tenant_id)

    def set_doc(
        self, collection: str, doc_id: str, data: dict, tenant_id: str | None = None
    ):
        if tenant_id is None:
            if collection == "tenants":
                self.tenants[doc_id] = {"id": doc_id, **data}
            return
        bucket = self._tenant_bucket(tenant_id).setdefault(collection, {})
        bucket[doc_id] = {"id": doc_id, **data}

    def update_doc(
        self, collection: str, doc_id: str, data: dict, tenant_id: str | None = None
    ):
        existing = self.get_doc(collection, doc_id, tenant_id)
        assert existing is not None, f"Missing doc {collection}/{doc_id}"
        merged = {**existing, **data}
        self.set_doc(collection, doc_id, merged, tenant_id)

    def query_docs(
        self,
        collection: str,
        filters: list[tuple[str, str, object]] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        tenant_id: str | None = None,
    ):
        if tenant_id is None:
            docs = list(self.tenants.values()) if collection == "tenants" else []
        else:
            docs = list(self._tenant_bucket(tenant_id).get(collection, {}).values())

        def coerce(value):
            if hasattr(value, "to_datetime"):
                return value.to_datetime()
            return value

        def matches(doc: dict) -> bool:
            for field, op, value in filters or []:
                current = coerce(doc.get(field))
                target = coerce(value)
                if op == "==" and current != target:
                    return False
                if op == "array_contains" and target not in (current or []):
                    return False
                if op == ">=" and (current is None or current < target):
                    return False
            return True

        filtered = [doc for doc in docs if matches(doc)]
        if order_by:
            reverse = order_by.startswith("-")
            key_name = order_by.lstrip("-")
            filtered.sort(
                key=lambda item: coerce(item.get(key_name))
                or datetime.min.replace(tzinfo=timezone.utc),
                reverse=reverse,
            )
        if limit is not None:
            filtered = filtered[:limit]
        return filtered

    def query_collection_group(
        self,
        collection: str,
        filters: list[tuple[str, str, object]] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ):
        docs = []
        for tenant_id, tenant_collections in self.collections.items():
            for doc in tenant_collections.get(collection, {}).values():
                docs.append({**doc, "tenant_id": tenant_id})

        def coerce(value):
            if hasattr(value, "to_datetime"):
                return value.to_datetime()
            return value

        def matches(doc: dict) -> bool:
            for field, op, value in filters or []:
                current = coerce(doc.get(field))
                target = coerce(value)
                if op == "==" and current != target:
                    return False
                if op == "<=" and (current is None or current > target):
                    return False
                if op == ">=" and (current is None or current < target):
                    return False
            return True

        filtered = [doc for doc in docs if matches(doc)]
        if order_by:
            reverse = order_by.startswith("-")
            key_name = order_by.lstrip("-")
            filtered.sort(
                key=lambda item: coerce(item.get(key_name))
                or datetime.min.replace(tzinfo=timezone.utc),
                reverse=reverse,
            )
        if limit is not None:
            filtered = filtered[:limit]
        return filtered


def _tenant_profile() -> TenantProfile:
    return TenantProfile.model_validate(
        {
            "tenant_id": "tenant-1",
            "owner_uid": "uid-1",
            "owner_email": "owner@example.com",
            "company_name": "Intonation Labs",
            "industry": "AI consulting",
            "description": "Pipeline smoke test tenant",
            "target_audience": "CTOs",
            "platforms_enabled": ["linkedin", "x_twitter"],
            "subscription_tier": "pro",
            "subscription_status": "active",
            "daily_digest_email": "owner@example.com",
            "platform_credentials": {
                "linkedin": {
                    "access_token": "token-linkedin",
                    "platform_id": "org-1",
                },
                "x_twitter": {
                    "access_token": "token-x",
                    "platform_id": "acct-1",
                },
            },
            "created_at": datetime(2026, 3, 13, tzinfo=timezone.utc),
        }
    )


def test_publish_schedule_pipeline_smoke(monkeypatch):
    monkeypatch.setattr(publisher, "REAL_PUBLISHING_ENABLED", False)
    store = FirestoreSmokeStore()
    tenant = _tenant_profile()
    store.tenants[tenant.tenant_id] = {
        "id": tenant.tenant_id,
        **tenant.model_dump(mode="json"),
    }
    store.set_doc(
        "drafts",
        "draft-1",
        {
            "tenant_id": tenant.tenant_id,
            "headline": "AI expansion update",
            "platform": "linkedin",
            "platforms_generated": ["linkedin", "x_twitter"],
            "text": "LinkedIn-ready expansion update",
            "content_by_platform": {
                "linkedin": "LinkedIn-ready expansion update",
                "x_twitter": "Short X-ready expansion update",
            },
            "linkedin_post": "LinkedIn-ready expansion update",
            "x_post": "Short X-ready expansion update",
            "status": "draft",
            "batch_date": "2026-03-20",
            "created_at": datetime(2026, 3, 20, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 3, 20, tzinfo=timezone.utc),
        },
        tenant_id=tenant.tenant_id,
    )
    store.set_doc(
        "outreach_drafts",
        "outreach-1",
        {
            "lead_id": "lead-1",
            "status": "sent",
            "generated_at": datetime(2026, 3, 20, tzinfo=timezone.utc),
        },
        tenant_id=tenant.tenant_id,
    )
    store.set_doc(
        "qualified_leads",
        "lead-1",
        {
            "company_name": "Acme Robotics",
            "status": "meeting_booked",
            "created_at": datetime(2026, 3, 20, tzinfo=timezone.utc),
        },
        tenant_id=tenant.tenant_id,
    )
    store.set_doc(
        "prospect_signals",
        "signal-1",
        {
            "title": "Acme expanding AI team",
            "status": "qualified",
        },
        tenant_id=tenant.tenant_id,
    )

    for module in (drafts, publisher, analytics_gatherer, analytics_routes):
        monkeypatch.setattr(module, "query_docs", store.query_docs)
    monkeypatch.setattr(
        publisher, "query_collection_group", store.query_collection_group
    )
    monkeypatch.setattr(publisher, "get_tenant", store.get_tenant)
    monkeypatch.setattr(drafts, "get_doc", store.get_doc)
    monkeypatch.setattr(drafts, "set_doc", store.set_doc)
    monkeypatch.setattr(drafts, "update_doc", store.update_doc)
    monkeypatch.setattr(publisher, "get_doc", store.get_doc)
    monkeypatch.setattr(publisher, "update_doc", store.update_doc)
    monkeypatch.setattr(analytics_gatherer, "set_doc", store.set_doc)

    schedule_response = asyncio.run(
        drafts.update_draft_status(
            "draft-1",
            drafts.DraftStatusUpdate(status="scheduled", batch_date="2026-03-21"),
            tenant=tenant,
        )
    )
    assert schedule_response["ok"] is True
    assert (
        store.get_doc("drafts", "draft-1", tenant_id=tenant.tenant_id)["status"]
        == "scheduled"
    )
    assert (
        store.get_doc(
            "calendar_events", "social_post_draft-1", tenant_id=tenant.tenant_id
        )
        is not None
    )
    assert (
        store.get_doc(
            "publishing_records", "draft-1:linkedin", tenant_id=tenant.tenant_id
        )
        is not None
    )

    reschedule_response = asyncio.run(
        drafts.update_draft_status(
            "draft-1",
            drafts.DraftStatusUpdate(batch_date="2026-03-22"),
            tenant=tenant,
        )
    )
    assert reschedule_response["draft"]["batch_date"] == "2026-03-22"

    for record_id in ("draft-1:linkedin", "draft-1:x_twitter"):
        store.update_doc(
            "publishing_records",
            record_id,
            {"scheduled_for": datetime.now(timezone.utc) - timedelta(minutes=5)},
            tenant_id=tenant.tenant_id,
        )

    publish_result = asyncio.run(publisher.run_publisher())
    assert publish_result["published"] == 2
    assert (
        store.get_doc(
            "publishing_records", "draft-1:linkedin", tenant_id=tenant.tenant_id
        )["status"]
        == "published"
    )

    analytics_result = asyncio.run(analytics_gatherer.gather_daily_analytics())
    assert analytics_result["tenants_processed"] == 1
    snapshots = store.query_docs("analytics_snapshots", tenant_id=tenant.tenant_id)
    assert len(snapshots) == 1
    assert snapshots[0]["metrics_source"] == "placeholder_until_platform_apis"

    analytics_payload = asyncio.run(
        analytics_routes.get_analytics(days=14, tenant=tenant)
    )
    assert analytics_payload["summary"]["published_posts"] == 2
    assert analytics_payload["summary"]["qualified_leads"] == 1
    assert analytics_payload["summary"]["reply_received"] == 1
    assert analytics_payload["series"]
    assert analytics_payload["series"][0]["impressions"] == 0
