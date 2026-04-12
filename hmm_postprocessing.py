#!/usr/bin/env python3
"""
HMM post-processing for neural key detection.

Uses a 24-state Hidden Markov Model where:
- Emission probabilities come from the neural model's softmax output per note
- Transition probabilities encode circle-of-fifths proximity, relative/parallel
  key relationships, and general music-theoretic key change patterns
- Viterbi decoding produces the most likely key sequence

This approach combines neural pattern recognition with structural music theory
constraints that the neural model may not have fully learned.

Usage:
    python hmm_postprocessing.py --predictions research_data/gru_predictions.json

    # Grid search with proper train/val/test split (recommended):
    python hmm_postprocessing.py --predictions research_data/test_predictions.json \
        --val-predictions research_data/val_predictions.json --grid-search
"""

from __future__ import annotations

import argparse
import json
import math
import os
from typing import Dict, List, Tuple

import numpy as np

from harmonic_context_model import KEY_LABELS
from evaluate_harmonic_context_model import mirex_weighted_score, bootstrap_mirex_ci

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def circle_of_fifths_distance(key_a: int, key_b: int) -> int:
    """Minimum distance on circle of fifths between two pitch classes (0-11)."""
    pc_a = key_a % 12
    pc_b = key_b % 12
    # Circle of fifths: each step is +7 semitones mod 12
    forward = 0
    current = pc_a
    while current != pc_b and forward < 12:
        current = (current + 7) % 12
        forward += 1
    return min(forward, 12 - forward)


def build_transition_matrix(
    self_transition: float = 0.85,
    fifth_weight: float = 0.06,
    relative_weight: float = 0.04,
    parallel_weight: float = 0.03,
    tau: float = 2.0,
) -> np.ndarray:
    """Build a 24x24 transition matrix encoding music-theoretic key change patterns.

    Parameters:
        self_transition: Probability of staying in same key (high = more stable)
        fifth_weight: Base weight for fifth-related keys (I -> V, I -> IV)
        relative_weight: Weight for relative major/minor (Cm -> Eb, C -> Am)
        parallel_weight: Weight for parallel major/minor (C -> Cm)
        tau: Temperature for circle-of-fifths distance decay

    Returns:
        24x24 row-stochastic transition matrix.
    """
    trans = np.zeros((24, 24))

    for i in range(24):
        i_pc = i % 12
        i_minor = i >= 12

        for j in range(24):
            j_pc = j % 12
            j_minor = j >= 12

            if i == j:
                trans[i, j] = self_transition
                continue

            cof_dist = circle_of_fifths_distance(i_pc, j_pc)

            # Same mode, fifth relation (I->V, I->IV)
            if i_minor == j_minor and cof_dist <= 1:
                trans[i, j] = fifth_weight

            # Relative key: major -> relative minor (3 semitones up)
            # e.g., C major (0) -> A minor (21)
            elif not i_minor and j_minor and (j_pc - i_pc) % 12 == 9:
                trans[i, j] = relative_weight
            elif i_minor and not j_minor and (j_pc - i_pc) % 12 == 3:
                trans[i, j] = relative_weight

            # Parallel key: same root, different mode (C -> Cm)
            elif i_pc == j_pc and i_minor != j_minor:
                trans[i, j] = parallel_weight

            else:
                # General distance-based decay
                trans[i, j] = 0.001 * math.exp(-cof_dist / tau)

        # Normalize row to sum to 1
        row_sum = trans[i].sum()
        if row_sum > 0:
            trans[i] /= row_sum

    return trans


