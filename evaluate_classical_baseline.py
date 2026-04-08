#!/usr/bin/env python3
"""
Evaluate classical key-finding algorithms on the ATEPP-319 test set.

Implements Krumhansl-Kessler (1982), Temperley (1999), and Albrecht-Shanahan (2013)
profile-correlation methods. Reports MIREX weighted scores on the same test set
used for neural model evaluation, enabling direct comparison.

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

# --- Key Profiles (ported from js/key-detection.js) ---

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

ENSEMBLE_WEIGHTS = {
    'albrecht_shanahan': 0.45,
    'temperley': 0.35,
    'krumhansl_kessler': 0.20,
}

PROFILES = {
    'albrecht_shanahan': ALBRECHT_SHANAHAN,
    'temperley': TEMPERLEY,
    'krumhansl_kessler': KRUMHANSL_KESSLER,
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
) -> Tuple[int, float, Dict[str, Tuple[int, float]]]:
    """Detect key using weighted ensemble of all three profiles.

    Returns (ensemble_key, ensemble_score, per_profile_results).
    """
    scores = np.zeros(24)
    per_profile = {}
    for name, profile in PROFILES.items():
        weight = ENSEMBLE_WEIGHTS[name]
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


def evaluate_classical_on_records(
    records: List[Dict],
    method: str = 'ensemble',
) -> Dict:
    """Evaluate a classical method on loaded records.

    For each composition, builds a global pitch-class histogram from all notes,
    detects key, and assigns that prediction to every note for MIREX scoring.

    Args:
        records: List of label JSON records with 'notes' arrays.
        method: 'ensemble', 'albrecht_shanahan', 'temperley', or 'krumhansl_kessler'.

    Returns:
        Dict with overall metrics and per-composition results.
    """
    all_preds_trues = []
    per_comp_results = []

    for record in records:
        notes = record.get('notes', [])
        if not notes:
            continue

        comp_id = record.get('composition_id', record.get('piece_id', 'unknown'))
        histogram = build_pitch_class_histogram(notes)

        if method == 'ensemble':
            pred_key, _, _ = detect_key_ensemble(histogram)
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
    args = parser.parse_args()

    if args.manifest:
        label_dirs = [d.strip() for d in args.label_dirs.split(',')] if args.label_dirs else [args.label_dir]
        records = load_test_records_from_manifest(args.manifest, label_dirs)
    else:
        records = load_test_records_from_splits(args.splits, args.label_dir)

    print(f'Loaded {len(records)} test compositions')

    methods = ['krumhansl_kessler', 'temperley', 'albrecht_shanahan', 'ensemble']
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
