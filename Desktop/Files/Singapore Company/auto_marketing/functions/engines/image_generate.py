"""Vertex AI image generation with tiered model strategy."""

from __future__ import annotations

import os

from shared.gcp_auth import get_google_credentials
from shared.logger import get_logger

logger = get_logger("engine.image_generate")

_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
_REGION = os.getenv("GCP_REGION", "us-central1")

# Tiered model selection:
#   Starter/Growth: Imagen 4 ($0.04/image)
#   Pro + bilingual: Gemini 3 Pro Image ($0.134/image, supports multilingual prompts)
_MODEL_STARTER = "imagen-4.0-generate-001"
_MODEL_PRO = "gemini-3-pro-image-preview"

_IMAGE_PREFIX = (
    "Create a realistic editorial-style business visual. "
    "Avoid glossy CGI aesthetics, fake-looking faces, staged stock-photo people, and any text in the image. "
    "Prefer clean data-storytelling visuals, abstract professional compositions, modern office details without obvious faces, "
    "or understated strategic concept imagery."
)


def _select_model(tier: str = "starter", language: str = "en") -> str:
    if tier == "pro" and language in ("zh", "bilingual"):
        return _MODEL_PRO
    return _MODEL_STARTER


async def generate(
    prompt: str,
    tier: str = "starter",
    language: str = "en",
) -> bytes:
    """Generate an image from a text prompt. Returns raw PNG bytes."""
    import vertexai
    from vertexai.preview.vision_models import ImageGenerationModel

    creds, project, _ = get_google_credentials(require_quota_project=True)
    vertexai.init(project=project or _PROJECT_ID, location=_REGION, credentials=creds)
    model_name = _select_model(tier, language)
    model = ImageGenerationModel.from_pretrained(model_name)
    final_prompt = f"{_IMAGE_PREFIX}\n\n{prompt.strip()}"

    logger.info(
        "image_generate.start",
        extra={"prompt_chars": len(prompt), "model": model_name, "tier": tier},
    )
    images = model.generate_images(
        prompt=final_prompt,
        number_of_images=1,
        aspect_ratio="1:1",
        safety_filter_level="block_some",
        person_generation="dont_allow",
    )

    if not images:
        raise RuntimeError("Image generation returned no images")

    image_bytes: bytes = images[0]._image_bytes
    logger.info(
        "image_generate.done",
        extra={"bytes": len(image_bytes), "model": model_name},
    )
    return image_bytes
