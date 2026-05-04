#!/usr/bin/env python3
"""
Phase I formal paired cluster-bootstrap re-runs at full n = 5.

Computes the five pre-registered contrasts (H1, H2, H3, H4a, H4b) using
the composition-level paired cluster bootstrap (B = 10 000) defined in
PHASE1_PREREGISTRATION_2026-04-25.md §3.1.

Test statistic per the pre-registration:
  1. For each piece p, compute per-cell mean MIREX (mean across the 5
     seeds in the cell).
  2. Compute Δ_p = cell_a(p) − cell_b(p).
  3. Resample the 41 piece-level Δ values 10 000 times with replacement.
  4. Two-sided p = 2 × min(P(Δ_boot > 0 | H0), P(Δ_boot < 0 | H0)).

Bonferroni α = 0.01 for the 5-test family-wise H1, H2, H3, H4a, H4b.

This is the formal Mac-side closing computation flagged in the
2026-04-30 audit and in Chapter 8 §8.5.1 (Tier-0 future-work item 1).

Author: Rui Su, 2026-05-01.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

# ─────────────────────────────────────────────────────────────────────────
# Configuration

ATEPP_41 = {
    7, 60, 77, 120, 122, 215, 515, 541, 546, 547, 550, 602, 610, 650, 670,
    672, 728, 876, 907, 910, 1076, 1128, 1132, 1144, 1147, 1164, 1190, 1200,
    1212, 1215, 1227, 1240, 1248, 1256, 1257, 1259, 1263, 1495, 1512, 1518,
    1542,
}

PHASE_I_DIR = Path('/tmp/phase1_results_2026-05-01/phase1_beat_classical_2026-04-25')
B9_DIR = Path('/tmp/b9_restored/B9_extra_seeds_a100_2026-04-28')
CLASSICAL_FILE = Path(
    '/Users/ruisu/Desktop/ruisuphd/prototype090326AI-functions/research_data/'
    'phaseA_track1_results/ensemble_eval_seed20260309.json'
)

PHASE_I_SEEDS = [
    ('20260425a', 3886265411),
    ('20260425b', 3128166492),
    ('20260425c', 1252837625),
    ('20260425d', 3629727882),
    ('20260425e', 440397851),
]
B9_SEEDS = ['20260309', '20260310', '20260311', '20260312', '20260313']

N_BOOT = 10_000
SEED_BOOT = 20260501  # frozen seed for the bootstrap — change requires deviation log entry
ALPHA_BONFERRONI = 0.01  # 0.05 / 5 family-wise tests


# ─────────────────────────────────────────────────────────────────────────
# Per-piece MIREX vectors

def load_phase1_per_piece(variant: str) -> Dict[int, np.ndarray]:
    """Return {composition_id: np.array of 5 per-seed MIREX values}."""
    per_piece: Dict[int, list] = {cid: [] for cid in ATEPP_41}
    for label, seed_int in PHASE_I_SEEDS:
        path = PHASE_I_DIR / f'{variant}_seed{label}.json'
        if not path.exists():
            raise FileNotFoundError(f'Phase I file missing: {path}')
        d = json.load(open(path))
        for c in d['per_composition']:
            cid = int(c['composition_id'])
            if cid in ATEPP_41:
                per_piece[cid].append(float(c['mirex']))
    out = {}
    for cid, vals in per_piece.items():
        if len(vals) != 5:
            raise ValueError(f'{variant}: composition {cid} has {len(vals)} seed values, expected 5')
        out[cid] = np.array(vals)
    return out


def load_b9_per_piece() -> Dict[int, np.ndarray]:
    per_piece: Dict[int, list] = {cid: [] for cid in ATEPP_41}
    for s in B9_SEEDS:
        path = B9_DIR / f'B9_seed{s}_predictions.json'
        if not path.exists():
            raise FileNotFoundError(f'B9 file missing: {path}')
        d = json.load(open(path))
        for c in d['compositions']:
            cid = int(c['composition_id'])
            if cid in ATEPP_41:
                per_piece[cid].append(float(c['mirex']))
    out = {}
    for cid, vals in per_piece.items():
        if len(vals) != 5:
            raise ValueError(f'B9: composition {cid} has {len(vals)} seed values, expected 5')
        out[cid] = np.array(vals)
    return out


def load_classical_per_piece() -> Dict[int, float]:
    d = json.load(open(CLASSICAL_FILE))
    out = {}
    for c in d['per_composition']:
        cid = int(c['composition_id'])
        if cid in ATEPP_41:
            out[cid] = float(c['classical_mirex'])
    if len(out) != 41:
        raise ValueError(f'Classical: {len(out)}/41 compositions matched')
    return out


# ─────────────────────────────────────────────────────────────────────────
# Bootstrap

def per_piece_cell_mean(per_piece: Dict[int, np.ndarray], composition_ids: List[int]) -> np.ndarray:
    """Return [mean MIREX over seeds] for each composition, in order."""
    return np.array([per_piece[cid].mean() for cid in composition_ids])


def cluster_bootstrap_two_sided_p(
    delta_per_piece: np.ndarray, n_boot: int, rng_seed: int,
) -> Dict[str, float]:
    """
    Composition-level cluster bootstrap.

    delta_per_piece: shape (n_pieces,) — per-piece Δ = cell_a − cell_b
                     where each cell is the per-piece mean over seeds.
    """
    rng = np.random.default_rng(rng_seed)
    n = len(delta_per_piece)
    boots = np.empty(n_boot, dtype=np.float64)
    observed_mean = float(delta_per_piece.mean())
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[b] = delta_per_piece[idx].mean()
    # 95 % bootstrap percentile CI
    ci_low = float(np.percentile(boots, 2.5))
    ci_high = float(np.percentile(boots, 97.5))
    # Two-sided p: H_0 is Δ = 0; we test under the null by recentering.
    # Pre-registration §3.1 specifies "twice the proportion of bootstrap
    # resamples whose Δ has the OPPOSITE sign of the observed Δ".
    if observed_mean > 0:
        opposite_count = int((boots <= 0).sum())
    elif observed_mean < 0:
        opposite_count = int((boots >= 0).sum())
    else:
        opposite_count = n_boot // 2
    p_two_sided = 2.0 * opposite_count / n_boot
    p_two_sided = min(p_two_sided, 1.0)
    return {
        'observed_mean_delta': observed_mean,
        'ci_low_95': ci_low,
        'ci_high_95': ci_high,
        'p_two_sided': p_two_sided,
        'n_boot': n_boot,
        'n_pieces': n,
    }


# ─────────────────────────────────────────────────────────────────────────
# Main

def main():
    print('=' * 90)
    print('Phase I formal paired cluster-bootstrap re-runs (n = 5 vs n = 5, B = 10 000)')
    print(f'Pre-registration: PHASE1_PREREGISTRATION_2026-04-25.md §3.1')
    print(f'Bonferroni α = {ALPHA_BONFERRONI} for the 5-test family-wise H1, H2, H3, H4a, H4b')
    print(f'Bootstrap RNG seed: {SEED_BOOT} (frozen)')
    print('=' * 90)

    # Load per-piece per-cell vectors
    print('\nLoading per-piece per-cell MIREX vectors...')
    cells = {
        'B9': load_b9_per_piece(),
        'BASELINE': load_phase1_per_piece('BASELINE'),
        'T6': load_phase1_per_piece('T6'),
        'T6_T1': load_phase1_per_piece('T6_T1'),
        'T6_T1_T2': load_phase1_per_piece('T6_T1_T2'),
    }
    classical = load_classical_per_piece()
    composition_ids = sorted(ATEPP_41)

    # Per-cell FW MIREX sanity check
    print('\nPer-cell sanity: FW MIREX (expected to match chapter headline)')
    # For per-cell FW: weight per-piece per-cell-mean by piece n_predictions
    # Load n_predictions for each piece from any Phase I file
    n_pred_by_piece = {}
    sample_d = json.load(open(PHASE_I_DIR / 'BASELINE_seed20260425a.json'))
    for c in sample_d['per_composition']:
        n_pred_by_piece[int(c['composition_id'])] = int(c['n_predictions'])

    for cell_name, per_piece in cells.items():
        means = per_piece_cell_mean(per_piece, composition_ids)
        ns = np.array([n_pred_by_piece[cid] for cid in composition_ids])
        fw = float(np.sum(means * ns) / ns.sum())
        ce = float(means.mean())
        print(f'  {cell_name:<10}: cell-mean FW = {fw:.4f}, CE = {ce:.4f}')
    # Classical
    classical_vec = np.array([classical[cid] for cid in composition_ids])
    ns = np.array([n_pred_by_piece[cid] for cid in composition_ids])
    fw_c = float(np.sum(classical_vec * ns) / ns.sum())
    ce_c = float(classical_vec.mean())
    print(f'  classical : FW = {fw_c:.4f}, CE = {ce_c:.4f}')

    # ---- Run the five pre-registered contrasts ----
    print('\n' + '=' * 90)
    print('Pre-registered family-wise contrasts (B = 10 000):')
    print('=' * 90)

    # Use cell-mean (mean over seeds per piece) for both sides; this is the
    # pre-registered statistic from §3.1.
    results = {}
    contrasts = [
        ('H1', 'T6_T1_T2', 'B9', 'pre-registered primary outcome (full stack vs B9)'),
        ('H2', 'BASELINE', 'B9', 'pre-registered (training-pool only vs B9; provisional p=0.0006 at n=3 vs 2)'),
        ('H3', 'T6', 'BASELINE', 'pre-registered (transposition aug. vs BASELINE)'),
        ('H4a', 'T6_T1', 'T6', 'pre-registered (global PCP vs T6)'),
        ('H4b', 'T6_T1_T2', 'T6_T1', 'pre-registered (chord head vs T6_T1)'),
    ]
    for hyp_id, cell_a, cell_b, note in contrasts:
        a_mean = per_piece_cell_mean(cells[cell_a], composition_ids)
        b_mean = per_piece_cell_mean(cells[cell_b], composition_ids)
        delta = a_mean - b_mean
        rng_seed_for_test = SEED_BOOT + hash(hyp_id) % 1000
        out = cluster_bootstrap_two_sided_p(delta, N_BOOT, rng_seed_for_test)
        # Effect size: mean Δ / σ(Δ_per_piece)
        sd = float(delta.std(ddof=1))
        d_z = out['observed_mean_delta'] / sd if sd > 0 else float('nan')
        clears_bonferroni = out['p_two_sided'] < ALPHA_BONFERRONI
        results[hyp_id] = {
            'cell_a': cell_a,
            'cell_b': cell_b,
            'note': note,
            **out,
            'sd_delta_per_piece': sd,
            'cohen_d_z': d_z,
            'clears_bonferroni_alpha_001': clears_bonferroni,
        }
        sign_str = '+' if out['observed_mean_delta'] >= 0 else '−'
        print(f"\n{hyp_id} ({cell_a} − {cell_b}):  {note}")
        print(f"  Observed Δ_CE = {out['observed_mean_delta']:+.4f}  (per-piece σ(Δ) = {sd:.4f}, d_z = {d_z:+.3f})")
        print(f"  95 % CI [{out['ci_low_95']:+.4f}, {out['ci_high_95']:+.4f}]")
        print(f"  Two-sided p = {out['p_two_sided']:.4f}  (Bonferroni α = {ALPHA_BONFERRONI})")
        print(f"  Bonferroni-significant: {'YES' if clears_bonferroni else 'NO'}")

    # ---- Auxiliary contrasts (not in the family-wise correction) ----
    print('\n' + '=' * 90)
    print('Auxiliary contrasts (not in family-wise α correction):')
    print('=' * 90)
    aux = [
        ('AUX1', 'T6', 'classical', 'T6 vs classical 3-profile (auxiliary; H5-relevant)'),
        ('AUX2', 'T6_T1', 'classical', 'T6_T1 vs classical 3-profile (auxiliary; best-evaluated)'),
        ('AUX3', 'T6_T1_T2', 'classical', 'T6_T1_T2 vs classical 3-profile (auxiliary; pre-registered H5 cell)'),
    ]
    for hyp_id, cell_a, cell_b, note in aux:
        a_mean = per_piece_cell_mean(cells[cell_a], composition_ids)
        b_vec = classical_vec if cell_b == 'classical' else per_piece_cell_mean(cells[cell_b], composition_ids)
        delta = a_mean - b_vec
        rng_seed_for_test = SEED_BOOT + hash(hyp_id) % 1000
        out = cluster_bootstrap_two_sided_p(delta, N_BOOT, rng_seed_for_test)
        sd = float(delta.std(ddof=1))
        d_z = out['observed_mean_delta'] / sd if sd > 0 else float('nan')
        results[hyp_id] = {
            'cell_a': cell_a,
            'cell_b': cell_b,
            'note': note,
            **out,
            'sd_delta_per_piece': sd,
            'cohen_d_z': d_z,
        }
        print(f"\n{hyp_id} ({cell_a} − {cell_b}):  {note}")
        print(f"  Observed Δ_CE = {out['observed_mean_delta']:+.4f}  (per-piece σ(Δ) = {sd:.4f}, d_z = {d_z:+.3f})")
        print(f"  95 % CI [{out['ci_low_95']:+.4f}, {out['ci_high_95']:+.4f}]")
        print(f"  Two-sided p = {out['p_two_sided']:.4f}")

    # ---- Save canonical output ----
    output_path = Path(
        '/Users/ruisu/Desktop/ruisuphd/prototype090326AI-functions/research_data/'
        'phase1_paired_bootstrap_2026-05-01.json'
    )
    out_doc = {
        'pre_registration': 'PHASE1_PREREGISTRATION_2026-04-25.md',
        'pre_registration_section': '§3.1',
        'date_run': '2026-05-01',
        'rng_seed': SEED_BOOT,
        'n_boot': N_BOOT,
        'alpha_bonferroni': ALPHA_BONFERRONI,
        'n_compositions': len(composition_ids),
        'composition_ids': composition_ids,
        'phase1_seeds': [s[0] for s in PHASE_I_SEEDS],
        'b9_seeds': B9_SEEDS,
        'cell_means_FW': {
            cell_name: float(np.sum(per_piece_cell_mean(cells[cell_name], composition_ids) * ns) / ns.sum())
            for cell_name in cells
        },
        'classical_FW': fw_c,
        'cell_means_CE': {
            cell_name: float(per_piece_cell_mean(cells[cell_name], composition_ids).mean())
            for cell_name in cells
        },
        'classical_CE': ce_c,
        'contrasts': results,
    }
    with open(output_path, 'w') as f:
        json.dump(out_doc, f, indent=2)
    print(f'\nResults saved to: {output_path}')

    # ---- Final decision-rule summary ----
    print('\n' + '=' * 90)
    print('Pre-registered decision-rule summary (Bonferroni α = 0.01):')
    print('=' * 90)
    for hyp_id in ('H1', 'H2', 'H3', 'H4a', 'H4b'):
        r = results[hyp_id]
        verdict = 'REJECT H_null (cluster-bootstrap supports the alternative)' if r['clears_bonferroni_alpha_001'] and r['observed_mean_delta'] > 0 \
            else ('REJECT H_null (cluster-bootstrap supports OPPOSITE of pre-registered direction)' if r['clears_bonferroni_alpha_001'] and r['observed_mean_delta'] < 0
                  else 'fail to reject H_null at Bonferroni α = 0.01')
        print(f'  {hyp_id} ({r["cell_a"]} > {r["cell_b"]}): Δ = {r["observed_mean_delta"]:+.4f}, '
              f'p = {r["p_two_sided"]:.4f} → {verdict}')


if __name__ == '__main__':
    main()
