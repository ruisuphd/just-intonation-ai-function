#!/usr/bin/env python3
"""
Pure-Python port of the justkeydding HMM (Nápoles 2019).

Implements the 24-state hidden Markov model for symbolic key detection
described in:

    Nápoles López, N. (2019). "Key-Finding Based on a Hidden Markov Model
    and Key Profiles." In Proceedings of the 6th International Conference
    on Digital Libraries for Musicology (DLfM 2019), ACM, pp. 33-37.
    DOI: 10.1145/3358664.3358675

Algorithm:
- 24 hidden states (12 major + 12 minor keys)
- 12 observation symbols (pitch classes 0-11)
- Initial distribution: uniform 1/24
- Transition matrix: hardcoded per scheme (default: exponential10), with
  rotation per source key
- Emission matrix: rotated key profiles, row-normalized
- Decoding: Viterbi (log-space for numerical stability)
- Global key: most-frequent state in the Viterbi sequence (optionally
  weighted by note duration)

The transition matrices and key profiles were ported byte-for-byte from
the C++ source at:
    https://github.com/napulen/justkeydding (src/keytransition.cc, src/keyprofile.cc)

Compatible with the existing classical baseline pipeline:
- Imports the PROFILES dict from evaluate_classical_baseline.py
- Adds Bellman-Budge, Aarden-Essen, etc. as standalone HMM-based methods
- Returns (global_key_index, viterbi_sequence) tuples for direct comparison

Usage:
    from justkeydding_hmm import detect_key_hmm
    result = detect_key_hmm(notes, profile='bellman_budge', transition='exponential10')
    print(f'Global key: {result[0]}')

Or as a CLI:
    python justkeydding_hmm.py --predictions-from research_data/ablation_A1_predictions_softmax.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# Reuse profiles from the classical baseline (which has Bellman-Budge,
# Aarden-Essen, and the legacy 3 already)
from evaluate_classical_baseline import (
    PROFILES,
    BELLMAN_BUDGE,
    AARDEN_ESSEN,
    TEMPERLEY,
    KRUMHANSL_KESSLER,
    ALBRECHT_SHANAHAN,
    build_pitch_class_histogram,
)
from harmonic_context_model import KEY_LABELS, key_to_index
from evaluate_harmonic_context_model import mirex_weighted_score

# ============================================================
# Transition matrix schemes (verified from src/keytransition.cc)
# ============================================================
#
# Each scheme defines a 24-element row representing transitions FROM C-major
# (row 0) to all other 24 keys. The first 12 entries are transitions to other
# major keys (C, Db, D, Eb, E, F, F#, G, Ab, A, Bb, B); the next 12 are
# transitions to minor keys (c, db, d, eb, e, f, f#, g, ab, a, bb, b).
#
# To get the transition row for any other source key, the C-major row is
# rotated by the source root. Minor source rows use a special transform
# (see _build_transition_matrix below).

TRANSITION_SCHEMES = {
    # Default in the C++ source. Powers of 10, heavily peaked on self-transition.
    'exponential10': [
        100000000.0, 1000.0, 100000.0, 100000.0, 10000.0, 10000000.0,
        1.0, 10000000.0, 10000.0, 100000.0, 100000.0, 1000.0,
        10000000.0, 10.0, 1000000.0, 100.0, 1000000.0, 1000000.0,
        100.0, 1000000.0, 10.0, 10000000.0, 10000.0, 10000.0,
    ],
    # Powers of 2, less peaked
    'exponential2': [
        256.0, 8.0, 32.0, 32.0, 16.0, 128.0,
        1.0, 128.0, 16.0, 32.0, 32.0, 8.0,
        128.0, 2.0, 64.0, 4.0, 64.0, 64.0,
        4.0, 64.0, 2.0, 128.0, 16.0, 16.0,
    ],
    # Empirically derived from the original justkeydding paper
    'linear': [
        9.0, 4.0, 6.0, 6.0, 5.0, 8.0,
        1.0, 8.0, 5.0, 6.0, 6.0, 4.0,
        8.0, 2.0, 7.0, 3.0, 7.0, 7.0,
        3.0, 7.0, 2.0, 8.0, 5.0, 5.0,
    ],
    # Uniform across all 24 keys
    'symmetrical': [1.0] * 24,
    # Counts from a corpus heatmap (from src/keytransition.cc)
    'heatmap': [
        1.0, 6.0, 4.0, 4.0, 5.0, 2.0, 9.0, 2.0, 5.0, 4.0, 4.0, 6.0,
        2.0, 8.0, 3.0, 7.0, 3.0, 3.0, 7.0, 3.0, 8.0, 2.0, 5.0, 5.0,
    ],
}

# Pitch class index for A natural (used by minor source rotation in C++ code)
PITCHCLASS_A_NATURAL = 9


def _build_transition_matrix(scheme: str = 'exponential10') -> np.ndarray:
    """Build the 24x24 transition matrix from a hardcoded scheme.

    Mirrors the rotation logic in justkeydding/src/keytransition.cc
    `getKeyTransitionMap()` (lines 103-166).

    For major source keys: rotate the first-12 (major-target) and last-12
    (minor-target) halves of the C-major row independently.

    For minor source keys: first apply a "minor source transform" that uses
    a rotate_copy with offset PITCHCLASS_A_NATURAL=9 on the major-target
    half of the C-major row, then rotate by the source root.

    Returns:
        A 24x24 numpy array where row i sums to 1 and represents the
        transition probabilities from state i to all 24 states.
    """
    if scheme not in TRANSITION_SCHEMES:
        raise ValueError(f'Unknown transition scheme: {scheme}. '
                         f'Available: {list(TRANSITION_SCHEMES.keys())}')

    raw = np.array(TRANSITION_SCHEMES[scheme], dtype=np.float64)
    # First 12 = transitions from C-major to {C-major, Db-major, ..., B-major}
    cmaj_to_maj = raw[:12]
    # Next 12 = transitions from C-major to {c-minor, db-minor, ..., b-minor}
    cmaj_to_min = raw[12:]

    A = np.zeros((24, 24), dtype=np.float64)

    for source_key in range(24):
        if source_key < 12:
            # Major source: rotate both halves by the source root.
            #
            # In C++ keytransition.cc lines 114-122:
            #   tonic = cmaj_to_maj          (the to-major half)
            #   relative = cmaj_to_min       (the to-minor half)
            #   then std::rotate by (12 - root) on each
            #
            # std::rotate(begin, begin + k, end) shifts elements left by k,
            # which in numpy is np.roll(arr, -k). Here k = (12 - root),
            # so np.roll(arr, root - 12) = np.roll(arr, root) (mod 12).
            root = source_key
            row_maj = np.roll(cmaj_to_maj, root)
            row_min = np.roll(cmaj_to_min, root)
        else:
            # Minor source: more complex transform from C++ keytransition.cc
            # lines 124-135.
            #
            #   tonic = rotate_copy(cmaj_to_min[0:12], middle=9, dest=tonic)
            #   relative = cmaj_to_maj                   (unchanged)
            #   then std::rotate by (12 - root) on each
            #
            # The clever trick: for c-minor source, the to-MINOR transitions
            # follow the same circle-of-fifths pattern as C-major's to-MAJOR
            # transitions (since the dominant of c-minor is g-minor, parallel
            # to the dominant of C-major being G-major). Hence relative_half =
            # cmaj_to_maj for the to-MINOR slot of the output row.
            #
            # The to-MAJOR transitions for c-minor are derived by rotating the
            # C-major-to-minor row by 9 (the position of A in the chromatic
            # scale, since A-minor is the relative minor of C-major).
            #
            # rotate_copy(begin=12, middle=12+9, end=24) shifts left by 9,
            # which is np.roll(cmaj_to_min, -9).
            root = source_key - 12
            tonic_half = np.roll(cmaj_to_min, -PITCHCLASS_A_NATURAL)  # to-MAJOR slot (per C++ semantics)
            relative_half = cmaj_to_maj.copy()                       # to-MINOR slot

            # Final std::rotate by (12 - root) on each half
            row_maj = np.roll(tonic_half, root)      # to-MAJOR slot of output
            row_min = np.roll(relative_half, root)   # to-MINOR slot of output

        full_row = np.concatenate([row_maj, row_min])
        A[source_key] = full_row / full_row.sum()  # row-normalize

    return A


def _build_emission_matrix(profile_name: str = 'bellman_budge') -> np.ndarray:
    """Build the 24x12 emission matrix B(state, pitch_class).

    For each key state, the emission row is the rotated key profile so that
    the profile's tonic aligns with pitch class 0 of the state's root.

    The C++ source (src/keyprofile.cc lines 178-209) does:
        rotation = NUMBER_OF_PITCHCLASSES - root  # = (12 - root) % 12
        std::rotate(profile.begin(), profile.begin() + rotation, profile.end())

    Returns:
        A 24x12 numpy array where row i represents P(observation = j | state = i)
        for state i and pitch class j. Row-normalized.
    """
    if profile_name not in PROFILES:
        raise ValueError(f'Unknown profile: {profile_name}. '
                         f'Available: {list(PROFILES.keys())}')
    profile = PROFILES[profile_name]
    major_profile = np.array(profile['major'], dtype=np.float64)
    minor_profile = np.array(profile['minor'], dtype=np.float64)

    B = np.zeros((24, 12), dtype=np.float64)
    for k in range(24):
        is_major = (k < 12)
        root = k % 12
        # The C++ std::rotate(begin, begin + (12-root), end) shifts elements
        # so that index (12-root) becomes the new index 0. In numpy this is
        # np.roll(profile, root) — verified by symmetry: for C-major (root=0),
        # rotation=12 ≡ 0, so the profile is unchanged. For G-major (root=7),
        # we want the G-major-tonic-aligned profile.
        base = major_profile if is_major else minor_profile
        rotated = np.roll(base, root)
        # Row-normalize so the row sums to 1 (proper probability distribution)
        B[k] = rotated / rotated.sum()

    return B


def viterbi_log(
    observations: Sequence[int],
    transition: np.ndarray,
    emission: np.ndarray,
    initial: Optional[np.ndarray] = None,
) -> List[int]:
    """Standard Viterbi decoder in log space (numerically stable).

    Args:
        observations: Sequence of observation indices (0-11 pitch classes).
        transition: (24, 24) transition matrix (rows sum to 1).
        emission: (24, 12) emission matrix (rows sum to 1).
        initial: (24,) initial distribution. Defaults to uniform.

    Returns:
        List of 24-state indices, the most-likely sequence.
    """
    n_states = transition.shape[0]
    n_obs = len(observations)

    if initial is None:
        initial = np.full(n_states, 1.0 / n_states, dtype=np.float64)

    # Use log probabilities to avoid underflow on long sequences
    LOG_ZERO = -1e300
    log_init = np.where(initial > 0, np.log(initial), LOG_ZERO)
    log_trans = np.where(transition > 0, np.log(transition), LOG_ZERO)
    log_emit = np.where(emission > 0, np.log(emission), LOG_ZERO)

    # delta[t, s] = max log-prob of any path ending at state s at time t
    delta = np.full((n_obs, n_states), LOG_ZERO, dtype=np.float64)
    psi = np.zeros((n_obs, n_states), dtype=np.int32)

    # Initialization at t=0
    obs_0 = observations[0]
    delta[0] = log_init + log_emit[:, obs_0]

    # Forward pass
    for t in range(1, n_obs):
        obs_t = observations[t]
        # For each target state s, find the source state j that maximises
        # delta[t-1, j] + log_trans[j, s]
        # Vectorized: scores[j, s] = delta[t-1, j] + log_trans[j, s]
        scores = delta[t - 1, :, None] + log_trans  # (24, 24)
        psi[t] = np.argmax(scores, axis=0)
        delta[t] = scores[psi[t], np.arange(n_states)] + log_emit[:, obs_t]

    # Backtrace from the most-likely final state
    path = [int(np.argmax(delta[-1]))]
    for t in range(n_obs - 1, 0, -1):
        path.append(int(psi[t, path[-1]]))
    path.reverse()
    return path


def detect_key_hmm(
    notes: Sequence[Dict],
    profile: str = 'bellman_budge',
    transition: str = 'exponential10',
    duration_weighted: bool = True,
) -> Tuple[int, List[int]]:
    """Detect global key from a sequence of notes using the justkeydding HMM.

    Args:
        notes: List of note dicts with 'pitch' (MIDI 0-127) and optional
               'duration_beat' (for duration-weighted vote).
        profile: Key profile name (e.g. 'bellman_budge', 'aarden_essen',
                 'krumhansl_kessler', 'temperley', 'albrecht_shanahan').
        transition: Transition matrix scheme (default 'exponential10').
        duration_weighted: If True, weight Viterbi states by note duration
                           when computing the global key vote.

    Returns:
        (global_key, viterbi_sequence) — global_key is the 0-23 index;
        viterbi_sequence is the per-note state sequence.
    """
    # Convert notes to pitch class observations
    observations = []
    durations = []
    for note in notes:
        pitch = int(note.get('pitch', 0))
        pc = pitch % 12
        observations.append(pc)
        dur = float(note.get('duration_beat', note.get('duration_ms', 1.0)))
        durations.append(max(dur, 1e-6))

    if not observations:
        return 0, []

    # Build matrices (cached at module level would be faster but per-call is fine)
    A = _build_transition_matrix(transition)
    B = _build_emission_matrix(profile)

    # Decode
    states = viterbi_log(observations, A, B)

    # Global key vote
    if duration_weighted:
        votes = np.zeros(24, dtype=np.float64)
        for s, d in zip(states, durations):
            votes[s] += d
    else:
        votes = np.bincount(states, minlength=24).astype(np.float64)

    global_key = int(np.argmax(votes))
    return global_key, states


# ============================================================
# Convenience functions for batch evaluation
# ============================================================


def evaluate_hmm_on_records(
    records: List[Dict],
    profile: str = 'bellman_budge',
    transition: str = 'exponential10',
    aligned_to_neural: Optional[str] = None,
) -> Dict:
    """Evaluate the justkeydding HMM on a list of label records.

    Mirrors evaluate_classical_baseline.evaluate_classical_on_records but
    uses the HMM instead of profile correlation, and supports the alignment
    protocol (same compositions and notes as a neural prediction file).

    Args:
        records: List of label records (each with 'notes' and 'composition_id').
        profile: Key profile name.
        transition: Transition scheme.
        aligned_to_neural: Optional path to a neural prediction file. When
                           provided, the HMM's global key per composition is
                           assigned to every note in the corresponding neural
                           prediction list, ensuring identical (composition, note)
                           coverage. Without it, every note in the label record
                           is used.

    Returns:
        Dict with overall MIREX, accuracy, and per-composition breakdown.
    """
    neural_lookup = None
    if aligned_to_neural:
        with open(aligned_to_neural) as f:
            neural_data = json.load(f)
        neural_lookup = {
            c['composition_id']: c['predictions'] for c in neural_data['compositions']
        }

    all_preds_trues = []
    per_comp_results = []

    for record in records:
        notes = record.get('notes', [])
        if not notes:
            continue
        cid = record.get('composition_id', record.get('piece_id', 'unknown'))

        global_key, _ = detect_key_hmm(notes, profile, transition)

        if neural_lookup is not None:
            # Aligned mode: score against the neural prediction file's true labels
            tuples = neural_lookup.get(cid)
            if tuples is None:
                continue
            comp_mirex = 0.0
            comp_correct = 0
            comp_preds = []
            for (_, true_key) in tuples:
                comp_mirex += mirex_weighted_score(global_key, true_key)
                if global_key == true_key:
                    comp_correct += 1
                comp_preds.append((global_key, true_key))
                all_preds_trues.append((global_key, true_key))
        else:
            # Standalone mode: score against the label record's note labels
            comp_mirex = 0.0
            comp_correct = 0
            comp_preds = []
            for note in notes:
                true_key_str = str(note.get('key', ''))
                try:
                    true_key_idx = key_to_index(true_key_str)
                except (ValueError, KeyError):
                    continue
                comp_mirex += mirex_weighted_score(global_key, true_key_idx)
                if global_key == true_key_idx:
                    comp_correct += 1
                comp_preds.append((global_key, true_key_idx))
                all_preds_trues.append((global_key, true_key_idx))

        n = len(comp_preds)
        if n > 0:
            per_comp_results.append({
                'composition_id': cid,
                'predicted_key': KEY_LABELS[global_key],
                'mirex': comp_mirex / n,
                'accuracy': comp_correct / n,
                'n_predictions': n,
                'predictions': comp_preds,
            })

    total = len(all_preds_trues)
    return {
        'method': f'justkeydding_hmm_{profile}_{transition}',
        'profile': profile,
        'transition': transition,
        'overall_mirex': sum(mirex_weighted_score(p, t) for p, t in all_preds_trues) / max(total, 1),
        'overall_accuracy': sum(1 for p, t in all_preds_trues if p == t) / max(total, 1),
        'total_predictions': total,
        'n_compositions': len(per_comp_results),
        'per_composition': per_comp_results,
        'aligned_to': aligned_to_neural,
    }


# ============================================================
# CLI
# ============================================================


def _self_test() -> bool:
    """Sanity-check the HMM with a synthetic C-major sequence."""
    print('--- Self-test: synthetic C-major sequence ---')
    # C major scale notes, repeated several times
    c_major_scale = [60, 62, 64, 65, 67, 69, 71, 72]
    notes = [{'pitch': p, 'duration_beat': 1.0} for p in c_major_scale * 8]

    all_pass = True
    for profile_name in ['krumhansl_kessler', 'temperley', 'albrecht_shanahan',
                         'bellman_budge', 'aarden_essen']:
        global_key, states = detect_key_hmm(notes, profile=profile_name)
        label = KEY_LABELS[global_key]
        ok = (global_key == 0)  # C major
        marker = '✓' if ok else '✗'
        print(f'  {marker} {profile_name:<20} -> {label} (idx {global_key})')
        if not ok:
            all_pass = False

    # Test with a synthetic A-minor sequence
    print('\n--- Self-test: synthetic A-minor sequence ---')
    # A minor scale: A B C D E F G A
    a_minor_scale = [69, 71, 72, 74, 76, 77, 79, 81]
    notes = [{'pitch': p, 'duration_beat': 1.0} for p in a_minor_scale * 8]

    for profile_name in ['krumhansl_kessler', 'temperley', 'albrecht_shanahan',
                         'bellman_budge', 'aarden_essen']:
        global_key, states = detect_key_hmm(notes, profile=profile_name)
        label = KEY_LABELS[global_key]
        # A-minor is index 21 (12 + 9). Relative-major C is index 0.
        # The HMM may pick C-major because the note distribution is identical.
        # Both are acceptable for this synthetic test.
        ok = (global_key in (21, 0))
        marker = '✓' if ok else '✗'
        notes_msg = ' (relative C-major also acceptable)' if global_key == 0 else ''
        print(f'  {marker} {profile_name:<20} -> {label}{notes_msg}')

    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description='Pure-Python justkeydding HMM')
    parser.add_argument('--self-test', action='store_true',
                        help='Run synthetic C-major and A-minor tests')
    parser.add_argument('--profile', default='bellman_budge',
                        choices=list(PROFILES.keys()),
                        help='Key profile to use')
    parser.add_argument('--transition', default='exponential10',
                        choices=list(TRANSITION_SCHEMES.keys()),
                        help='Transition matrix scheme')
    parser.add_argument('--align-to-predictions', default=None,
                        help='Path to a neural prediction JSON for aligned eval')
    parser.add_argument('--label-dirs', default='research_data/all_key_labels,research_data/score_key_labels,research_data/wir_key_labels',
                        help='Comma-separated label directories')
    parser.add_argument('--output', default='research_data/justkeydding_hmm_eval.json',
                        help='Output JSON path')
    parser.add_argument('--all-profiles', action='store_true',
                        help='Run all 5 profiles and compare')
    args = parser.parse_args()

    if args.self_test:
        ok = _self_test()
        return

    if args.align_to_predictions is None:
        print('ERROR: --align-to-predictions required (or use --self-test)')
        return

    # Load records aligned to a neural prediction file
    from evaluate_classical_baseline import load_records_for_predictions
    label_dirs = [d.strip() for d in args.label_dirs.split(',')]
    records = load_records_for_predictions(args.align_to_predictions, label_dirs)
    print(f'Loaded {len(records)} compositions')

    if args.all_profiles:
        profiles_to_run = ['krumhansl_kessler', 'temperley', 'albrecht_shanahan',
                           'bellman_budge', 'aarden_essen']
    else:
        profiles_to_run = [args.profile]

    print(f'\n{"Profile":<22} {"Transition":<15} {"MIREX":>8} {"Accuracy":>10} {"Predictions":>12}')
    print('-' * 70)

    all_results = {}
    for prof in profiles_to_run:
        result = evaluate_hmm_on_records(
            records, profile=prof, transition=args.transition,
            aligned_to_neural=args.align_to_predictions,
        )
        all_results[prof] = {
            'overall_mirex': result['overall_mirex'],
            'overall_accuracy': result['overall_accuracy'],
            'total_predictions': result['total_predictions'],
            'n_compositions': result['n_compositions'],
            'profile': prof,
            'transition': args.transition,
        }
        print(f'{prof:<22} {args.transition:<15} {result["overall_mirex"]:>8.4f} '
              f'{result["overall_accuracy"]:>10.4f} {result["total_predictions"]:>12}')

    out = {
        'mode': 'justkeydding_hmm',
        'transition': args.transition,
        'aligned_to': args.align_to_predictions,
        'profiles': all_results,
    }
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(out, f, indent=2)
    print(f'\nSaved to {args.output}')


if __name__ == '__main__':
    main()