def viterbi_decode(
    emissions: np.ndarray,
    transition: np.ndarray,
    prior: np.ndarray | None = None,
) -> Tuple[List[int], float]:
    """Viterbi decoding for sequence of emissions.

    Args:
        emissions: (T, 24) log-probabilities or probabilities per timestep
        transition: (24, 24) transition matrix (row-stochastic)
        prior: (24,) initial state distribution (uniform if None)

    Returns:
        (best_path, log_likelihood)
    """
    T, K = emissions.shape
    assert K == 24

    if prior is None:
        prior = np.ones(K) / K

    # Work in log space
    log_trans = np.log(transition + 1e-10)
    log_prior = np.log(prior + 1e-10)
    log_emit = np.log(emissions + 1e-10)

    # Viterbi tables
    V = np.zeros((T, K))
    backptr = np.zeros((T, K), dtype=int)

    V[0] = log_prior + log_emit[0]

    for t in range(1, T):
        for j in range(K):
            candidates = V[t - 1] + log_trans[:, j]
            backptr[t, j] = int(np.argmax(candidates))
            V[t, j] = candidates[backptr[t, j]] + log_emit[t, j]

    # Backtrace
    path = [0] * T
    path[-1] = int(np.argmax(V[-1]))
    log_likelihood = float(V[-1, path[-1]])

    for t in range(T - 2, -1, -1):
        path[t] = backptr[t + 1, path[t + 1]]

    return path, log_likelihood


def postprocess_predictions(
    predictions: List[Tuple[int, int]],
    softmax_outputs: List[List[float]] | None = None,
    self_transition: float = 0.85,
    tau: float = 2.0,
) -> List[Tuple[int, int]]:
    """Apply HMM post-processing to neural predictions.

    If softmax_outputs are available, use them as emission probabilities.
    Otherwise, create pseudo-emissions from hard predictions with smoothing.

    Args:
        predictions: List of (predicted_key, true_key) tuples
        softmax_outputs: Optional (T, 24) softmax probabilities from neural model
        self_transition: HMM self-transition probability
        tau: Circle-of-fifths distance temperature

    Returns:
        New list of (hmm_predicted_key, true_key) tuples
    """
    T = len(predictions)
    if T == 0:
        return []

    transition = build_transition_matrix(self_transition=self_transition, tau=tau)

    if softmax_outputs is not None:
        emissions = np.array(softmax_outputs)
    else:
        # Create pseudo-emissions: put 0.7 on predicted class, spread 0.3 uniformly
        emissions = np.full((T, 24), 0.3 / 23)
        for t, (pred, _) in enumerate(predictions):
            emissions[t, pred] = 0.7

    hmm_path, _ = viterbi_decode(emissions, transition)
    return [(hmm_path[t], predictions[t][1]) for t in range(T)]


