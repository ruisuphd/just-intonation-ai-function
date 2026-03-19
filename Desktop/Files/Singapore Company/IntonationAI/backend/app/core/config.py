from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Firebase / GCP
    FIREBASE_PROJECT_ID: str | None = None
    GOOGLE_CLOUD_PROJECT: str | None = None
    GCP_REGION: str = "us-central1"
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None

    # Vertex AI
    VERTEX_AI_MODEL: str = "claude-sonnet-4-6-20250514"
    VERTEX_AI_LOCATION: str = "us-east5"
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Cloud Storage
    GCS_BUCKET: str | None = None

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/intonation_ai"

    # Stripe
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_ID_MONTHLY: str | None = None
    STRIPE_PRICE_ID_YEARLY: str | None = None
    STRIPE_PRICE_ID_ESSENTIAL_MONTHLY: str | None = None
    STRIPE_PRICE_ID_ESSENTIAL_YEARLY: str | None = None
    STRIPE_PRICE_ID_PRO_MONTHLY: str | None = None
    STRIPE_PRICE_ID_PRO_YEARLY: str | None = None

    # App
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"

    @property
    def gcp_project(self) -> str | None:
        return self.GOOGLE_CLOUD_PROJECT or self.FIREBASE_PROJECT_ID


settings = Settings()
