from pydantic import BaseModel, ConfigDict


class WarmupExerciseSchema(BaseModel):
    id: str
    name: str
    description: str
    target_pitch_range: list[float]
    duration_sec: int
    tempo: int
    difficulty: int


class WarmupScoreSchema(BaseModel):
    exercise_id: str
    pitch_accuracy: float
    rhythm_accuracy: float
    overall_score: float


class WarmupSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exercises: list[WarmupExerciseSchema]
    scores: list[WarmupScoreSchema]
    started_at: str
    completed_at: str | None = None
