from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from api.routes import analytics as analytics_routes
from api.routes import drafts, leads
from engines import analytics_gatherer, linkedin_enrichment
from shared.models import TenantProfile


def _tenant(**overrides) -> TenantProfile:
    base = {
        "tenant_id": "tenant-1",
        "owner_uid": "uid-1",
        "owner_email": "owner@example.com",
        "company_name": "Intonation Labs",
        "industry": "AI consulting",
        "description": "Original company description",
        "target_audience": "Founders and CTOs",
        "platforms_enabled": ["linkedin", "x_twitter"],
        "subscription_tier": "pro",
        "subscription_status": "active",
        "daily_digest_email": "owner@example.com",
        "created_at": datetime(2026, 3, 13, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return TenantProfile.model_validate(base)


def test_update_draft_status_creates_calendar_and_publishing_records(monkeypatch):
    updated_payload: dict = {}
    written_docs: list[tuple[str, str, dict, str | None]] = []

    existing_draft = {
        "id": "draft-1",
        "status": "draft",
        "batch_date": "2026-03-13",
        "platform": "linkedin",
        "platforms_generated": ["linkedin", "x_twitter"],
        "headline": "Important update",
    }

    def fake_get_doc(collection, doc_id, tenant_id=None):
        if collection == "drafts":
            return existing_draft
        return None

    def fake_update_doc(collection, doc_id, payload, tenant_id=None):
        updated_payload.update(payload)

    def fake_set_doc(collection, doc_id, payload, tenant_id=None):
        written_docs.append((collection, doc_id, payload, tenant_id))

    monkeypatch.setattr(drafts, "get_doc", fake_get_doc)
    monkeypatch.setattr(drafts, "update_doc", fake_update_doc)
    monkeypatch.setattr(drafts, "set_doc", fake_set_doc)

    response = asyncio.run(
        drafts.update_draft_status(
            "draft-1",
            drafts.DraftStatusUpdate(status="scheduled", batch_date="2026-03-18"),
            tenant=_tenant(subscription_tier="starter"),
        )
    )

    assert response["ok"] is True
    assert updated_payload["status"] == "scheduled"
    assert updated_payload["batch_date"] == "2026-03-18"
    assert "scheduled_for" in updated_payload
    assert any(
        collection == "calendar_events" and doc_id == "social_post_draft-1"
        for collection, doc_id, _, _ in written_docs
    )
    publishing_doc_ids = sorted(
        doc_id
        for collection, doc_id, _, _ in written_docs
        if collection == "publishing_records"
    )
    assert publishing_doc_ids == ["draft-1:linkedin", "draft-1:x_twitter"]


def test_list_leads_merges_latest_outreach_copy(monkeypatch):
    def fake_query_docs(collection, **kwargs):
        if collection == "qualified_leads":
            return [
                {
                    "id": "lead-1",
                    "company_name": "Acme Robotics",
                    "icp_fit": "high",
                    "icp_fit_score": 0.91,
                    "suggested_outreach_angle": "Series A support",
                    "status": "new",
                }
            ]
        if collection == "outreach_drafts":
            return [
                {
                    "lead_id": "lead-1",
                    "draft_type": "cold_email",
                    "status": "approved",
                    "content": {
                        "subject": "Helping Acme scale delivery",
                        "body": "Here is the full outreach draft body.",
                    },
                }
            ]
        return []

    def fake_query_docs_paginated(collection, **kwargs):
        docs = fake_query_docs(collection, **kwargs)
        return (docs, None)

    monkeypatch.setattr(leads, "query_docs_paginated", fake_query_docs_paginated)
    monkeypatch.setattr(leads, "query_docs", fake_query_docs)

    response = asyncio.run(leads.list_leads(limit=20, tenant=_tenant()))

    assert response["leads"][0]["draft_subject"] == "Helping Acme scale delivery"
    assert (
        response["leads"][0]["draft_content"] == "Here is the full outreach draft body."
    )
    assert response["leads"][0]["outreach_status"] == "approved"


def test_get_analytics_aggregates_snapshots_and_funnel(monkeypatch):
    def fake_query_docs(collection, **kwargs):
        if collection == "analytics_snapshots":
            return [
                {
                    "id": "2026-03-13",
                    "measured_at": "2026-03-13T00:00:00+00:00",
                    "post_metrics": [
                        {"impressions": 120, "likes": 8, "comments": 2, "shares": 1},
                    ],
                    "outreach_metrics": [
                        {"open_rate": 0.41},
                    ],
                },
                {
                    "id": "2026-03-14",
                    "measured_at": "2026-03-14T00:00:00+00:00",
                    "post_metrics": [
                        {"impressions": 180, "likes": 10, "comments": 4, "shares": 3},
                    ],
                    "outreach_metrics": [
                        {"open_rate": 0.59},
                    ],
                },
            ]
        if collection == "publishing_records":
            return [{"id": "pub-1"}, {"id": "pub-2"}]
        if collection == "prospect_signals":
            return [{"id": "sig-1"}, {"id": "sig-2"}, {"id": "sig-3"}]
        if collection == "qualified_leads":
            return [
                {"id": "lead-1", "status": "new"},
                {"id": "lead-2", "status": "meeting_booked"},
            ]
        if collection == "outreach_drafts":
            return [{"id": "out-1", "status": "sent"}]
        return []

    monkeypatch.setattr(analytics_routes, "query_docs", fake_query_docs)

    response = asyncio.run(
        analytics_routes.get_analytics(
            days=14, tenant=_tenant(subscription_tier="starter")
        )
    )

    assert response["summary"]["total_impressions"] == 300
    assert response["summary"]["avg_open_rate"] == 0.5
    assert response["summary"]["qualified_leads"] == 2
    assert response["summary"]["signals_detected"] == 3
    assert response["summary"]["reply_received"] == 1
    assert len(response["series"]) == 2


def test_gather_daily_analytics_writes_snapshot_to_tenant_collection(monkeypatch):
    writes: list[tuple[str, str, dict, str | None]] = []

    def fake_query_docs(collection, **kwargs):
        tenant_id = kwargs.get("tenant_id")
        if collection == "tenants":
            return [{"id": "tenant-1"}]
        if collection == "publishing_records" and tenant_id == "tenant-1":
            return [{"post_id": "draft-1", "status": "published"}]
        if collection == "outreach_drafts" and tenant_id == "tenant-1":
            return [{"id": "outreach-1"}]
        return []

    def fake_set_doc(collection, doc_id, payload, tenant_id=None):
        writes.append((collection, doc_id, payload, tenant_id))

    monkeypatch.setattr(analytics_gatherer, "query_docs", fake_query_docs)
    monkeypatch.setattr(analytics_gatherer, "set_doc", fake_set_doc)

    result = asyncio.run(analytics_gatherer.gather_daily_analytics())

    assert result["tenants_processed"] == 1
    assert writes
    assert writes[0][0] == "analytics_snapshots"
    assert writes[0][3] == "tenant-1"


def test_linkedin_enrichment_uses_qualified_leads_collection(monkeypatch):
    update_calls: list[tuple[str, dict]] = []

    def fake_get_doc(collection, doc_id, tenant_id=None):
        assert collection == "qualified_leads"
        return {
            "company_name": "Acme Robotics",
            "contact_linkedin_url": "https://linkedin.com/in/example",
        }

    def fake_update_doc(collection, doc_id, payload, tenant_id=None):
        update_calls.append((collection, payload))

    monkeypatch.setattr(linkedin_enrichment, "get_doc", fake_get_doc)
    monkeypatch.setattr(linkedin_enrichment, "update_doc", fake_update_doc)

    asyncio.run(linkedin_enrichment.enrich_lead("tenant-1", "lead-1"))

    assert update_calls
    assert update_calls[0][0] == "qualified_leads"
    assert update_calls[0][1]["enrichment_status"] == "completed"
