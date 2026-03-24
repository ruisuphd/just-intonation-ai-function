from pydantic import BaseModel


class AudioAnalysisResponse(BaseModel):
    pitch_hz: float | None = None
    note_name: str | None = None
    cents_deviation: float = 0.0
    rms_db: float = 0.0
    onset_detected: bool = False
    tempo: float | None = None
    breath_support_score: float | None = None
    vibrato_present: bool | None = None
    pitch_stability: float | None = None
    rhythm_score: float | None = None
    schema_version: int | None = None
    analysis_tier: str | None = None
