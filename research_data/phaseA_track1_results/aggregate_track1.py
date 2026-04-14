"""Phase A Track 1 aggregator (2026-04-14).

Loads per-seed HMM and ensemble eval JSONs and reports:
- Per-seed and 3-seed-mean test MIREX for: A1 base, A1+HMM, A1+ensemble
- Per-class deltas where computable
- Best HMM hyperparameters chosen on val
- Best ensemble alpha chosen on val
- Sanity check: ensemble's neural MIREX should match A1-corrected MIREX (proves
  that the predictions-keyed fix made the ensemble's coverage match the eval).

Run from repo root:
    python3 research_data/phaseA_track1_results/aggregate_track1.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    track1 = repo_root / 'research_data' / 'phaseA_track1_results'
    seed_dir = repo_root / 'phase_a_seeds_2026-04-14'
    seeds = ['20260309', '20260310', '20260311']

    rows = []
    for s in seeds:
        a1 = json.loads((seed_dir / f'A1_phaseA_seed{s}_eval.json').read_text())
        hmm = json.loads((track1 / f'hmm_eval_seed{s}.json').read_text())
        ens = json.loads((track1 / f'ensemble_eval_seed{s}.json').read_text())
        rows.append({
            'seed': s,
            'A1_test_mirex': a1['test']['mirex_weighted_score'],
            'A1_test_acc': a1['test']['accuracy'],
            'A1_minor_acc': a1['class_metrics']['mean_minor_accuracy'],
            'A1_major_acc': a1['class_metrics']['mean_major_accuracy'],
            'val_test_drift': a1['validation']['mirex_weighted_score'] - a1['test']['mirex_weighted_score'],
            'HMM_orig_mirex': hmm['original_mirex'],
            'HMM_test_mirex': hmm['hmm_mirex'],
            'HMM_delta': hmm['mirex_improvement'],
            'HMM_orig_acc': hmm['original_accuracy'],
            'HMM_test_acc': hmm['hmm_accuracy'],
            'HMM_self_t': hmm['self_transition'],
            'HMM_tau': hmm['tau'],
            'ens_neural_mirex': ens.get('neural_mirex'),
            'ens_classical_mirex': ens.get('classical_mirex'),
            'ens_test_mirex': ens.get('ensemble_mirex'),
            'ens_alpha': ens.get('alpha'),
            'ens_n_compositions': len(ens.get('per_composition', [])),
            'ens_total_predictions': sum(c.get('n_predictions', 0)
                                         for c in ens.get('per_composition', [])),
        })

    print('=== Per-seed numbers ===\n')
    cols = ['A1_test_mirex', 'HMM_test_mirex', 'HMM_delta',
            'ens_neural_mirex', 'ens_classical_mirex', 'ens_test_mirex',
            'ens_alpha', 'ens_n_compositions', 'ens_total_predictions',
            'HMM_self_t', 'HMM_tau']
    header = f"{'seed':<10s}  " + '  '.join(f'{c:>16s}' for c in cols)
    print(header)
    print('-' * len(header))
    for r in rows:
        cells = []
        for c in cols:
            v = r[c]
            if v is None:
                s = 'None'
            elif isinstance(v, float):
                s = f'{v:.4f}'
            else:
                s = str(v)
            cells.append(f'{s:>16s}')
        print(f"  {r['seed']:<8s}  " + '  '.join(cells))

    print('\n=== 3-seed aggregate ===\n')
    print(f"{'metric':<24s}  {'mean':>10s}  {'sigma':>9s}  {'max-min':>9s}")
    print('-' * 60)
    for c in ['A1_test_mirex', 'A1_minor_acc', 'A1_major_acc', 'val_test_drift',
              'HMM_test_mirex', 'HMM_delta', 'HMM_test_acc',
              'ens_test_mirex', 'ens_neural_mirex', 'ens_classical_mirex']:
        vals = [r[c] for r in rows if r[c] is not None]
        if not vals:
            continue
        m = statistics.mean(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
        rng = max(vals) - min(vals)
        print(f"  {c:<22s}  {m:>10.4f}  {sd:>9.4f}  {rng:>9.4f}")

    # Sanity-check: ensemble's neural_mirex should match A1's test_mirex (proves
    # the ensemble is now evaluated on the same composition set as the underlying
    # neural eval). Phase A Track 1 fix verification.
    print('\n=== Coverage sanity check ===\n')
    for r in rows:
        diff = abs(r['A1_test_mirex'] - r['ens_neural_mirex'])
        ok = 'OK' if diff < 0.001 else 'MISMATCH'
        print(f"  seed {r['seed']}: A1_test_mirex={r['A1_test_mirex']:.4f}  "
              f"ens_neural_mirex={r['ens_neural_mirex']:.4f}  diff={diff:.4f}  [{ok}]")

    out = {
        'date': '2026-04-14',
        'phase': 'A Track 1 (HMM + ensemble re-eval on 3 A1-corrected seeds)',
        'baseline': 'A1-corrected: causal GRU h=96, weight_mode=sqrt, val_mirex selection, deterministic',
        'per_seed': rows,
        'aggregate': {},
    }
    for c in ['A1_test_mirex', 'A1_minor_acc', 'A1_major_acc', 'val_test_drift',
              'HMM_test_mirex', 'HMM_delta', 'HMM_test_acc',
              'ens_test_mirex', 'ens_neural_mirex', 'ens_classical_mirex']:
        vals = [r[c] for r in rows if r[c] is not None]
        if vals:
            out['aggregate'][c] = {
                'mean': statistics.mean(vals),
                'sigma': statistics.stdev(vals) if len(vals) > 1 else 0.0,
                'max_minus_min': max(vals) - min(vals),
                'values': vals,
            }
    json_path = track1 / 'phaseA_track1_summary_2026-04-14.json'
    json_path.write_text(json.dumps(out, indent=2))
    print(f'\nSaved aggregate summary to {json_path.relative_to(repo_root)}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
