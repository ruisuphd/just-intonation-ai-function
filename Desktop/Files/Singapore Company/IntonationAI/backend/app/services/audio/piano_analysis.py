"""
Piano-specific audio analysis: note detection, chord recognition, timing, velocity.
"""

import asyncio
import numpy as np
import librosa

from app.services.audio.audio_utils import (
    bytes_to_array,
    calculate_rms_db,
    detect_onset_frames,
    detect_pitch_yin,
    frequency_to_note,
)
from app.services.audio.chord_templates import match_chord


def analyze_piano_audio(audio_data: np.ndarray, sample_rate: int = 44100) -> dict:
    if len(audio_data) < 512:
        return {
            "note_name": None,
            "chord_detected": None,
            "chord_confidence": 0.0,
            "timing_offset_ms": 0.0,
            "velocity_db": -60.0,
            "accuracy_score": 0.5,
        }

    y = audio_data.astype(np.float32) if audio_data.dtype != np.float32 else audio_data

    note_name = None
    pitch_hz, f0 = detect_pitch_yin(y, sample_rate, fmin=27.5, fmax=4000)
    if pitch_hz:
        note_name, _ = frequency_to_note(pitch_hz)

    chroma = librosa.feature.chroma_cqt(y=y, sr=sample_rate, hop_length=512)
    chroma_mean = np.mean(chroma, axis=1)
    chord_detected, chord_confidence = match_chord(chroma_mean)
    if chord_confidence < 0.4:
        chord_detected = None
        chord_confidence = 0.0

    onset_frames = detect_onset_frames(y, sample_rate)
    onset_detected = len(onset_frames) > 0

    timing_offset_ms = 0.0
    tempo = None
    if onset_detected:
        tempo_est, _ = librosa.beat.beat_track(y=y, sr=sample_rate, hop_length=512)
        tempo = float(tempo_est) if np.isfinite(tempo_est) else 120.0
        hop_ms = 512 / sample_rate * 1000
        first_onset_ms = float(onset_frames[0]) * hop_ms
        if tempo and tempo > 0:
            beat_interval_ms = 60000 / tempo
            timing_offset_ms = first_onset_ms % beat_interval_ms
            if timing_offset_ms > beat_interval_ms / 2:
                timing_offset_ms -= beat_interval_ms

    velocity_db = calculate_rms_db(y)
    if onset_detected and len(onset_frames) > 0:
        onset_idx = int(onset_frames[0] * 512)
        onset_window = y[max(0, onset_idx) : min(len(y), onset_idx + 2048)]
        if len(onset_window) > 0:
            velocity_db = calculate_rms_db(onset_window)

    accuracy_score = 0.5
    if chord_confidence > 0:
        accuracy_score = 0.5 + chord_confidence * 0.4
    if note_name and note_name != "?":
        accuracy_score = max(accuracy_score, 0.6)
    if -35 < velocity_db < -5:
        accuracy_score = min(1.0, accuracy_score + 0.05)
    accuracy_score = float(np.clip(accuracy_score, 0, 1))

    return {
        "note_name": note_name,
        "chord_detected": chord_detected,
        "chord_confidence": chord_confidence,
        "timing_offset_ms": timing_offset_ms,
        "velocity_db": velocity_db,
        "accuracy_score": accuracy_score,
    }


async def analyse_piano(audio_bytes: bytes, sample_rate: int = 44100) -> dict:
    def _run() -> dict:
        y = bytes_to_array(audio_bytes, sample_rate)
        return analyze_piano_audio(y, sample_rate)

    return await asyncio.to_thread(_run)
