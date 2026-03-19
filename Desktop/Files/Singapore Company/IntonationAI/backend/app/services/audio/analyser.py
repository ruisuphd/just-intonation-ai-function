import asyncio
import logging

import librosa
import numpy as np

from app.services.audio.audio_utils import (
    bytes_to_array,
    calculate_rms_db,
    detect_onset_frames,
    detect_pitch_yin,
    frequency_to_note,
)

logger = logging.getLogger(__name__)


class AudioAnalyser:
    def _breath_support(self, y: np.ndarray, rms_db: float) -> float:
        frame_len = 2048
        hop = 512
        n_frames = max(1, (len(y) - frame_len) // hop + 1)
        energies = []
        for i in range(n_frames):
            start = i * hop
            end = min(start + frame_len, len(y))
            if end <= start:
                break
            frame = y[start:end]
            e = np.sqrt(np.mean(frame**2) + 1e-10)
            energies.append(20 * np.log10(e))
        if not energies:
            return 0.5
        threshold_db = max(-40, np.median(energies) - 6)
        above = sum(1 for e in energies if e >= threshold_db)
        ratio = above / len(energies)
        return float(np.clip(ratio, 0, 1))

    def _vibrato_and_stability(
        self, f0: np.ndarray, sample_rate: int
    ) -> tuple[bool, float]:
        voiced = f0[np.isfinite(f0)]
        if len(voiced) < 32:
            return False, 0.5
        freqs_hz = voiced.astype(np.float64)
        freqs_hz = np.maximum(freqs_hz, 1)
        cents_delta = 1200 * np.log2(freqs_hz[1:] / freqs_hz[:-1])
        cents_delta = np.nan_to_num(cents_delta, 0)
        std_cents = float(np.std(cents_delta))
        mean_abs = float(np.mean(np.abs(cents_delta)))
        vibrato = 3 <= std_cents <= 100 and mean_abs > 2
        stability = 1 - min(1, std_cents / 60)
        return bool(vibrato), float(np.clip(stability, 0, 1))

    async def analyse(self, audio_bytes: bytes, sample_rate: int = 44100) -> dict:
        def _run() -> dict:
            y = bytes_to_array(audio_bytes, sample_rate)
            if len(y) < 512:
                rms_early = calculate_rms_db(y)
                return {
                    "pitch_hz": None,
                    "note_name": None,
                    "cents_deviation": 0.0,
                    "rms_db": rms_early,
                    "onset_detected": False,
                    "tempo": None,
                    "breath_support_score": 0.5,
                    "vibrato_present": False,
                    "pitch_stability": 0.5,
                    "rhythm_score": 0.5,
                }

            pitch_hz, f0 = detect_pitch_yin(y, sample_rate, fmin=80, fmax=400)

            note_name, cents_deviation = "?", 0.0
            if pitch_hz:
                note_name, cents_deviation = frequency_to_note(pitch_hz)

            rms_db = calculate_rms_db(y)

            onset_frames = detect_onset_frames(y, sample_rate)
            onset_detected = len(onset_frames) > 0

            tempo = None
            if onset_detected:
                tempo_est, _ = librosa.beat.beat_track(y=y, sr=sample_rate)
                tempo = float(tempo_est) if np.isfinite(tempo_est) else None

            breath_support_score = self._breath_support(y, rms_db)
            vibrato_present, pitch_stability = self._vibrato_and_stability(
                f0, sample_rate
            )

            rhythm_score = 0.6
            if onset_detected:
                rhythm_score += 0.2
            if tempo is not None and 60 <= tempo <= 180:
                rhythm_score += 0.2
            rhythm_score = float(np.clip(rhythm_score, 0, 1))

            return {
                "pitch_hz": pitch_hz,
                "note_name": note_name if pitch_hz else None,
                "cents_deviation": cents_deviation,
                "rms_db": rms_db,
                "onset_detected": onset_detected,
                "tempo": tempo,
                "breath_support_score": breath_support_score,
                "vibrato_present": vibrato_present,
                "pitch_stability": pitch_stability,
                "rhythm_score": rhythm_score,
            }

        try:
            return await asyncio.to_thread(_run)
        except Exception as e:
            logger.exception("Audio analysis failed: %s", e)
            raise


audio_analyser = AudioAnalyser()
