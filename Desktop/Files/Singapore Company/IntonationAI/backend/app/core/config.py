from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Firebase / GCP
    FIREBASE_PROJECT_ID: str | None = None
    # When true, abuse-prone HTTP routes and coach WebSocket require a valid App Check token.
    FIREBASE_APP_CHECK_ENFORCE: bool = False
    GOOGLE_CLOUD_PROJECT: str | None = None
    GCP_REGION: str = "us-central1"
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None

    # Vertex AI
    VERTEX_AI_MODEL: str = "claude-sonnet-4-6-20250514"
    VERTEX_AI_LOCATION: str = "us-central1"
    GEMINI_MODEL: str = "gemini-3.1-flash-lite-preview"

    # Cloud Storage
    GCS_BUCKET: str | None = None

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/intonation_ai"

    # Stripe
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_ID_MONTHLY: str | None = None
    STRIPE_PRICE_ID_YEARLY: str | None = None
    STRIPE_PRICE_ID_PRO_MONTHLY: str | None = None
    STRIPE_PRICE_ID_PRO_YEARLY: str | None = None
    STRIPE_TRIAL_DAYS: int | None = None

    # App
    ENVIRONMENT: str = "development"
    DATABASE_AUTO_CREATE: bool = True
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"

    # Observability
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    ENABLE_CLOUD_TRACE: bool = False
    LOG_JSON: bool = False
    APP_RELEASE: str | None = None

    # Coach / experiments (env-driven feature flag)
    COACH_PROMPT_VERSION: str = "1"
    # Max chat lines (user+coach) passed to the LLM; full history stays in Firestore.
    COACH_LLM_HISTORY_MESSAGES: int = 30

    # Resilience
    COACH_LLM_TIMEOUT_SEC: float = 120.0
    GCS_OPERATION_TIMEOUT_SEC: float = 60.0
    STRIPE_HTTP_TIMEOUT_SEC: float = 30.0
    GEMINI_CIRCUIT_FAILURE_THRESHOLD: int = 5
    GEMINI_CIRCUIT_OPEN_SEC: float = 60.0

    # Readiness probes: bounded so Cloud Run / load balancers do not hang
    READINESS_DB_TIMEOUT_SEC: float = 5.0
    READINESS_GCS_TIMEOUT_SEC: float = 12.0

    @property
    def gcp_project(self) -> str | None:
        return self.GOOGLE_CLOUD_PROJECT or self.FIREBASE_PROJECT_ID

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


settings = Settings()
