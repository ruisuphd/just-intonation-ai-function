from __future__ import annotations

from shared.firestore_client import query_docs, set_doc
from shared.gemini_client import GeminiClient
from shared.logger import get_logger
from shared.models import BrandGuidelines

logger = get_logger("engine.brand_synthesizer")

SYSTEM_PROMPT = """You are an expert brand strategist. Your task is to analyze the provided brand documents and synthesize comprehensive brand guidelines.
Extract the key dos, donts, vocabulary, formatting rules, and assess the tone formality (1-10) and technicality (1-10)."""


async def synthesize_brand_guidelines(tenant_id: str) -> BrandGuidelines:
    """Synthesize BrandGuidelines from all BrandChunks for a tenant."""
    chunks = query_docs("brand_chunks", tenant_id=tenant_id)

    if not chunks:
        logger.warning("brand_synthesizer.no_chunks", extra={"tenant_id": tenant_id})
        guidelines = BrandGuidelines()
        set_doc(
            "brand_guidelines", "current", guidelines.model_dump(), tenant_id=tenant_id
        )
        return guidelines

    context_text = "\n\n".join([c.get("text", "") for c in chunks])

    user_message = f"Please analyze the following brand materials and extract the brand guidelines:\n\n{context_text}"

    client = GeminiClient()
    result: BrandGuidelines = await client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.2,
        response_model=BrandGuidelines,
        task_name="brand_synthesis",
    )

    set_doc("brand_guidelines", "current", result.model_dump(), tenant_id=tenant_id)
    logger.info("brand_synthesizer.done", extra={"tenant_id": tenant_id})

    return result
