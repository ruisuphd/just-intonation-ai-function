from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from engines import email_builder
from engines import image_generate
from engines import intelligence
from engines import outreach_generate
import pipeline as pipeline_module
from engines import post_generate
from engines import qualification
from engines import signals
from shared.models import DailyPostResult
from shared.retriever import Retriever


def test_run_pipeline_returns_summary(monkeypatch):
    intel_items = [
        {
            "title": "AI consulting demand rises in Singapore",
            "summary": "Firms are investing in AI transformation work.",
            "source_name": "Google News",
            "source_url": "https://example.com/news-1",
            "relevance_score": 0.92,
            "tags": ["ai", "consulting"],
        },
        {
            "title": "European enterprises expand AI budgets",
            "summary": "Budget growth is accelerating in Europe.",
            "source_name": "Google News",
            "source_url": "https://example.com/news-2",
            "relevance_score": 0.88,
            "tags": ["europe"],
        },
    ]
    signals_found = [
        {
            "company_name": "Acme Robotics",
            "title": "Acme Robotics raises Series A",
            "summary": "Fresh funding for AI deployment.",
        }
    ]
    sent = {}

    async def fake_run_and_return_items(*, sources, tenant_id=None):
        assert sources
        assert tenant_id is None
        return intel_items

    async def fake_generate_daily_post(
        *,
        intelligence_summaries,
        intelligence_items,
        brand_context,
        tenant_id=None,
    ):
        assert intelligence_summaries
        assert intelligence_items
        assert brand_context
        assert tenant_id is None
        return DailyPostResult(
            headline="Hook EN",
            linkedin_post="English post",
            x_post="Short post",
            instagram_caption="Caption",
            google_business_profile_post="Google Business post",
            tiktok_caption="TikTok caption",
            xiaohongshu_post="Xiaohongshu post",
            why_it_matters="Why it matters",
            hashtags=["AI", "Consulting"],
            image_prompt="Generate a modern AI consulting graphic.",
        )

    async def fake_generate_image(prompt):
        assert prompt
        return b"png-bytes"

    async def fake_run_and_classify(*, sources, max_signals, tenant_id=None):
        assert sources
        assert max_signals == 8
        assert tenant_id is None
        return signals_found

    async def fake_qualify_inline(signal_data, *, tenant_id=None):
        assert signal_data["company_name"] == "Acme Robotics"
        assert tenant_id is None
        return {
            "company_name": "Acme Robotics",
            "icp_fit": "high",
            "icp_fit_score": 0.91,
            "suggested_outreach_angle": "Series A expansion support",
        }

    async def fake_generate_outreach_inline(lead_data, signal_data, *, tenant_id=None):
        assert lead_data["company_name"] == signal_data["company_name"]
        assert tenant_id is None
        return {
            "linkedin_dm": "Congrats on the raise.",
            "cold_email": {
                "subject": "Helping Acme Robotics scale AI delivery",
                "body": "Body copy",
            },
        }

    def fake_retrieve(self, query_text, language="en"):
        assert query_text
        return ([{"text": "Brand context", "doc_type": "service_description"}], False)

    def fake_send_daily_brief(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(
        pipeline_module,
        "_load_digest_config",
        lambda: pipeline_module.DigestConfig(
            enabled=True,
            recipient_email="founder@intonationlabs.ai",
            timezone_name="Asia/Singapore",
            top_k_intelligence=2,
        ),
    )
    monkeypatch.setattr(
        pipeline_module, "_claim_daily_digest_send", lambda **kwargs: True
    )
    monkeypatch.setattr(
        pipeline_module, "_update_daily_digest_send", lambda **kwargs: None
    )
    monkeypatch.setattr(intelligence, "run_and_return_items", fake_run_and_return_items)
    monkeypatch.setattr(post_generate, "generate_daily_post", fake_generate_daily_post)
    monkeypatch.setattr(image_generate, "generate", fake_generate_image)
    monkeypatch.setattr(signals, "run_and_classify", fake_run_and_classify)
    monkeypatch.setattr(qualification, "qualify_inline", fake_qualify_inline)
    monkeypatch.setattr(
        outreach_generate,
        "generate_outreach_inline",
        fake_generate_outreach_inline,
    )
    monkeypatch.setattr(Retriever, "retrieve", fake_retrieve)
    monkeypatch.setattr(email_builder, "send_daily_brief", fake_send_daily_brief)

    result = asyncio.run(pipeline_module._run_pipeline())

    assert result["intel_items"] == 2
    assert result["post_generated"] is True
    assert result["image_generated"] is True
    assert result["leads_found"] == 1
    assert result["prospects_found"] == 0
    assert result["email_status"] == "sent"
    assert result["timezone"] == "Asia/Singapore"
    assert sent["post_draft"].linkedin_post == "English post"
    assert sent["post_status"] == "ready"
    assert sent["image_bytes"] == b"png-bytes"
    assert len(sent["lead_items"]) == 1
    assert sent["prospect_items"] == []
    assert sent["recipient_email"] == "founder@intonationlabs.ai"


def test_load_digest_config_reads_generation_settings(monkeypatch):
    monkeypatch.setattr(
        pipeline_module,
        "get_doc",
        lambda collection, doc_id: {
            "daily_digest_enabled": False,
            "daily_digest_email": "digest@intonationlabs.ai",
            "timezone": "Europe/Dublin",
            "top_k_intelligence": 4,
        },
    )

    config = pipeline_module._load_digest_config()

    assert config.enabled is False
    assert config.recipient_email == "digest@intonationlabs.ai"
    assert config.timezone_name == "Europe/Dublin"
    assert config.top_k_intelligence == 4


def test_run_pipeline_skips_duplicate_send(monkeypatch):
    sent = {"called": False}

    async def fake_run_and_return_items(*, sources, tenant_id=None):
        assert sources
        assert tenant_id is None
        return []

    async def fake_run_and_classify(*, sources, max_signals, tenant_id=None):
        assert sources
        assert max_signals == 8
        assert tenant_id is None
        return []

    def fake_send_daily_brief(**kwargs):
        sent["called"] = True

    monkeypatch.setattr(
        pipeline_module,
        "_load_digest_config",
        lambda: pipeline_module.DigestConfig(
            enabled=True,
            recipient_email=None,
            timezone_name="Asia/Singapore",
            top_k_intelligence=3,
        ),
    )
    monkeypatch.setattr(
        pipeline_module, "_claim_daily_digest_send", lambda **kwargs: False
    )
    monkeypatch.setattr(intelligence, "run_and_return_items", fake_run_and_return_items)
    monkeypatch.setattr(signals, "run_and_classify", fake_run_and_classify)
    monkeypatch.setattr(email_builder, "send_daily_brief", fake_send_daily_brief)

    result = asyncio.run(pipeline_module._run_pipeline())

    assert result["email_status"] == "skipped_duplicate"
    assert result["post_generated"] is False
    assert result["leads_found"] == 0
    assert result["prospects_found"] == 0
    assert sent["called"] is False


def test_build_html_renders_best_effort_prospect_state():
    html = email_builder._build_html(
        today="2026-03-10",
        post_draft=None,
        post_status="no_candidates",
        image_bytes=None,
        intel_items=[],
        lead_items=[],
        prospect_items=[
            {
                "company_name": "Acme Labs",
                "signal_summary": "Hiring an AI product lead after a recent launch.",
                "fit_reasoning": "The company is adjacent to the ICP but smaller than the ideal buyer.",
                "approach_suggestion": "Lead with a short audit offer tied to launch velocity.",
                "recommended_channel": "LinkedIn",
                "channel_reason": "A lighter-touch opener fits the weaker signal.",
                "linkedin_dm": "Congrats on the launch. Happy to share a quick AI workflow teardown.",
                "cold_email": {
                    "subject": "A quick AI workflow teardown for Acme Labs",
                    "body": "Thought this might be useful.",
                },
                "icp_fit_score": 0.42,
            }
        ],
        generated_at=datetime(2026, 3, 9, 23, 4, tzinfo=timezone.utc),
        timezone_name="Asia/Singapore",
    )

    assert "No strong content angle found today." in html
    assert "Best-Effort Prospects" in html
    assert "LinkedIn Opener" in html
    assert "Cold Email Draft" in html
    assert "2026-03-10 07:04 (Asia/Singapore)" in html
    assert "Watchlist Signals" not in html
    assert "No buying signals detected today." not in html


def test_run_pipeline_generates_best_effort_draft_for_tenant(monkeypatch):
    stored: dict = {}
    sent: dict = {}

    async def fake_run_and_return_items(*, sources, tenant_id=None):
        assert sources
        assert tenant_id == "tenant-1"
        return []

    async def fake_generate_daily_post(
        *,
        intelligence_summaries,
        intelligence_items=None,
        brand_context=None,
        tenant_id=None,
    ):
        assert intelligence_summaries
        assert intelligence_items is None
        assert brand_context
        assert tenant_id == "tenant-1"
        return DailyPostResult(
            headline="Best effort hook",
            linkedin_post="Best effort LinkedIn post",
            x_post="Best effort X post",
            instagram_caption="Best effort Instagram caption",
            google_business_profile_post="Best effort GBP post",
            tiktok_caption="Best effort TikTok caption",
            xiaohongshu_post="Best effort Xiaohongshu post",
            why_it_matters="Still useful",
            hashtags=["AI"],
            image_prompt="",
        )

    async def fake_run_and_classify(*, sources, max_signals, tenant_id=None):
        assert sources
        assert max_signals == 8
        assert tenant_id == "tenant-1"
        return []

    def fake_retrieve(self, query_text, language="en"):
        assert query_text
        return ([{"text": "Brand context", "doc_type": "service_description"}], False)

    def fake_send_daily_brief(**kwargs):
        sent.update(kwargs)

    def fake_add_doc(collection, data, doc_id=None, tenant_id=None):
        stored.update(
            {
                "collection": collection,
                "data": data,
                "doc_id": doc_id,
                "tenant_id": tenant_id,
            }
        )
        return doc_id or "draft-1"

    monkeypatch.setattr(
        pipeline_module,
        "_load_digest_config",
        lambda tenant_id=None: pipeline_module.DigestConfig(
            enabled=True,
            recipient_email="founder@intonationlabs.ai",
            timezone_name="Asia/Singapore",
            top_k_intelligence=2,
        ),
    )
    monkeypatch.setattr(
        pipeline_module,
        "get_tenant",
        lambda tenant_id: {
            "tenant_id": tenant_id,
            "owner_uid": "uid-1",
            "owner_email": "founder@intonationlabs.ai",
            "company_name": "Intonation Labs",
            "industry": "AI consulting",
            "description": "We help founders ship practical AI systems.",
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
            "daily_digest_email": "founder@intonationlabs.ai",
            "created_at": datetime(2026, 3, 13, tzinfo=timezone.utc),
        },
    )
    monkeypatch.setattr(
        pipeline_module, "_claim_daily_digest_send", lambda **kwargs: True
    )
    monkeypatch.setattr(
        pipeline_module, "_update_daily_digest_send", lambda **kwargs: None
    )
    monkeypatch.setattr(pipeline_module, "add_doc", fake_add_doc)
    monkeypatch.setattr(intelligence, "run_and_return_items", fake_run_and_return_items)
    monkeypatch.setattr(post_generate, "generate_daily_post", fake_generate_daily_post)
    monkeypatch.setattr(signals, "run_and_classify", fake_run_and_classify)
    monkeypatch.setattr(Retriever, "retrieve", fake_retrieve)
    monkeypatch.setattr(email_builder, "send_daily_brief", fake_send_daily_brief)

    result = asyncio.run(pipeline_module._run_pipeline(tenant_id="tenant-1"))

    assert result["tenant_id"] == "tenant-1"
    assert result["post_generated"] is True
    assert stored["collection"] == "drafts"
    assert stored["tenant_id"] == "tenant-1"
    assert stored["data"]["origin"] == "pipeline"
    assert stored["data"]["platforms_generated"] == [
        "linkedin",
        "x_twitter",
        "instagram",
        "google_business_profile",
        "tiktok",
        "xiaohongshu",
    ]
    assert stored["doc_id"] == f"{stored['data']['batch_date']}__pipeline_post"
    assert sent["post_status"] == "best_effort"
