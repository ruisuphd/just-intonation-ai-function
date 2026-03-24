import io
import struct

import numpy as np
from pydub import AudioSegment


def pcm16_to_float32(pcm_bytes: bytes) -> np.ndarray:
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


def webm_to_wav_bytes(audio_bytes: bytes, sample_rate: int = 44100) -> bytes:
    seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
    seg = seg.set_frame_rate(sample_rate).set_channels(1)
    samples = np.array(seg.get_array_of_samples(), dtype=np.float32) / 32768
    return float32_to_wav(samples, sample_rate)


def float32_to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    pcm = (samples * 32767).astype(np.int16)
    num_samples = len(pcm)
    byte_rate = sample_rate * 2
    block_align = 2
    data_size = num_samples * block_align

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        byte_rate,
        block_align,
        16,
        b"data",
        data_size,
    )
    return header + pcm.tobytes()


def chunk_audio(
    audio_bytes: bytes,
    chunk_size_ms: int,
    sample_rate: int,
) -> list[bytes]:
    samples_per_chunk = int(sample_rate * chunk_size_ms / 1000) * 2
    chunks: list[bytes] = []
    offset = 0
    while offset < len(audio_bytes):
        chunk = audio_bytes[offset : offset + samples_per_chunk]
        if chunk:
            chunks.append(chunk)
        offset += samples_per_chunk
    return chunks
