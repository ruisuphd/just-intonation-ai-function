#!/usr/bin/env python3
"""Evaluate just intonation tuning quality using psychoacoustic roughness models.

This script computes Sethares/Vassilakis sensory dissonance (roughness) for
standard chord types under three tuning schemes: 12-TET, 5-limit JI, and
7-limit JI.  It is self-contained and depends only on numpy.

References
----------
.. [1] Sethares, W. A. (1993). "Local consonance and the relationship between
       timbre and scale." *Journal of the Acoustical Society of America*,
       94(3), 1218--1228.
.. [2] Vassilakis, P. N. (2001). "Perceptual and Physical Properties of
       Amplitude Fluctuation and their Musical Significance." PhD thesis,
       University of California, Los Angeles.
.. [3] Ramani, R. (2026). "A Comprehensive Corpus of Biomechanically
       Constrained Piano Chords." arXiv:2603.29710.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Sethares (1993) roughness model parameters
B1 = 3.5
B2 = 5.75

# 5-limit JI ratio tables (copied from two_stage_server.py)
JI_RATIOS_MAJOR: Dict[int, float] = {
    0: 1.0,
    1: 16 / 15,
    2: 9 / 8,
    3: 6 / 5,
    4: 5 / 4,
    5: 4 / 3,
    6: 45 / 32,
    7: 3 / 2,
    8: 8 / 5,
    9: 5 / 3,
    10: 9 / 5,
    11: 15 / 8,
}

JI_RATIOS_MINOR: Dict[int, float] = {
    0: 1.0,
    1: 16 / 15,
    2: 9 / 8,
    3: 6 / 5,
    4: 5 / 4,
    5: 4 / 3,
    6: 45 / 32,
    7: 3 / 2,
    8: 8 / 5,
    9: 5 / 3,
    10: 16 / 9,
    11: 15 / 8,
}

# 7-limit variant: minor seventh uses the septimal ratio 7/4
JI_RATIOS_7LIMIT: Dict[int, float] = {
    **JI_RATIOS_MAJOR,
    10: 7 / 4,  # septimal minor seventh
}

NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

NUM_PARTIALS = 8  # number of harmonic partials per piano note


# ---------------------------------------------------------------------------
# Piano partial model
# ---------------------------------------------------------------------------

def midi_to_freq(midi_pitch: int) -> float:
    """Convert a MIDI pitch number to frequency in Hz (A4 = 69 = 440 Hz)."""
    return 440.0 * (2.0 ** ((midi_pitch - 69) / 12.0))


def piano_partials(fundamental: float, n_partials: int = NUM_PARTIALS) -> Tuple[np.ndarray, np.ndarray]:
    """Return arrays of (frequencies, amplitudes) for a piano-like tone.

    Piano strings produce nearly-harmonic partials at integer multiples of the
    fundamental.  Amplitudes decay approximately as 1/n for the nth partial.

    Parameters
    ----------
    fundamental : float
        Fundamental frequency in Hz.
    n_partials : int
        Number of harmonic partials to include.

    Returns
    -------
    freqs : ndarray, shape (n_partials,)
    amps : ndarray, shape (n_partials,)
    """
    ns = np.arange(1, n_partials + 1, dtype=float)
    freqs = fundamental * ns
    amps = 1.0 / ns
    return freqs, amps


# ---------------------------------------------------------------------------
# Sethares (1993) roughness model
# ---------------------------------------------------------------------------

def sethares_roughness(freqs: np.ndarray, amps: np.ndarray) -> float:
    """Compute sensory roughness for a set of partials.

    Implements the pairwise roughness model from Sethares (1993) [1]:

        R = sum_{i<j} a_i * a_j * [exp(-b1 * s * |f_i - f_j|)
                                  - exp(-b2 * s * |f_i - f_j|)]

    where  s = 0.24 / (0.0207 * min(f_i, f_j) + 18.96).

    Parameters
    ----------
    freqs : ndarray
        Frequencies of all partials (Hz).
    amps : ndarray
        Amplitudes of all partials (linear scale).

    Returns
    -------
    float
        Total roughness (non-negative).
    """
    n = len(freqs)
    roughness = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            f_min = min(freqs[i], freqs[j])
            delta_f = abs(freqs[i] - freqs[j])
            s = 0.24 / (0.0207 * f_min + 18.96)
            roughness += (
                amps[i] * amps[j]
                * (np.exp(-B1 * s * delta_f) - np.exp(-B2 * s * delta_f))
            )
    return float(roughness)


# ---------------------------------------------------------------------------
# Tuning schemes
# ---------------------------------------------------------------------------

def chord_freqs_12tet(root_midi: int, intervals_semitones: List[int]) -> List[float]:
    """Return chord frequencies in 12-TET.

    Parameters
    ----------
    root_midi : int
        MIDI pitch of the chord root.
    intervals_semitones : list of int
        Semitone intervals above the root (0 = root).
    """
    return [midi_to_freq(root_midi + s) for s in intervals_semitones]


def chord_freqs_ji(
    root_midi: int,
    intervals_semitones: List[int],
    ratio_table: Dict[int, float],
) -> List[float]:
    """Return chord frequencies in a just-intonation tuning.

    Each note is tuned as  f_root * ratio_table[interval mod 12], transposed
    by the appropriate number of octaves.

    Parameters
    ----------
    root_midi : int
        MIDI pitch of the chord root.
    intervals_semitones : list of int
        Semitone intervals above the root (0 = root).
    ratio_table : dict
        Mapping from semitone class (0..11) to JI frequency ratio.
    """
    f_root = midi_to_freq(root_midi)
    freqs = []
    for s in intervals_semitones:
        octaves = s // 12
        semitone_class = s % 12
        ratio = ratio_table[semitone_class]
        freqs.append(f_root * ratio * (2.0 ** octaves))
    return freqs


# ---------------------------------------------------------------------------
# Chord definitions (semitone intervals above root)
# ---------------------------------------------------------------------------

CHORD_TYPES = {
    "major_triad": [0, 4, 7],
    "minor_triad": [0, 3, 7],
    "dominant_7th": [0, 4, 7, 10],
    "diminished_7th": [0, 3, 6, 9],
}


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def evaluate_chord(
    root_midi: int,
    intervals: List[int],
    tuning: str,
) -> float:
    """Compute roughness for a single chord under a given tuning.

    Parameters
    ----------
    root_midi : int
        MIDI pitch of the chord root.
    intervals : list of int
        Semitone intervals above the root.
    tuning : str
        One of "12tet", "ji5", "ji7".

    Returns
    -------
    float
        Total Sethares roughness.
    """
    if tuning == "12tet":
        note_freqs = chord_freqs_12tet(root_midi, intervals)
    elif tuning == "ji5":
        # Choose major or minor table based on the chord's third
        has_minor_third = 3 in intervals
        table = JI_RATIOS_MINOR if has_minor_third else JI_RATIOS_MAJOR
        note_freqs = chord_freqs_ji(root_midi, intervals, table)
    elif tuning == "ji7":
        has_minor_third = 3 in intervals
        table = JI_RATIOS_7LIMIT if not has_minor_third else {**JI_RATIOS_MINOR, 10: 7 / 4}
        note_freqs = chord_freqs_ji(root_midi, intervals, table)
    else:
        raise ValueError(f"Unknown tuning: {tuning}")

    # Build combined partial spectrum for all notes
    all_freqs = []
    all_amps = []
    for f0 in note_freqs:
        f, a = piano_partials(f0)
        all_freqs.append(f)
        all_amps.append(a)

    all_freqs = np.concatenate(all_freqs)
    all_amps = np.concatenate(all_amps)

    return sethares_roughness(all_freqs, all_amps)


def run_evaluation() -> dict:
    """Run the full roughness evaluation across keys, chords, and tunings.

    Returns
    -------
    dict
        Nested results: results[tuning][chord_type][key_name] = roughness.
        Also includes summary statistics.
    """
    tunings = ["12tet", "ji5", "ji7"]
    # C4 = MIDI 60
    root_midis = list(range(60, 72))  # C4 through B4

    results: dict = {"per_chord": {}, "summary": {}}

    for tuning in tunings:
        results["per_chord"][tuning] = {}
        for chord_name, intervals in CHORD_TYPES.items():
            results["per_chord"][tuning][chord_name] = {}
            for root_midi in root_midis:
                key_name = NOTE_NAMES[root_midi % 12] + "4"
                r = evaluate_chord(root_midi, intervals, tuning)
                results["per_chord"][tuning][chord_name][key_name] = round(r, 6)

    # Summary: mean roughness per chord type per tuning
    for tuning in tunings:
        results["summary"][tuning] = {}
        for chord_name in CHORD_TYPES:
            values = list(results["per_chord"][tuning][chord_name].values())
            results["summary"][tuning][chord_name] = {
                "mean": round(float(np.mean(values)), 6),
                "std": round(float(np.std(values)), 6),
                "min": round(float(np.min(values)), 6),
                "max": round(float(np.max(values)), 6),
            }

    return results


# ---------------------------------------------------------------------------
# CLI and output
# ---------------------------------------------------------------------------

def print_summary_table(results: dict) -> None:
    """Print a human-readable comparison table to stdout."""
    tunings = ["12tet", "ji5", "ji7"]
    tuning_labels = {"12tet": "12-TET", "ji5": "5-limit JI", "ji7": "7-limit JI"}
    chord_labels = {
        "major_triad": "Major triad",
        "minor_triad": "Minor triad",
        "dominant_7th": "Dom. 7th",
        "diminished_7th": "Dim. 7th",
    }

    header = f"{'Chord type':<18}"
    for t in tunings:
        header += f" | {tuning_labels[t]:>14}"
    print("\n" + "=" * len(header))
    print("  Sethares Roughness -- Mean across 12 keys (std)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for chord_name in CHORD_TYPES:
        row = f"{chord_labels[chord_name]:<18}"
        for t in tunings:
            s = results["summary"][t][chord_name]
            cell = f"{s['mean']:.4f} ({s['std']:.4f})"
            row += f" | {cell:>14}"
        print(row)

    print("=" * len(header))
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate tuning quality (12-TET vs. JI) using the Sethares (1993) "
            "psychoacoustic roughness model."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        default="research_data/tuning_roughness_eval.json",
        help="Path for JSON results (default: research_data/tuning_roughness_eval.json)",
    )
    args = parser.parse_args()

    print("Running Sethares roughness evaluation ...")
    results = run_evaluation()

    # Print summary
    print_summary_table(results)

    # Save JSON
    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results written to {args.output}")


if __name__ == "__main__":
    main()
