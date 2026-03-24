from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.routes import drafts, settings
from shared.models import DailyPostResult, TenantProfile
from shared.settings_limits import (
    COMPETITOR_LIMIT,
    DESCRIPTION_MAX_CHARS,
    TARGET_AUDIENCE_MAX_CHARS,
)


def _tenant(**overrides) -> TenantProfile:
    base = {
        "tenant_id": "tenant-1",
        "owner_uid": "uid-1",
        "owner_email": "owner@example.com",
        "company_name": "Intonation Labs",
        "industry": "AI consulting",
        "description": "Original company description",
        "target_audience": "Founders and CTOs",
        "platforms_enabled": [
            "linkedin",
            "x_twitter",
            "instagram",
            "google_business_profile",
            "tiktok",
            "xiaohongshu",
        ],
        "subscription_tier": "starter",
        "subscription_status": "free",
        "daily_digest_email": "owner@example.com",
        "created_at": datetime(2026, 3, 13, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return TenantProfile.model_validate(base)


def test_quick_generate_request_rejects_unsupported_platform():
    with pytest.raises(ValidationError):
        drafts.QuickGenerateRequest(platform="facebook")


def test_daily_post_result_normalizes_hashtag_string():
    result = DailyPostResult(
        headline="Headline",
        linkedin_post="Post",
        hashtags="#AIStrategy #DataEngineering #IntonationLabs #EnterpriseAI",
    )

    assert result.hashtags == [
        "#AIStrategy",
        "#DataEngineering",
        "#IntonationLabs",
        "#EnterpriseAI",
    ]


def test_quick_generate_persists_real_draft(monkeypatch):
    stored: dict = {}

    async def fake_generate_daily_post(
        *,
        intelligence_summaries,
        brand_context=None,
        tenant_id=None,
        intelligence_items=None,
        tier="starter",
    ):
        assert intelligence_summaries
        assert tenant_id == "tenant-1"
        assert tier == "starter"
        return DailyPostResult(
            headline="Tailored company update",
            linkedin_post="LinkedIn variant",
            x_post="X variant",
            instagram_caption="Instagram variant",
            google_business_profile_post="Visit us for a tailored AI roadmap.",
            tiktok_caption="TikTok variant",
            xiaohongshu_post="Xiaohongshu variant",
            why_it_matters="Because tailored content performs better.",
            hashtags=["AI", "Strategy"],
            image_prompt="",
        )

    def fake_retrieve(self, query_text, language="en"):
        assert "Intonation Labs" in query_text
        return ([{"text": "Brand context", "doc_type": "service_description"}], False)

    def fake_add_doc(collection, data, doc_id=None, tenant_id=None):
        stored.update(
            {
                "collection": collection,
                "data": data,
                "doc_id": doc_id,
                "tenant_id": tenant_id,
            }
        )
        return "draft-1"

    monkeypatch.setattr(drafts, "query_docs", lambda *args, **kwargs: [])
    monkeypatch.setattr(drafts, "add_doc", fake_add_doc)
    monkeypatch.setattr("shared.retriever.Retriever.retrieve", fake_retrieve)
    monkeypatch.setattr(
        "engines.post_generate.generate_daily_post",
        fake_generate_daily_post,
    )

    response = asyncio.run(
        drafts.quick_generate(
            drafts.QuickGenerateRequest(platform="google_business_profile"),
            request=SimpleNamespace(
                state=SimpleNamespace(tenant_tier="starter", email_verified=True)
            ),
            tenant=_tenant(),
        )
    )

    assert response["id"] == "draft-1"
    assert response["platform"] == "google_business_profile"
    assert response["text"] == "Visit us for a tailored AI roadmap."
    assert response["content_by_platform"]["tiktok"] == "TikTok variant"
    assert response["platforms_generated"] == [
        "linkedin",
        "x_twitter",
        "instagram",
        "google_business_profile",
        "tiktok",
        "xiaohongshu",
    ]
    assert stored["collection"] == "drafts"
    assert stored["tenant_id"] == "tenant-1"
    assert stored["data"]["origin"] == "quick_generate"
    assert stored["data"]["headline"] == "Tailored company update"
    assert stored["data"]["platform"] == "google_business_profile"


def test_list_drafts_falls_back_when_indexed_query_fails(monkeypatch):
    draft_docs = [
        {
            "id": "draft-older",
            "status": "draft",
            "batch_date": "2026-03-10",
            "created_at": datetime(2026, 3, 10, 8, tzinfo=timezone.utc),
        },
        {
            "id": "draft-newer",
            "status": "draft",
            "batch_date": "2026-03-11",
            "created_at": datetime(2026, 3, 11, 8, tzinfo=timezone.utc),
        },
        {
            "id": "draft-scheduled",
            "status": "scheduled",
            "batch_date": "2026-03-12",
            "created_at": datetime(2026, 3, 12, 8, tzinfo=timezone.utc),
        },
    ]

    def fake_query_docs_paginated(*args, **kwargs):
        raise RuntimeError("missing composite index")

    def fake_query_docs(
        collection, filters=None, order_by=None, limit=None, *, tenant_id=None
    ):
        assert collection == "drafts"
        assert tenant_id == "tenant-1"
        assert filters is None
        assert order_by is None
        assert limit == 500
        return draft_docs

    monkeypatch.setattr(drafts, "query_docs_paginated", fake_query_docs_paginated)
    monkeypatch.setattr(drafts, "query_docs", fake_query_docs, raising=False)

    response = asyncio.run(
        drafts.list_drafts(status="draft", limit=1, tenant=_tenant())
    )

    assert [item["id"] for item in response["drafts"]] == ["draft-newer"]
    assert response["next_cursor"] == "draft-newer"


def test_draft_feedback_persists_thumbs_and_reason(monkeypatch):
    updates: list[dict] = []

    def fake_get_doc(collection, doc_id, *, tenant_id=None):
        assert collection == "drafts"
        assert doc_id == "d1"
        return {"id": "d1", "headline": "H"}

    def fake_update_doc(collection, doc_id, data, *, tenant_id=None):
        updates.append(
            {
                "collection": collection,
                "doc_id": doc_id,
                "data": data,
                "tenant_id": tenant_id,
            }
        )

    monkeypatch.setattr(drafts, "get_doc", fake_get_doc)
    monkeypatch.setattr(drafts, "update_doc", fake_update_doc)

    body = drafts.DraftFeedbackRequest(thumbs="down", reason="Too generic")
    result = asyncio.run(drafts.draft_feedback("d1", body, tenant=_tenant()))

    assert result["ok"] is True
    assert result["thumbs"] == "down"
    assert len(updates) == 1
    assert updates[0]["data"]["feedback_thumbs"] == "down"
    assert updates[0]["data"]["feedback_reason"] == "Too generic"
    assert "feedback_at" in updates[0]["data"]


def test_update_settings_normalizes_platforms_and_clamps_text(monkeypatch):
    captured: dict = {}

    def fake_update_tenant(tenant_id, updates):
        captured["tenant_id"] = tenant_id
        captured["updates"] = updates

    monkeypatch.setattr(settings, "update_tenant", fake_update_tenant)

    body = settings.SettingsUpdate(
        description="x" * (DESCRIPTION_MAX_CHARS + 25),
        target_audience="y" * (TARGET_AUDIENCE_MAX_CHARS + 25),
        competitor_names=[" Alpha ", "", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"],
        industry_keywords=[" AI strategy ", "", "Enterprise delivery"],
        platforms_enabled=["linkedin", "linkedin", "tiktok", "unknown"],
    )

    response = asyncio.run(settings.update_settings(body, tenant=_tenant()))

    assert response["ok"] is True
    assert captured["tenant_id"] == "tenant-1"
    assert len(captured["updates"]["description"]) == DESCRIPTION_MAX_CHARS
    assert len(captured["updates"]["target_audience"]) == TARGET_AUDIENCE_MAX_CHARS
    assert (
        captured["updates"]["competitor_names"]
        == [
            "Alpha",
            "Beta",
            "Gamma",
            "Delta",
            "Epsilon",
        ][:COMPETITOR_LIMIT]
    )
    assert captured["updates"]["industry_keywords"] == [
        "AI strategy",
        "Enterprise delivery",
    ]
    assert captured["updates"]["platforms_enabled"] == ["linkedin", "tiktok"]
