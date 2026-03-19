from pydantic import BaseModel


class AudioAnalysisResponse(BaseModel):
    pitch_hz: float | None = None
    note_name: str | None = None
    cents_deviation: float = 0.0
    rms_db: float = 0.0
    onset_detected: bool = False
    tempo: float | None = None
