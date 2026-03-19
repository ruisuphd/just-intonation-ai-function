"""
Guitar-specific audio analysis: chord recognition, muted strings, strumming, barre heuristic.
"""

import asyncio
import numpy as np
import librosa

from app.services.audio.audio_utils import bytes_to_array, detect_onset_frames
from app.services.audio.chord_templates import match_chord

GUITAR_STRING_FUNDAMENTALS = [82.41, 110.0, 146.83, 196.0, 246.94, 329.63]


def _energy_at_freq(y: np.ndarray, sr: int, freq: float, tolerance: float = 0.1) -> float:
    n_fft = 4096
    hop = 512
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    lo = freq * (1 - tolerance)
    hi = freq * (1 + tolerance)
    idx = np.where((freqs >= lo) & (freqs <= hi))[0]
    if len(idx) == 0:
        return 0.0
    return float(np.mean(S[idx, :]))


def analyze_guitar_audio(audio_data: np.ndarray, sample_rate: int = 44100) -> dict:
    if len(audio_data) < 512:
        return {
            "chord_detected": None,
            "chord_confidence": 0.0,
            "muted_strings": [],
            "strumming_pattern": "",
            "timing_accuracy": 0.5,
            "barre_detected": False,
        }

    y = audio_data.astype(np.float32) if audio_data.dtype != np.float32 else audio_data
    harmonic = librosa.effects.harmonic(y, margin=8)

    chroma = librosa.feature.chroma_cqt(y=harmonic, sr=sample_rate, hop_length=512)
    chroma_mean = np.mean(chroma, axis=1)
    chord_detected, chord_confidence = match_chord(chroma_mean)
    if chord_confidence < 0.35:
        chord_detected = None
        chord_confidence = 0.0

    overall_energy = np.sqrt(np.mean(harmonic**2) + 1e-10)
    muted_strings: list[int] = []
    for i, freq in enumerate(GUITAR_STRING_FUNDAMENTALS):
        energy = _energy_at_freq(harmonic, sample_rate, freq)
        if overall_energy > 1e-8 and energy < overall_energy * 0.3:
            muted_strings.append(i)

    onset_frames = detect_onset_frames(harmonic, sample_rate)
    onset_times = librosa.frames_to_time(onset_frames, sr=sample_rate, hop_length=512)
    strumming_pattern = ""
    if len(onset_times) >= 2:
        intervals = np.diff(onset_times)
        median_interval = np.median(intervals)
        pattern = []
        for i, t in enumerate(onset_times[1:]):
            prev = onset_times[i]
            delta = t - prev
            if median_interval > 0:
                ratio = delta / median_interval
                if ratio < 0.6:
                    pattern.append("U")
                else:
                    pattern.append("D")
        strumming_pattern = " ".join(pattern[:6]) if pattern else "D D U D"

    tempo_est, _ = librosa.beat.beat_track(y=harmonic, sr=sample_rate, hop_length=512)
    tempo = float(tempo_est) if np.isfinite(tempo_est) else 120.0
    beat_interval = 60.0 / tempo if tempo > 0 else 0.5
    timing_accuracy = 0.7
    if len(onset_times) >= 2 and beat_interval > 0:
        deviations = []
        for t in onset_times:
            beat_pos = (t % beat_interval) / beat_interval
            dev = min(beat_pos, 1 - beat_pos) * 2
            deviations.append(dev)
        timing_accuracy = float(np.clip(1 - np.mean(deviations), 0.3, 0.95))

    barre_chords = {"F", "Fm", "F7", "Fmaj7", "Fm7", "F#", "F#m", "F#7", "F#maj7", "F#m7",
                    "Bb", "Bbm", "Bb7", "Bbmaj7", "Bbm7", "B", "Bm", "B7", "Bmaj7", "Bm7"}
    barre_detected = chord_detected in barre_chords if chord_detected else False

    return {
        "chord_detected": chord_detected,
        "chord_confidence": chord_confidence,
        "muted_strings": muted_strings,
        "strumming_pattern": strumming_pattern,
        "timing_accuracy": timing_accuracy,
        "barre_detected": barre_detected,
    }


async def analyse_guitar(audio_bytes: bytes, sample_rate: int = 44100) -> dict:
    def _run() -> dict:
        y = bytes_to_array(audio_bytes, sample_rate)
        return analyze_guitar_audio(y, sample_rate)

    return await asyncio.to_thread(_run)
