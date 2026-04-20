"""Phase B paired cluster bootstrap on per-composition MIREX.

Consumes ensemble_eval.json files (which carry per-composition neural_mirex +
classical_mirex), averages across the 3 Phase B seeds per cell, and runs a
paired cluster bootstrap at the composition level to produce:
  - mean Δ MIREX (cell_a − cell_b)
  - 95 percent CI (percentile)
  - two-sided p-value

Usage:
    python phaseB_paired_bootstrap.py \\
        --track-dir /path/to/phase_b_track1_2026-04-17 \\
        --output    phaseB_paired_bootstrap_results.json \\
        --n-boot    10000 \\
        --seed      20260418

The classical baseline is constant across seeds (same classical_mirex
per composition regardless of which neural checkpoint produced the file),
so the 3-seed mean for classical is just classical_mirex of any one seed.

Reference: Efron & Tibshirani (1993), section on cluster bootstrap.
"""

from __future__ import annotations

import argparse
import json
import os
import random
from typing import Dict, List, Tuple

import numpy as np

SEEDS = (20260309, 20260310, 20260311)


def load_per_composition_array(track_dir: str, cell_id: str) -> Dict[str, np.ndarray]:
    """Load per-composition neural_mirex across 3 seeds, return mean vector
    (41-long). Also returns the classical vector (seed-invariant) and composition ids.

    Returns {'neural': array, 'classical': array, 'ids': list}.
    """
    seed_vectors = []
    classical_vec = None
    ids = None
    for seed in SEEDS:
        path = os.path.join(track_dir, f'{cell_id}_seed{seed}_ensemble_eval.json')
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with open(path) as f:
            data = json.load(f)
        pc = data['per_composition']
        pc_sorted = sorted(pc, key=lambda r: int(r['composition_id']))
        seed_vectors.append(np.array([r['neural_mirex'] for r in pc_sorted]))
        if classical_vec is None:
            classical_vec = np.array([r['classical_mirex'] for r in pc_sorted])
            ids = [int(r['composition_id']) for r in pc_sorted]
    neural_mean = np.mean(seed_vectors, axis=0)
    return {'neural': neural_mean, 'classical': classical_vec, 'ids': ids}


def paired_cluster_bootstrap(
    vec_a: np.ndarray,
    vec_b: np.ndarray,
    n_boot: int,
    seed: int,
) -> Dict[str, float]:
    """Paired cluster bootstrap at composition level.

    Returns dict with mean_delta, ci_low, ci_high, p_two_sided, n_compositions.
    """
    assert vec_a.shape == vec_b.shape, 'vectors must match composition-wise'
    rng = np.random.default_rng(seed)
    n = vec_a.shape[0]
    deltas = vec_a - vec_b
    observed = float(np.mean(deltas))

    boot_means = np.empty(n_boot, dtype=np.float64)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_means[i] = float(np.mean(deltas[idx]))

    ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
    # Two-sided p-value: proportion of bootstrap resamples where the
    # observed direction is contradicted. Standard test-of-zero:
    #   p = 2 * min(Pr[boot <= 0], Pr[boot >= 0])
    p_le = float(np.mean(boot_means <= 0.0))
    p_ge = float(np.mean(boot_means >= 0.0))
    p_two_sided = 2.0 * min(p_le, p_ge)
    p_two_sided = min(1.0, p_two_sided)

    return {
        'mean_delta': observed,
        'ci_low': float(ci_low),
        'ci_high': float(ci_high),
        'p_two_sided': p_two_sided,
        'n_compositions': int(n),
        'n_boot': int(n_boot),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--track-dir', required=True,
                        help='Directory of ensemble_eval.json files')
    parser.add_argument('--output', required=True)
    parser.add_argument('--n-boot', type=int, default=10000)
    parser.add_argument('--seed', type=int, default=20260418)
    args = parser.parse_args()

    # All Phase B cells
    cells = ('B1','B2','B3','B4','B5','B6','B7','B8','B9','B10','B11','B12')
    vectors = {c: load_per_composition_array(args.track_dir, c) for c in cells}
    classical_vec = vectors['B1']['classical']   # seed-invariant
    ids = vectors['B1']['ids']

    # Pre-registered comparisons of interest
    contrasts = [
        # Pipeline integrity (should be ~0)
        ('B7', 'B1', 'B1==B7 mirror integrity check'),
        ('B11', 'B9', 'B9==B11 mirror integrity check'),
        # Sqrt vs none vs ens on gru h=96
        ('B2', 'B1', 'weight_mode=none vs sqrt (gru h=96)'),
        ('B9', 'B1', 'weight_mode=ens vs sqrt (gru h=96)'),
        ('B9', 'B2', 'weight_mode=ens vs none (gru h=96)'),
        # Focal loss effect
        ('B8', 'B1', 'sqrt+focal vs sqrt (null expected)'),
        ('B10', 'B9', 'ens+focal vs ens'),
        # h=192 effect
        ('B3', 'B1', 'h=192 vs h=96 (both sqrt)'),
        ('B4', 'B2', 'h=192 vs h=96 (both none)'),
        # Transformer
        ('B6', 'B1', 'transformer none vs gru 96 sqrt'),
        # PCP ablation (B12 vs B11)
        ('B12', 'B11', 'PCP feature vs base'),
        # Against classical baseline
        ('B9', 'classical', 'B9 (best) vs classical baseline'),
        ('B10', 'classical', 'B10 (best stability) vs classical baseline'),
        ('B2', 'classical', 'B2 vs classical baseline'),
    ]

    results = []
    print(f'{"contrast":<38} {"mean Δ":>8} {"95% CI":>18} {"p":>10}  note')
    print('-' * 110)
    for a, b, note in contrasts:
        vec_a = vectors[a]['neural']
        vec_b = classical_vec if b == 'classical' else vectors[b]['neural']
        stats = paired_cluster_bootstrap(vec_a, vec_b, args.n_boot, args.seed)
        sig = '***' if stats['p_two_sided'] < 0.001 else \
              '**'  if stats['p_two_sided'] < 0.01  else \
              '*'   if stats['p_two_sided'] < 0.05  else 'ns'
        ci = f"[{stats['ci_low']:+.4f}, {stats['ci_high']:+.4f}]"
        print(f'{a} vs {b:<10} {stats["mean_delta"]:>+8.4f} {ci:>18} '
              f'{stats["p_two_sided"]:>8.4f} {sig:>3}  {note}')
        results.append({'cell_a': a, 'cell_b': b, 'note': note, **stats})

    out = {
        'config': {
            'n_boot': args.n_boot,
            'seed': args.seed,
            'n_seeds_averaged_per_cell': 3,
            'n_compositions': len(ids),
            'composition_ids': ids,
        },
        'classical_baseline_mean_mirex': float(np.mean(classical_vec)),
        'contrasts': results,
    }
    with open(args.output, 'w') as f:
        json.dump(out, f, indent=2)
    print(f'\nSaved {len(results)} contrasts to {args.output}')


if __name__ == '__main__':
    main()
