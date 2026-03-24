from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.i18n.locales import normalize_locale


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    preferred_locale: str | None = None
    voice_profile: dict | None = Field(default=None, validation_alias="voice_profile_json")
    skill_profile: dict | None = Field(default=None, validation_alias="skill_profile_json")
    badges: list[str] = Field(default_factory=list)


class UserProfileUpdate(BaseModel):
    skill_profile: dict | None = None
    preferred_locale: str | None = None

    @field_validator("preferred_locale", mode="before")
    @classmethod
    def validate_preferred_locale(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise TypeError("preferred_locale must be a string")
        n = normalize_locale(v)
        if n is None:
            raise ValueError("unsupported preferred_locale")
        return n
