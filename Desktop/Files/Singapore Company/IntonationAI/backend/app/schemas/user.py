from pydantic import BaseModel, ConfigDict, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    voice_profile: dict | None = Field(default=None, validation_alias="voice_profile_json")
    skill_profile: dict | None = Field(default=None, validation_alias="skill_profile_json")


class UserProfileUpdate(BaseModel):
    skill_profile: dict | None = None
