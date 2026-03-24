from pydantic import BaseModel, ConfigDict, field_validator


class CoachMessageRequest(BaseModel):
    content: str


class CoachMessageResponse(BaseModel):
    reply: str
    audio_url: str | None = None
    analysis: dict | None = None


class CoachSessionCreate(BaseModel):
    coach_type: str
    timezone: str | None = None
    practice_mode: bool | None = None
    locale: str | None = None

    @field_validator("coach_type")
    @classmethod
    def validate_coach_type(cls, v: str) -> str:
        if v not in ("vocal", "piano", "guitar"):
            raise ValueError("coach_type must be vocal, piano, or guitar")
        return v


class CoachSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    coach_type: str
    locale: str = "en"
    started_at: str
    ended_at: str | None = None
    prompt_version: str = "1"
