"""
Shared audio analysis utilities for vocal, piano, and guitar analysis.
"""

import io

import librosa
import numpy as np

from app.services.audio.processor import pcm16_to_float32, webm_to_wav_bytes


def bytes_to_array(audio_bytes: bytes, sample_rate: int = 44100) -> np.ndarray:
    if audio_bytes[:4] == b"RIFF" or audio_bytes[:4] == b"fLaC":
        y, _ = librosa.load(io.BytesIO(audio_bytes), sr=sample_rate, mono=True)
        return y.astype(np.float32)
    if audio_bytes[:4] == b"\x1aE\xdf\xa3":
        wav_bytes = webm_to_wav_bytes(audio_bytes, sample_rate)
        y, _ = librosa.load(io.BytesIO(wav_bytes), sr=sample_rate, mono=True)
        return y.astype(np.float32)
    try:
        y, _ = librosa.load(io.BytesIO(audio_bytes), sr=sample_rate, mono=True)
        return y.astype(np.float32)
    except Exception:
        samples = pcm16_to_float32(audio_bytes)
        if len(samples) % 2:
            samples = samples[:-1]
        return samples.astype(np.float32)


def frequency_to_note(hz: float) -> tuple[str, float]:
    if hz <= 0:
        return "?", 0.0
    A4 = 440.0
    C0 = A4 * (2 ** (-4.75))
    semitones = 12 * np.log2(hz / C0)
    midi = round(semitones)
    note_num = midi % 12
    octave = midi // 12
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    note_name = f"{names[note_num]}{octave}"
    freq_note = C0 * (2 ** (midi / 12))
    cents = 1200 * np.log2(hz / freq_note) if freq_note > 0 else 0.0
    return note_name, float(cents)


def calculate_rms_db(y: np.ndarray) -> float:
    rms = np.sqrt(np.mean(y**2) + 1e-10)
    return float(20 * np.log10(rms))


def detect_onset_frames(y: np.ndarray, sr: int) -> np.ndarray:
    return librosa.onset.onset_detect(y=y, sr=sr)


def detect_pitch_yin(
    y: np.ndarray,
    sr: int,
    fmin: float = 80.0,
    fmax: float = 4000.0,
) -> tuple[float | None, np.ndarray]:
    f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=fmin, fmax=fmax, sr=sr)
    voiced = f0[np.isfinite(f0)]
    pitch_hz = float(np.median(voiced)) if len(voiced) > 0 else None
    return pitch_hz, f0
