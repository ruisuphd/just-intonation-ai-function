import time
from datetime import datetime, timezone
from shared.logger import get_logger
from shared.firestore_client import get_tenant, update_tenant, add_doc
from shared.models import OnboardingState, BrandDocument

logger = get_logger("onboarding_flow")


def process_new_tenant(tenant_id: str) -> None:
    """
    Mock process to handle new tenant onboarding.
    Simulates scraping the company URL, populating initial BrandDocuments,
    and auto-discovering competitors.
    """
    logger.info(f"Starting onboarding flow for tenant: {tenant_id}")

    tenant_data = get_tenant(tenant_id)
    if not tenant_data:
        logger.error(f"Tenant {tenant_id} not found.")
        return

    # Initialize onboarding state if not present
    onboarding_state = (
        tenant_data.get("onboarding_state") or OnboardingState().model_dump()
    )

    # 1. Mock scraping company URL
    logger.info(f"Mocking website scrape for tenant: {tenant_id}")
    time.sleep(1)  # Simulate network delay
    onboarding_state["website_scraped"] = True

    # 2. Mock auto-discovering competitors
    logger.info(f"Mocking competitor discovery for tenant: {tenant_id}")
    time.sleep(1)
    new_competitors = ["Acme Corp", "Global Tech", "Innovate Inc"]
    existing_competitors = tenant_data.get("competitor_names", [])
    updated_competitors = list(set(existing_competitors + new_competitors))
    onboarding_state["competitors_identified"] = True

    # 3. Mock populating initial BrandDocuments
    logger.info(f"Mocking initial BrandDocument generation for tenant: {tenant_id}")
    time.sleep(1)

    mock_doc = BrandDocument(
        filename="website_scrape_summary.md",
        storage_path=f"tenants/{tenant_id}/brand_docs/website_scrape_summary.md",
        file_type="md",
        file_size_bytes=1024,
        doc_type="brand_voice",
        status="indexed",
        chunk_count=5,
        uploaded_by="system",
        processed_at=datetime.now(timezone.utc),
    )

    add_doc(
        collection="brand_documents", data=mock_doc.model_dump(), tenant_id=tenant_id
    )

    onboarding_state["brand_voice_analyzed"] = True

    # Update tenant profile
    logger.info(f"Updating tenant {tenant_id} with completed onboarding state.")
    update_tenant(
        tenant_id,
        {
            "onboarding_state": onboarding_state,
            "competitor_names": updated_competitors,
            "onboarding_completed": True,
        },
    )

    logger.info(f"Onboarding flow completed for tenant: {tenant_id}")
