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


def piano_partials(
    fundamental: float,
    n_partials: int = NUM_PARTIALS,
    inharmonicity: float = 0.0005,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return arrays of (frequencies, amplitudes) for a piano-like tone.

    Real piano strings are slightly inharmonic due to stiffness — the nth
    partial is higher than the ideal n*f0 by a factor of sqrt(1 + B*n^2),
    where B is the inharmonicity coefficient.  Typical values: B ~ 0.0003
    for bass strings, B ~ 0.001 for treble strings (Gough 1997).

    Parameters
    ----------
    fundamental : float
        Fundamental frequency in Hz.
    n_partials : int
        Number of harmonic partials to include.
    inharmonicity : float
        Inharmonicity coefficient B (default 0.0005, mid-range piano).
        Set to 0.0 for ideal harmonics.

    Returns
    -------
    freqs : ndarray, shape (n_partials,)
    amps : ndarray, shape (n_partials,)

    References
    ----------
    Gough, C. E. (1997). "The Theory of Piano String Vibration."
    J. Sound and Vibration, 200(5), 519-539.
    """
    ns = np.arange(1, n_partials + 1, dtype=float)
    freqs = fundamental * ns * np.sqrt(1.0 + inharmonicity * ns ** 2)
    amps = 1.0 / ns
    return freqs, amps


# ---------------------------------------------------------------------------
# Roughness models
# ---------------------------------------------------------------------------

def sethares_roughness(freqs: np.ndarray, amps: np.ndarray) -> float:
    """Compute sensory roughness using the Vassilakis (2001) refinement.

    The original Sethares (1993) model weights roughness by a_i * a_j,
    which overweights the fundamental pair relative to upper-partial
    coincidences.  Vassilakis (2001) [2] refines the amplitude weighting to

        w = min(a_i, a_j)^0.606 * (a_i * a_j)^0.0606

    which better captures the perceptual reality that partial coincidences
    at different amplitude levels contribute meaningfully to consonance.

    The frequency-dependent kernel is unchanged from Sethares (1993):

        R = sum_{i<j} w * [exp(-b1 * s * |f_i - f_j|)
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

    References
    ----------
    .. [1] Sethares (1993), JASA 94(3), 1218-1228.
    .. [2] Vassilakis (2001), PhD thesis, UCLA.
    """
    n = len(freqs)
    roughness = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            f_min = min(freqs[i], freqs[j])
            delta_f = abs(freqs[i] - freqs[j])
            s = 0.24 / (0.0207 * f_min + 18.96)
            # Vassilakis amplitude weighting
            a_min = min(amps[i], amps[j])
            a_prod = amps[i] * amps[j]
            w = (a_min ** 0.606) * (a_prod ** 0.0606)
            roughness += (
                w * (np.exp(-B1 * s * delta_f) - np.exp(-B2 * s * delta_f))
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
# Passage-level evaluation
# ---------------------------------------------------------------------------

def load_passage_from_label_json(
    label_path: str,
    start_measure: int,
    end_measure: int,
) -> List[Dict]:
    """Load notes for a measure range from a score_key_labels JSON file.

    Parameters
    ----------
    label_path : str
        Path to a JSON label file produced by extract_score_key_labels.py.
    start_measure, end_measure : int
        Inclusive measure range to extract.

    Returns
    -------
    list of dict
        Note dicts with keys: pitch, onset_beat, duration_beat, key, tonic_pc, is_minor, scale_degree.
    """
    with open(label_path, "r") as f:
        data = json.load(f)
    return [
        n for n in data["notes"]
        if start_measure <= n.get("measure_index", 0) <= end_measure
    ]


def compute_onset_groups(
    notes: List[Dict],
    tolerance_beats: float = 0.05,
) -> List[List[Dict]]:
    """Group notes by onset time, including sustained notes.

    At each onset, the sounding notes are: (a) notes whose onset matches this
    group, plus (b) previously started notes whose onset + duration exceeds
    this onset.

    Parameters
    ----------
    notes : list of dict
        Notes sorted by onset_beat.
    tolerance_beats : float
        Maximum beat difference to consider notes simultaneous.

    Returns
    -------
    list of list of dict
        Each inner list contains all notes sounding at that onset.
    """
    if not notes:
        return []

    sorted_notes = sorted(notes, key=lambda n: n.get("onset_beat", 0.0))
    groups: List[List[Dict]] = []
    current_onset = sorted_notes[0].get("onset_beat", 0.0)
    current_group_onsets: List[Dict] = []

    for note in sorted_notes:
        onset = note.get("onset_beat", 0.0)
        if abs(onset - current_onset) <= tolerance_beats:
            current_group_onsets.append(note)
        else:
            # Flush current group: add sustained notes from earlier onsets
            sounding = list(current_group_onsets)
            for prev_group in groups:
                for prev_note in prev_group:
                    prev_end = prev_note.get("onset_beat", 0) + prev_note.get("duration_beat", 0)
                    if prev_end > current_onset + tolerance_beats:
                        if prev_note not in sounding:
                            sounding.append(prev_note)
            if sounding:
                groups.append(sounding)
            current_onset = onset
            current_group_onsets = [note]

    # Flush final group
    if current_group_onsets:
        sounding = list(current_group_onsets)
        for prev_group in groups:
            for prev_note in prev_group:
                prev_end = prev_note.get("onset_beat", 0) + prev_note.get("duration_beat", 0)
                if prev_end > current_onset + tolerance_beats:
                    if prev_note not in sounding:
                        sounding.append(prev_note)
        groups.append(sounding)

    return groups


def evaluate_passage_roughness(
    notes: List[Dict],
    tuning: str,
) -> Dict:
    """Compute roughness at each onset of a musical passage.

    Parameters
    ----------
    notes : list of dict
        Notes from a label JSON (must have pitch, is_minor, tonic_pc, scale_degree).
    tuning : str
        One of "12tet", "ji5", "ji7".

    Returns
    -------
    dict with keys: per_onset (list of floats), mean, max, onset_count.
    """
    onset_groups = compute_onset_groups(notes)
    per_onset = []

    for group in onset_groups:
        if len(group) < 2:
            continue  # single notes have no roughness

        # Build combined partial spectrum
        all_freqs = []
        all_amps = []
        for note in group:
            pitch = note["pitch"]
            is_minor = note.get("is_minor", False)
            tonic_pc = note.get("tonic_pc", 0)
            scale_degree = note.get("scale_degree", (pitch - tonic_pc) % 12)

            if tuning == "12tet":
                f0 = midi_to_freq(pitch)
            elif tuning == "ji5":
                table = JI_RATIOS_MINOR if is_minor else JI_RATIOS_MAJOR
                ratio = table.get(scale_degree, 1.0)
                # JI frequency = ET frequency adjusted by ratio deviation
                et_cents = scale_degree * 100
                ji_cents = 1200 * np.log2(ratio) if ratio > 0 else et_cents
                cents_dev = ji_cents - et_cents
                f0 = midi_to_freq(pitch) * (2.0 ** (cents_dev / 1200.0))
            elif tuning == "ji7":
                table = JI_RATIOS_7LIMIT if not is_minor else {**JI_RATIOS_MINOR, 10: 7 / 4}
                ratio = table.get(scale_degree, 1.0)
                et_cents = scale_degree * 100
                ji_cents = 1200 * np.log2(ratio) if ratio > 0 else et_cents
                cents_dev = ji_cents - et_cents
                f0 = midi_to_freq(pitch) * (2.0 ** (cents_dev / 1200.0))
            else:
                raise ValueError(f"Unknown tuning: {tuning}")

            f, a = piano_partials(f0)
            all_freqs.append(f)
            all_amps.append(a)

        all_freqs_arr = np.concatenate(all_freqs)
        all_amps_arr = np.concatenate(all_amps)
        r = sethares_roughness(all_freqs_arr, all_amps_arr)
        per_onset.append(r)

    if not per_onset:
        return {"per_onset": [], "mean": 0.0, "max": 0.0, "onset_count": 0}

    return {
        "per_onset": [round(r, 6) for r in per_onset],
        "mean": round(float(np.mean(per_onset)), 6),
        "max": round(float(np.max(per_onset)), 6),
        "onset_count": len(per_onset),
    }


def select_evaluation_passages() -> List[Dict]:
    """Return a curated list of passages for roughness evaluation.

    Each passage specifies a label file, measure range, and a description
    of why it was selected (e.g., dominant 7th content, minor key, chromatic).
    """
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "research_data", "score_key_labels")
    passages = [
        # Homophonic / chordal textures
        {"label_file": os.path.join(base, "0009.json"), "start": 0, "end": 8,
         "description": "Rachmaninoff Op.32 — opening homophonic chords"},
        {"label_file": os.path.join(base, "0009.json"), "start": 16, "end": 24,
         "description": "Rachmaninoff Op.32 — development (dominant 7ths)"},
        {"label_file": os.path.join(base, "1166.json"), "start": 0, "end": 16,
         "description": "Beethoven sonata — opening theme"},
        {"label_file": os.path.join(base, "1166.json"), "start": 32, "end": 48,
         "description": "Beethoven sonata — development section"},
        # Minor-key pieces
        {"label_file": os.path.join(base, "0007.json"), "start": 0, "end": 16,
         "description": "Rachmaninoff G#m prelude — minor key opening"},
        {"label_file": os.path.join(base, "0861.json"), "start": 0, "end": 16,
         "description": "Schubert — minor key lyrical passage"},
        {"label_file": os.path.join(base, "1082.json"), "start": 0, "end": 16,
         "description": "Brahms — minor key opening"},
        # Chromatic / impressionist
        {"label_file": os.path.join(base, "0645.json"), "start": 0, "end": 16,
         "description": "Debussy — impressionist harmonies"},
        {"label_file": os.path.join(base, "0716.json"), "start": 0, "end": 16,
         "description": "Ravel — chromatic passage (minor)"},
        # Polyphonic
        {"label_file": os.path.join(base, "0339.json"), "start": 0, "end": 16,
         "description": "Bach — polyphonic counterpoint"},
        # Extended minor
        {"label_file": os.path.join(base, "1495.json"), "start": 0, "end": 16,
         "description": "Liszt B minor sonata — dramatic opening"},
        {"label_file": os.path.join(base, "0127.json"), "start": 0, "end": 16,
         "description": "Scriabin — chromatic minor passage"},
        # Classical major
        {"label_file": os.path.join(base, "1113.json"), "start": 0, "end": 16,
         "description": "Mozart — Classical major opening"},
        {"label_file": os.path.join(base, "1064.json"), "start": 0, "end": 16,
         "description": "Haydn — Classical major opening"},
    ]
    # Filter to only passages whose label files exist
    return [p for p in passages if os.path.exists(p["label_file"])]


def run_passage_evaluation() -> Dict:
    """Evaluate roughness on curated musical passages under all three tunings.

    Returns
    -------
    dict
        Results with per-passage and aggregate statistics.
    """
    passages = select_evaluation_passages()
    tunings = ["12tet", "ji5", "ji7"]

    results = {"passages": [], "aggregate": {}}

    for psg in passages:
        notes = load_passage_from_label_json(psg["label_file"], psg["start"], psg["end"])
        if len(notes) < 4:
            continue

        passage_result = {
            "description": psg["description"],
            "label_file": os.path.basename(psg["label_file"]),
            "measures": f"{psg['start']}-{psg['end']}",
            "note_count": len(notes),
            "tunings": {},
        }

        for tuning in tunings:
            passage_result["tunings"][tuning] = evaluate_passage_roughness(notes, tuning)

        results["passages"].append(passage_result)

    # Aggregate: mean of means across passages
    for tuning in tunings:
        means = [
            p["tunings"][tuning]["mean"]
            for p in results["passages"]
            if p["tunings"][tuning]["onset_count"] > 0
        ]
        if means:
            results["aggregate"][tuning] = {
                "mean_of_means": round(float(np.mean(means)), 6),
                "std_of_means": round(float(np.std(means)), 6),
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
    parser.add_argument(
        "--passages",
        action="store_true",
        help="Run passage-level roughness evaluation on curated musical excerpts",
    )
    args = parser.parse_args()

    if args.passages:
        print("Running passage-level roughness evaluation ...")
        passage_results = run_passage_evaluation()

        # Print passage summary
        print(f"\n{'='*80}")
        print("  Passage-Level Roughness (Sethares/Vassilakis model)")
        print(f"{'='*80}")
        print(f"{'Passage':<50} | {'12-TET':>8} | {'5-lim JI':>8} | {'7-lim JI':>8}")
        print("-" * 80)
        for p in passage_results["passages"]:
            desc = p["description"][:48]
            vals = []
            for t in ["12tet", "ji5", "ji7"]:
                m = p["tunings"][t]["mean"]
                vals.append(f"{m:.4f}")
            print(f"{desc:<50} | {vals[0]:>8} | {vals[1]:>8} | {vals[2]:>8}")
        print("-" * 80)
        if passage_results["aggregate"]:
            agg_vals = []
            for t in ["12tet", "ji5", "ji7"]:
                m = passage_results["aggregate"].get(t, {}).get("mean_of_means", 0)
                agg_vals.append(f"{m:.4f}")
            print(f"{'AGGREGATE MEAN':<50} | {agg_vals[0]:>8} | {agg_vals[1]:>8} | {agg_vals[2]:>8}")
        print(f"{'='*80}\n")

        # Save passage results
        passage_output = args.output.replace(".json", "_passages.json")
        out_dir = os.path.dirname(passage_output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(passage_output, "w") as f:
            json.dump(passage_results, f, indent=2)
        print(f"Passage results written to {passage_output}")
        return

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