def evaluate_with_hmm(
    prediction_file: str,
    self_transition: float = 0.85,
    tau: float = 2.0,
) -> Dict:
    """Load saved predictions, apply HMM post-processing, and evaluate."""
    with open(prediction_file, 'r') as f:
        data = json.load(f)

    original_mirex_sum = 0.0
    hmm_mirex_sum = 0.0
    original_correct = 0
    hmm_correct = 0
    total = 0
    per_comp = []

    for comp in data['compositions']:
        preds = comp['predictions']  # list of [pred, true]
        if not preds:
            continue

        # Use softmax emissions if available, otherwise pseudo-emissions
        softmax = comp.get('softmax', None)
        hmm_preds = postprocess_predictions(
            preds, softmax_outputs=softmax,
            self_transition=self_transition, tau=tau,
        )

        comp_orig_mirex = 0.0
        comp_hmm_mirex = 0.0
        for (orig_p, t), (hmm_p, _) in zip(preds, hmm_preds):
            orig_m = mirex_weighted_score(orig_p, t)
            hmm_m = mirex_weighted_score(hmm_p, t)
            comp_orig_mirex += orig_m
            comp_hmm_mirex += hmm_m
            original_mirex_sum += orig_m
            hmm_mirex_sum += hmm_m
            if orig_p == t:
                original_correct += 1
            if hmm_p == t:
                hmm_correct += 1
            total += 1

        n = len(preds)
        per_comp.append({
            'composition_id': comp['composition_id'],
            'mirex': comp_hmm_mirex / n,
            'accuracy': sum(1 for hp, _ in hmm_preds if hp == preds[hmm_preds.index((hp, _))][1]) / n if n > 0 else 0,
            'n_predictions': n,
            'original_mirex': comp_orig_mirex / n,
        })

    return {
        'original_mirex': original_mirex_sum / max(total, 1),
        'hmm_mirex': hmm_mirex_sum / max(total, 1),
        'original_accuracy': original_correct / max(total, 1),
        'hmm_accuracy': hmm_correct / max(total, 1),
        'mirex_improvement': (hmm_mirex_sum - original_mirex_sum) / max(total, 1),
        'total_predictions': total,
        'self_transition': self_transition,
        'tau': tau,
        'per_composition': per_comp,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='HMM post-processing for key detection')
    parser.add_argument('--predictions', required=True,
                        help='Path to saved predictions JSON (from evaluate --save-predictions)')
    parser.add_argument('--self-transition', type=float, default=0.85)
    parser.add_argument('--tau', type=float, default=2.0)
    parser.add_argument('--val-predictions', default=None,
                        help='Path to VALIDATION predictions JSON for grid search tuning '
                             '(prevents data leakage from tuning on test set)')
    parser.add_argument('--grid-search', action='store_true',
                        help='Search over self_transition and tau values')
    parser.add_argument('--output', default=os.path.join(BASE_DIR, 'research_data', 'hmm_postprocessing_eval.json'))
    args = parser.parse_args()

    if args.grid_search:
        # Determine which file to use for hyperparameter tuning
        if args.val_predictions:
            tuning_file = args.val_predictions
            print('Grid search over HMM hyperparameters (tuning on VALIDATION set):')
        else:
            tuning_file = args.predictions
            print('WARNING: --val-predictions not provided. Grid search is tuning on '
                  'the TEST set, which constitutes data leakage. Provide '
                  '--val-predictions for proper evaluation.')
            print('Grid search over HMM hyperparameters (tuning on TEST set):')

        print(f'{"self_trans":>12} {"tau":>6} {"Orig MIREX":>12} {"HMM MIREX":>12} {"Delta":>8}')
        print('-' * 55)

        best_val_result = None
        best_delta = -1.0
        best_st = None
        best_tau = None

        for st in [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
            for tau in [1.0, 1.5, 2.0, 3.0, 5.0]:
                val_result = evaluate_with_hmm(tuning_file, self_transition=st, tau=tau)
                delta = val_result['mirex_improvement']
                print(f'{st:>12.2f} {tau:>6.1f} {val_result["original_mirex"]:>12.4f} '
                      f'{val_result["hmm_mirex"]:>12.4f} {delta:>+8.4f}')
                if delta > best_delta:
                    best_delta = delta
                    best_val_result = val_result
                    best_st = st
                    best_tau = tau

        print(f'\nBest params (on {"validation" if args.val_predictions else "test"}): '
              f'self_transition={best_st}, tau={best_tau}, delta={best_delta:+.4f}')

        if args.val_predictions:
            # Evaluate ONCE on test set with the best parameters from validation
            print(f'\nEvaluating on TEST set with fixed params '
                  f'(self_transition={best_st}, tau={best_tau}):')
            result = evaluate_with_hmm(
                args.predictions, self_transition=best_st, tau=best_tau,
            )
            print(f'  Validation MIREX: {best_val_result["hmm_mirex"]:.4f} '
                  f'(delta={best_delta:+.4f})')
            print(f'  Test MIREX:       {result["hmm_mirex"]:.4f} '
                  f'(delta={result["mirex_improvement"]:+.4f})')
        else:
            result = best_val_result
    else:
        result = evaluate_with_hmm(
            args.predictions,
            self_transition=args.self_transition,
            tau=args.tau,
        )
        print(f'Original MIREX: {result["original_mirex"]:.4f}')
        print(f'HMM MIREX:      {result["hmm_mirex"]:.4f}')
        print(f'Improvement:    {result["mirex_improvement"]:+.4f}')

    # Strip per-note predictions for output
    output = {k: v for k, v in result.items() if k != 'per_composition'}
    output['per_composition'] = [
        {k: v for k, v in c.items()}
        for c in result['per_composition']
    ]

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)
    print(f'Saved to {args.output}')


if __name__ == '__main__':
    main()
