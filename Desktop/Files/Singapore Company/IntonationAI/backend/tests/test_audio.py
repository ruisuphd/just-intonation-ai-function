import numpy as np
import pytest

from app.services.audio.analyser import AudioAnalyser
from app.services.audio.chord_templates import match_chord
from app.services.audio.guitar_analysis import analyze_guitar_audio
from app.services.audio.piano_analysis import analyze_piano_audio
from app.services.audio.processor import float32_to_wav, pcm16_to_float32


class TestAudioProcessor:
    def test_pcm16_to_float32_returns_float_array(self):
        pcm = np.array([0, 16383, -16384], dtype=np.int16).tobytes()
        result = pcm16_to_float32(pcm)
        assert result.dtype == np.float32
        assert len(result) == 3

    def test_float32_to_wav_produces_valid_header(self):
        samples = np.zeros(44100, dtype=np.float32)
        wav_bytes = float32_to_wav(samples, 44100)
        assert wav_bytes[:4] == b"RIFF"
        assert wav_bytes[8:12] == b"WAVE"

    def test_roundtrip_pcm_conversion(self):
        original = np.array([0, 10000, -10000, 32767, -32768], dtype=np.int16)
        pcm = original.tobytes()
        floats = pcm16_to_float32(pcm)
        assert floats.shape == (5,)
        assert -1.0 <= floats.min() <= floats.max() <= 1.0


class TestAudioAnalyser:
    def test_frequency_to_note_a4(self):
        from app.services.audio.audio_utils import frequency_to_note

        name, cents = frequency_to_note(440.0)
        assert name == "A4"
        assert abs(cents) < 1.0

    def test_frequency_to_note_c4(self):
        from app.services.audio.audio_utils import frequency_to_note

        name, cents = frequency_to_note(261.63)
        assert name == "C4"
        assert abs(cents) < 5.0

    @pytest.mark.asyncio
    async def test_analyse_silence(self):
        analyser = AudioAnalyser()
        silence = np.zeros(44100, dtype=np.float32).tobytes()
        result = await analyser.analyse(silence)
        assert "rms_db" in result
        assert result["rms_db"] < -40


class TestPianoAnalysis:
    def test_analyze_piano_short_audio(self):
        y = np.random.randn(256).astype(np.float32) * 0.01
        r = analyze_piano_audio(y, 44100)
        assert "note_name" in r
        assert "chord_detected" in r
        assert "accuracy_score" in r

    def test_analyze_piano_noise(self):
        y = np.random.randn(44100).astype(np.float32) * 0.1
        r = analyze_piano_audio(y, 44100)
        assert 0 <= r["accuracy_score"] <= 1


class TestGuitarAnalysis:
    def test_analyze_guitar_short_audio(self):
        y = np.random.randn(256).astype(np.float32) * 0.01
        r = analyze_guitar_audio(y, 44100)
        assert "chord_detected" in r
        assert "muted_strings" in r
        assert "timing_accuracy" in r

    def test_analyze_guitar_noise(self):
        y = np.random.randn(44100).astype(np.float32) * 0.1
        r = analyze_guitar_audio(y, 44100)
        assert isinstance(r["muted_strings"], list)


class TestChordTemplates:
    def test_match_chord_returns_tuple(self):
        chroma = np.ones(12, dtype=np.float32) / np.sqrt(12)
        label, conf = match_chord(chroma)
        assert isinstance(label, str)
        assert 0 <= conf <= 1
