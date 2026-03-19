"""
Precomputed chord chroma templates for chord recognition.
12 roots × 4 qualities (major, minor, 7, maj7) = 48 templates.
"""

import numpy as np

ROOT_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Pitch classes: 0=C, 1=C#, 2=D, 3=D#, 4=E, 5=F, 6=F#, 7=G, 8=G#, 9=A, 10=A#, 11=B
# Intervals from root: major=0,4,7 | minor=0,3,7 | 7=0,4,7,10 | maj7=0,4,7,11


def _make_chroma(intervals: list[int]) -> np.ndarray:
    vec = np.zeros(12, dtype=np.float32)
    for i in intervals:
        vec[i % 12] = 1.0
    norm = np.linalg.norm(vec)
    return (vec / norm) if norm > 0 else vec


TEMPLATES_MAJOR = _make_chroma([0, 4, 7])
TEMPLATES_MINOR = _make_chroma([0, 3, 7])
TEMPLATES_7 = _make_chroma([0, 4, 7, 10])
TEMPLATES_MAJ7 = _make_chroma([0, 4, 7, 11])

QUALITY_TEMPLATES = {
    "major": TEMPLATES_MAJOR,
    "minor": TEMPLATES_MINOR,
    "7": TEMPLATES_7,
    "maj7": TEMPLATES_MAJ7,
}

_CHORD_CACHE: list[tuple[str, np.ndarray]] = []


def _build_chord_list() -> list[tuple[str, np.ndarray]]:
    if _CHORD_CACHE:
        return _CHORD_CACHE
    for root_idx, root_name in enumerate(ROOT_NAMES):
        for quality, template in QUALITY_TEMPLATES.items():
            shifted = np.roll(template, root_idx)
            label = f"{root_name}{quality}" if quality != "major" else root_name
            _CHORD_CACHE.append((label, shifted))
    return _CHORD_CACHE


def match_chord(chroma_vector: np.ndarray) -> tuple[str, float]:
    """Match a 12-dim chroma vector to the closest chord template.
    Returns (chord_label, confidence 0-1).
    """
    if chroma_vector is None or len(chroma_vector) < 12:
        return "", 0.0
    vec = np.array(chroma_vector[:12], dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm <= 0:
        return "", 0.0
    vec = vec / norm

    best_label = ""
    best_sim = -1.0

    for label, template in _build_chord_list():
        sim = float(np.dot(vec, template))
        if sim > best_sim:
            best_sim = sim
            best_label = label

    confidence = float(np.clip(best_sim, 0, 1))
    return best_label, confidence


def get_chord_templates() -> list[tuple[str, np.ndarray]]:
    return _build_chord_list()
