#!/usr/bin/env python3
"""
Evaluate classical key-finding algorithms on the ATEPP-319 test set.

Implements Krumhansl-Kessler (1982), Temperley (1999), Albrecht-Shanahan (2013),
Bellman-Budge (Budge 1943; Temperley 2007), and Aarden-Essen (Aarden 2003)
profile-correlation methods. Reports MIREX weighted scores on the same test set
used for neural model evaluation, enabling direct comparison.

Profile values sourced from Nápoles (2019) "Key-Finding Based on a Hidden Markov
Model and Key Profiles" (DLfM 2019, DOI 10.1145/3358664.3358675) — see the
justkeydding project at https://github.com/napulen/justkeydding. The current
file uses the 3-decimal-rounded versions of the Krumhansl-Kessler, Temperley,
and Albrecht-Shanahan profiles for backwards compatibility with Phase 1/Phase 2
results already reported. The new Bellman-Budge and Aarden-Essen profiles use
full-precision values from justkeydding src/keyprofile.cc to enable byte-
equivalent reproduction of the Nápoles 2019 results.

Usage:
    python evaluate_classical_baseline.py
    python evaluate_classical_baseline.py --manifest research_data/unified_training_manifest.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
from typing import Dict, List, Tuple

import numpy as np

from harmonic_context_model import KEY_LABELS, key_to_index
from evaluate_harmonic_context_model import (
    mirex_weighted_score,
    bootstrap_mirex_ci,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Key Profiles ---
#
# The first three profiles (Krumhansl-Kessler, Temperley, Albrecht-Shanahan)
# retain their original 3-decimal precision as used in Phase 1 and Phase 2 to
# maintain reproducibility of already-reported ablation results. The new
# profiles (Bellman-Budge, Aarden-Essen) use full precision from the justkeydding
# C++ source (src/keyprofile.cc) to match Nápoles (2019) byte-for-byte.
#
# Sources:
#   - Krumhansl & Kessler (1982). Psychological Review, 89(4).
#   - Temperley (1999). Music Perception, 17(1).
#   - Albrecht & Shanahan (2013). Music Perception, 31(1).
#   - Budge (1943) dissertation; reproduced in Temperley (2007), Music Perception, 25(2).
#   - Aarden (2003). PhD dissertation, Ohio State University (Essen folksong corpus).
#   - Nápoles López (2019). "Key-Finding Based on an HMM and Key Profiles." DLfM 2019.
#     https://github.com/napulen/justkeydding

ALBRECHT_SHANAHAN = {
    'major': [0.238, 0.006, 0.111, 0.006, 0.137, 0.094, 0.016, 0.214, 0.009, 0.080, 0.008, 0.081],
    'minor': [0.220, 0.006, 0.104, 0.123, 0.019, 0.103, 0.012, 0.214, 0.062, 0.022, 0.061, 0.052],
}

TEMPERLEY = {
    'major': [0.176, 0.014, 0.115, 0.019, 0.158, 0.108, 0.023, 0.168, 0.024, 0.086, 0.013, 0.094],
    'minor': [0.170, 0.020, 0.113, 0.148, 0.012, 0.110, 0.025, 0.179, 0.097, 0.016, 0.032, 0.079],
}

KRUMHANSL_KESSLER = {
    'major': [0.152, 0.053, 0.083, 0.056, 0.105, 0.098, 0.060, 0.124, 0.057, 0.088, 0.055, 0.069],
    'minor': [0.142, 0.060, 0.079, 0.121, 0.058, 0.079, 0.057, 0.107, 0.089, 0.060, 0.075, 0.071],
}

# Bellman-Budge (Temperley 2007 reproduction; full precision from justkeydding).
# Historically the strongest profile in Nápoles 2019's evaluation (94.3% MIREX).
BELLMAN_BUDGE = {
    'major': [0.168, 0.0086, 0.1295, 0.0141, 0.1349, 0.1193,
              0.0125, 0.2028, 0.018000000000000002, 0.0804, 0.0062, 0.1057],
    'minor': [0.1816, 0.0069, 0.12990000000000002, 0.1334, 0.010700000000000001, 0.1115,
              0.0138, 0.2107, 0.07490000000000001, 0.015300000000000001, 0.0092, 0.10210000000000001],
}

# Aarden-Essen (Aarden 2003, Essen folksong corpus; full precision from justkeydding).
# Folksong-derived profile; reported 86.1% MIREX in Nápoles 2019.
AARDEN_ESSEN = {
    'major': [0.17766092893562843, 0.001456239417504233, 0.1492649402940239,
              0.0016018593592562562, 0.19804892078043168, 0.11358695456521818,
              0.002912478835008466, 0.2206199117520353, 0.001456239417504233,
              0.08154936738025305, 0.002329979068008373, 0.049512180195127924],
    'minor': [0.18264800547944018, 0.007376190221285707, 0.14049900421497014,
              0.16859900505797015, 0.0070249402107482066, 0.14436200433086013,
              0.0070249402107482066, 0.18616100558483017, 0.04566210136986304,
              0.019318600579558018, 0.07376190221285707, 0.017562300526869017],
}

# Legacy 3-profile ensemble weights (used in Phase 1/Phase 2). Retained for
# reproducibility of already-reported results. Do not modify without versioning.
ENSEMBLE_WEIGHTS = {
    'albrecht_shanahan': 0.45,
    'temperley': 0.35,
    'krumhansl_kessler': 0.20,
}

# 5-profile ensemble weights (new in v0.9.2-post). Weights follow Nápoles 2019's
# empirical ranking (Bellman-Budge > Albrecht-Shanahan > Temperley > KK > AE).
# These weights should be tuned on validation before being reported in the thesis.
ENSEMBLE_WEIGHTS_5 = {
    'bellman_budge': 0.30,
    'albrecht_shanahan': 0.25,
    'temperley': 0.20,
    'krumhansl_kessler': 0.15,
    'aarden_essen': 0.10,
}

PROFILES = {
    'albrecht_shanahan': ALBRECHT_SHANAHAN,
    'temperley': TEMPERLEY,
    'krumhansl_kessler': KRUMHANSL_KESSLER,
    'bellman_budge': BELLMAN_BUDGE,
    'aarden_essen': AARDEN_ESSEN,
}


def pearson_correlation(x: List[float], y: List[float]) -> float:
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)


def build_pitch_class_histogram(notes: List[Dict]) -> List[float]:
    """Build a 12-bin pitch-class histogram from note events."""
    histogram = [0.0] * 12
    for note in notes:
        pitch = int(note.get('pitch', 0))
        pc = pitch % 12
        # Weight by duration if available, otherwise count
        duration = float(note.get('duration_beat', 1.0))
        histogram[pc] += duration
    total = sum(histogram)
    if total > 0:
        histogram = [h / total for h in histogram]
    return histogram


def detect_key_profile(
    histogram: List[float],
    profile: Dict[str, List[float]],
) -> Tuple[int, float]:
    """Detect key by correlating histogram with rotated profile.

    Returns (key_index, correlation) where key_index is 0-23.
    """
    best_key = 0
    best_corr = -1.0
    for root in range(12):
        # Rotate histogram so that 'root' aligns with profile index 0
        rotated = [histogram[(root + i) % 12] for i in range(12)]
        # Major
        corr_major = pearson_correlation(rotated, profile['major'])
        key_idx = root  # major: 0-11
        if corr_major > best_corr:
            best_corr = corr_major
            best_key = key_idx
        # Minor
        corr_minor = pearson_correlation(rotated, profile['minor'])
        key_idx = root + 12  # minor: 12-23
        if corr_minor > best_corr:
            best_corr = corr_minor
            best_key = key_idx
    return best_key, best_corr


def detect_key_ensemble(
    histogram: List[float],
    weights: Dict[str, float] = None,
) -> Tuple[int, float, Dict[str, Tuple[int, float]]]:
    """Detect key using a weighted ensemble of profiles.

    Args:
        histogram: 12-dim normalized pitch-class histogram.
        weights: Dict mapping profile name to ensemble weight. Defaults to
            ENSEMBLE_WEIGHTS (the legacy 3-profile KK+TE+AS ensemble used in
            Phase 1/Phase 2) for backward compatibility. Use ENSEMBLE_WEIGHTS_5
            to include the new Bellman-Budge and Aarden-Essen profiles.

    Returns (ensemble_key, ensemble_score, per_profile_results).
    """
    if weights is None:
        weights = ENSEMBLE_WEIGHTS

    scores = np.zeros(24)
    per_profile = {}
    for name, weight in weights.items():
        profile = PROFILES[name]
        for root in range(12):
            rotated = [histogram[(root + i) % 12] for i in range(12)]
            corr_major = pearson_correlation(rotated, profile['major'])
            corr_minor = pearson_correlation(rotated, profile['minor'])
            scores[root] += weight * corr_major
            scores[root + 12] += weight * corr_minor
        key_idx, corr = detect_key_profile(histogram, profile)
        per_profile[name] = (key_idx, corr)

    best_key = int(np.argmax(scores))
    best_score = float(scores[best_key])
    return best_key, best_score, per_profile


def load_test_records_from_splits(
    splits_path: str,
    label_dir: str,
) -> List[Dict]:
    """Load test-set records from composition_splits.json."""
    with open(splits_path, 'r') as f:
        splits_data = json.load(f)
    test_ids = {int(item['composition_id']) for item in splits_data['splits']['test']}
    records = []
    for cid in sorted(test_ids):
        path = os.path.join(label_dir, f'{cid:04d}.json')
        if os.path.isfile(path):
            with open(path, 'r') as f:
                records.append(json.load(f))
    return records


def load_test_records_from_manifest(
    manifest_path: str,
    label_dirs: List[str],
) -> List[Dict]:
    """Load test-set records from unified manifest."""
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    records = []
    for entry in manifest['entries']:
        if entry['split'] != 'test':
            continue
        for label_dir in label_dirs:
            path = os.path.join(label_dir, os.path.basename(entry['file_path']))
            if os.path.isfile(path):
                with open(path, 'r') as f:
                    records.append(json.load(f))
                break
        else:
            # Try the original path
            if os.path.isfile(entry['file_path']):
                with open(entry['file_path'], 'r') as f:
                    records.append(json.load(f))
    return records


def load_records_for_predictions(
    predictions_path: str,
    label_dirs: List[str],
) -> List[Dict]:
    """Load only the label records that match a neural prediction file's compositions.

    This implements the prediction-alignment protocol from the research plan:
    given a neural model's prediction file (which contains a fixed set of
    composition IDs), load the matching label files so the classical baseline
    can be evaluated on the EXACT SAME compositions. This is the prerequisite
    for any fair classical-vs-neural comparison.

    Args:
        predictions_path: Path to a neural prediction JSON file (with
            'compositions' list, each having 'composition_id').
        label_dirs: List of directories to search for label files.

    Returns:
        List of label records (one per composition that exists in both the
        neural file and the label dirs).
    """
    with open(predictions_path, 'r') as f:
        pred_data = json.load(f)
    target_ids = [c['composition_id'] for c in pred_data['compositions']]

    records = []
    missing = []
    for cid in target_ids:
        # Try integer-format filename first (e.g. "0007.json"), then string
        candidates = []
        try:
            cid_int = int(cid)
            candidates.append(f'{cid_int:04d}.json')
        except (TypeError, ValueError):
            pass
        candidates.append(f'{cid}.json')

        found = False
        for label_dir in label_dirs:
            for cand in candidates:
                path = os.path.join(label_dir, cand)
                if os.path.isfile(path):
                    with open(path, 'r') as f:
                        rec = json.load(f)
                    # Force composition_id to match the neural file's
                    rec['composition_id'] = cid
                    records.append(rec)
                    found = True
                    break
            if found:
                break
        if not found:
            missing.append(cid)

    if missing:
        print(f'  WARNING: {len(missing)} compositions referenced by predictions '
              f'were not found in any label directory: {missing[:5]}{"..." if len(missing) > 5 else ""}')
    return records


def evaluate_classical_aligned_to_neural(
    label_records: List[Dict],
    neural_predictions_path: str,
    method: str = 'ensemble',
) -> Dict:
    """Evaluate classical method against the EXACT same per-note tuples as a neural model.

    Implements the prediction-alignment protocol: classical methods predict ONE
    global key per composition, but neural models predict per-note. To make a
    fair comparison, we (a) compute the classical global key from each
    composition's notes, (b) assign that prediction to every note in the
    neural prediction list for that composition, and (c) compute MIREX
    against the SAME true labels the neural model used.

    This eliminates the test-set-mismatch artifact where classical methods
    appear stronger than neural simply because they evaluate on a different
    subset (different note count, different composition coverage).

    Args:
        label_records: List of label records (from load_records_for_predictions).
        neural_predictions_path: Path to the neural prediction file (provides
            the canonical (composition_id, true_label) tuples to evaluate against).
        method: Classical method name (same options as evaluate_classical_on_records).

    Returns:
        Dict with overall metrics and per-composition results, evaluated on
        the same notes the neural model was evaluated on.
    """
    with open(neural_predictions_path, 'r') as f:
        neural_data = json.load(f)

    # Build lookup: composition_id -> list of (neural_pred, true_label) tuples
    neural_lookup = {}
    for comp in neural_data['compositions']:
        neural_lookup[comp['composition_id']] = comp['predictions']

    # Build lookup: composition_id -> label record
    record_lookup = {rec.get('composition_id'): rec for rec in label_records}

    all_preds_trues = []
    per_comp_results = []

    for cid, neural_tuples in neural_lookup.items():
        if cid not in record_lookup:
            continue
        notes = record_lookup[cid].get('notes', [])
        if not notes:
            continue

        # Compute the classical global key from this composition's notes
        histogram = build_pitch_class_histogram(notes)
        if method == 'ensemble':
            pred_key, _, _ = detect_key_ensemble(histogram, weights=ENSEMBLE_WEIGHTS)
        elif method == 'ensemble_5':
            pred_key, _, _ = detect_key_ensemble(histogram, weights=ENSEMBLE_WEIGHTS_5)
        else:
            profile = PROFILES[method]
            pred_key, _ = detect_key_profile(histogram, profile)

        # Score the classical prediction against the EXACT neural-evaluated notes
        comp_mirex = 0.0
        comp_correct = 0
        comp_preds = []
        for (_neural_pred, true_key_idx) in neural_tuples:
            mirex = mirex_weighted_score(pred_key, true_key_idx)
            comp_mirex += mirex
            if pred_key == true_key_idx:
                comp_correct += 1
            comp_preds.append((pred_key, true_key_idx))
            all_preds_trues.append((pred_key, true_key_idx))

        n = len(comp_preds)
        if n > 0:
            per_comp_results.append({
                'composition_id': cid,
                'predicted_key': KEY_LABELS[pred_key],
                'mirex': comp_mirex / n,
                'accuracy': comp_correct / n,
                'n_predictions': n,
                'predictions': comp_preds,
            })

    total = len(all_preds_trues)
    overall_correct = sum(1 for p, t in all_preds_trues if p == t)
    overall_mirex = sum(mirex_weighted_score(p, t) for p, t in all_preds_trues)

    return {
        'method': method,
        'overall_mirex': overall_mirex / max(total, 1),
        'overall_accuracy': overall_correct / max(total, 1),
        'total_predictions': total,
        'n_compositions': len(per_comp_results),
        'per_composition': per_comp_results,
        'aligned_to': neural_predictions_path,
    }


def evaluate_classical_on_records(
    records: List[Dict],
    method: str = 'ensemble',
) -> Dict:
    """Evaluate a classical method on loaded records.

    For each composition, builds a global pitch-class histogram from all notes,
    detects key, and assigns that prediction to every note for MIREX scoring.

    Args:
        records: List of label JSON records with 'notes' arrays.
        method: One of:
            - 'ensemble' — legacy 3-profile ensemble (KK + TE + AS), weights from
              ENSEMBLE_WEIGHTS. Retained for Phase 1/2 reproducibility.
            - 'ensemble_5' — 5-profile ensemble (KK + TE + AS + BB + AE), weights
              from ENSEMBLE_WEIGHTS_5. New in v0.9.2-post.
            - 'krumhansl_kessler', 'temperley', 'albrecht_shanahan',
              'bellman_budge', 'aarden_essen' — single-profile correlation.

    Returns:
        Dict with overall metrics and per-composition results.
    """
    all_preds_trues = []
    per_comp_results = []

    for record in records:
        notes = record.get('notes', [])
        if not notes:
            continue

        # 2026-05-09 patch: fall back to 'id' (used by parse_bps_fh.py + parse_pop909.py)
        # in addition to composition_id / piece_id (used by ATEPP score_key_labels).
        comp_id = (record.get('composition_id')
                   or record.get('piece_id')
                   or record.get('id', 'unknown'))
        histogram = build_pitch_class_histogram(notes)

        if method == 'ensemble':
            pred_key, _, _ = detect_key_ensemble(histogram, weights=ENSEMBLE_WEIGHTS)
        elif method == 'ensemble_5':
            pred_key, _, _ = detect_key_ensemble(histogram, weights=ENSEMBLE_WEIGHTS_5)
        else:
            profile = PROFILES[method]
            pred_key, _ = detect_key_profile(histogram, profile)

        # Assign global prediction to every note and compute MIREX
        comp_mirex = 0.0
        comp_correct = 0
        comp_preds = []
        for note in notes:
            true_key_str = str(note.get('key', ''))
            try:
                true_key_idx = key_to_index(true_key_str)
            except (ValueError, KeyError):
                continue
            mirex = mirex_weighted_score(pred_key, true_key_idx)
            comp_mirex += mirex
            if pred_key == true_key_idx:
                comp_correct += 1
            comp_preds.append((pred_key, true_key_idx))
            all_preds_trues.append((pred_key, true_key_idx))

        n = len(comp_preds)
        if n > 0:
            per_comp_results.append({
                'composition_id': comp_id,
                'predicted_key': KEY_LABELS[pred_key],
                'mirex': comp_mirex / n,
                'accuracy': comp_correct / n,
                'n_predictions': n,
                'predictions': comp_preds,
            })

    total = len(all_preds_trues)
    overall_correct = sum(1 for p, t in all_preds_trues if p == t)
    overall_mirex = sum(mirex_weighted_score(p, t) for p, t in all_preds_trues)

    return {
        'method': method,
        'overall_mirex': overall_mirex / max(total, 1),
        'overall_accuracy': overall_correct / max(total, 1),
        'total_predictions': total,
        'n_compositions': len(per_comp_results),
        'per_composition': per_comp_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Evaluate classical key-finding baselines on ATEPP test set',
    )
    parser.add_argument('--splits', default=os.path.join(BASE_DIR, 'research_data', 'composition_splits.json'))
    parser.add_argument('--label-dir', default=os.path.join(BASE_DIR, 'research_data', 'score_key_labels'))
    parser.add_argument('--manifest', default=None)
    parser.add_argument('--label-dirs', default=None)
    parser.add_argument('--output', default=os.path.join(BASE_DIR, 'research_data', 'classical_baseline_eval.json'))
    parser.add_argument('--bootstrap-n', type=int, default=1000)
    parser.add_argument(
        '--align-to-predictions', default=None,
        help='Path to a neural prediction JSON file. When provided, the classical '
             'baseline is evaluated on EXACTLY the same (composition, note) tuples '
             'as the neural model — enabling fair classical-vs-neural comparison.',
    )
    args = parser.parse_args()

    # ---- Aligned evaluation mode (fair classical-vs-neural comparison) ----
    if args.align_to_predictions:
        print(f'ALIGNED EVALUATION MODE')
        print(f'Aligning to neural predictions: {args.align_to_predictions}\n')
        label_dirs = [d.strip() for d in args.label_dirs.split(',')] if args.label_dirs else [args.label_dir]
        records = load_records_for_predictions(args.align_to_predictions, label_dirs)
        print(f'Loaded {len(records)} compositions matching the neural prediction file')

        methods = [
            'krumhansl_kessler',
            'temperley',
            'albrecht_shanahan',
            'bellman_budge',
            'aarden_essen',
            'ensemble',
            'ensemble_5',
        ]
        results = {}

        print(f'\n{"Method":<25} {"MIREX":>8} {"Accuracy":>10} {"Predictions":>12}')
        print('-' * 58)
        for method in methods:
            result = evaluate_classical_aligned_to_neural(
                records, args.align_to_predictions, method,
            )
            results[method] = result
            if args.bootstrap_n > 0:
                ci = bootstrap_mirex_ci(result['per_composition'], n_bootstrap=args.bootstrap_n)
                result['bootstrap_ci'] = ci
                ci_str = f' ({ci["mirex_ci_lower"]:.3f}–{ci["mirex_ci_upper"]:.3f})'
            else:
                ci_str = ''
            print(f'{method:<25} {result["overall_mirex"]:>8.4f}{ci_str} {result["overall_accuracy"]:>10.4f} {result["total_predictions"]:>12}')

        # Save aligned results
        output = {
            'mode': 'aligned_to_neural',
            'aligned_to': args.align_to_predictions,
            'methods': {},
        }
        for method, result in results.items():
            output['methods'][method] = {
                'overall_mirex': result['overall_mirex'],
                'overall_accuracy': result['overall_accuracy'],
                'total_predictions': result['total_predictions'],
                'n_compositions': result['n_compositions'],
                'bootstrap_ci': result.get('bootstrap_ci'),
            }
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        with open(args.output, 'w') as f:
            json.dump(output, f, indent=2)
        print(f'\nSaved aligned results to {args.output}')
        return

    # ---- Standard evaluation mode (legacy: own test set) ----
    if args.manifest:
        label_dirs = [d.strip() for d in args.label_dirs.split(',')] if args.label_dirs else [args.label_dir]
        records = load_test_records_from_manifest(args.manifest, label_dirs)
    else:
        records = load_test_records_from_splits(args.splits, args.label_dir)

    print(f'Loaded {len(records)} test compositions')

    # All classical methods evaluated. The 'ensemble' (3-profile, legacy) is
    # kept for Phase 1/Phase 2 backward compatibility. 'ensemble_5' is the new
    # 5-profile ensemble including Bellman-Budge and Aarden-Essen from Nápoles 2019.
    methods = [
        'krumhansl_kessler',
        'temperley',
        'albrecht_shanahan',
        'bellman_budge',
        'aarden_essen',
        'ensemble',      # legacy 3-profile (KK + TE + AS)
        'ensemble_5',    # new 5-profile (KK + TE + AS + BB + AE)
    ]
    results = {}

    print(f'\n{"Method":<25} {"MIREX":>8} {"Accuracy":>10} {"Predictions":>12}')
    print('-' * 58)

    for method in methods:
        result = evaluate_classical_on_records(records, method)
        results[method] = result

        # Bootstrap CI
        if args.bootstrap_n > 0:
            ci = bootstrap_mirex_ci(result['per_composition'], n_bootstrap=args.bootstrap_n)
            result['bootstrap_ci'] = ci
            ci_str = f' ({ci["mirex_ci_lower"]:.3f}–{ci["mirex_ci_upper"]:.3f})'
        else:
            ci_str = ''

        print(f'{method:<25} {result["overall_mirex"]:>8.4f}{ci_str} {result["overall_accuracy"]:>10.4f} {result["total_predictions"]:>12}')

    # Comparison summary
    print(f'\n--- Comparison Table (for thesis) ---')
    print(f'{"Method":<25} {"MIREX (95% CI)":<25} {"Accuracy":>10}')
    print('-' * 63)
    for method in methods:
        r = results[method]
        if 'bootstrap_ci' in r:
            ci = r['bootstrap_ci']
            ci_str = f'{r["overall_mirex"]:.3f} ({ci["mirex_ci_lower"]:.3f}–{ci["mirex_ci_upper"]:.3f})'
        else:
            ci_str = f'{r["overall_mirex"]:.3f}'
        print(f'{method:<25} {ci_str:<25} {r["overall_accuracy"]:>10.4f}')

    # Save results (strip per-note predictions for manageable file size)
    output = {}
    for method, result in results.items():
        output[method] = {
            'overall_mirex': result['overall_mirex'],
            'overall_accuracy': result['overall_accuracy'],
            'total_predictions': result['total_predictions'],
            'n_compositions': result['n_compositions'],
            'bootstrap_ci': result.get('bootstrap_ci'),
            'per_composition': [
                {k: v for k, v in c.items() if k != 'predictions'}
                for c in result['per_composition']
            ],
        }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    print(f'\nSaved to {args.output}')


if __name__ == '__main__':
    main()
