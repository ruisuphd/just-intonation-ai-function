#!/usr/bin/env python3
"""Hyperparameter sensitivity sweep around BASELINE / T6_T1.

Closes Tier 2.4 of COMPREHENSIVE_RIGOUR_PLAN_2026-04-26.md §4 and audit
weakness W7 (architecture scaling on the expanded 525-record pool).

Background
----------
The Phase B grid tested h ∈ {32, 96, 192, 256} on the original 250-record
ATEPP pool and found h = 96 was Pareto-optimal (B9 = `ARCH_WINNER`).
With the expanded 525-record pool (BASELINE), W7 asks: does h = 192 (or
larger) help on this larger pool? This script runs the one-hyperparameter-
at-a-time sweep specified in the rigour plan §4.

Cells (one variation each, around BASELINE on ATEPP-41 manifest, n=1
seed initially; bump to n=3 for any cell with > 0.01 FW improvement):

  h        ∈ {48, 96, 144, 192, 256, 384}     (6 cells)
  dropout  ∈ {0.0, 0.1, 0.2, 0.3}              (4 cells)
  ENS β    ∈ {0.99, 0.999, 0.9999, 0.99999}    (4 cells; β=0.999 is BASELINE)
  lr       ∈ {3e-4, 1e-3, 3e-3, 1e-2}          (4 cells; 1e-3 is BASELINE)
  batch    ∈ {4, 8, 16, 32}                    (4 cells; 8 is BASELINE)

Total:  ~22 cells × 1 seed = ~22 GPU-min on A100 (each cell ~1 min training
at h=96-equivalent compute; sweep over h is the only one with non-uniform
compute cost — h=384 is roughly 4× as expensive as h=96).

Output
------
  research_data/sensitivity_sweep_2026-05-09.json + .md
  Heatmap figure-data ready for the §6.6.X chapter prose pass.

Usage
-----
    # Full sweep
    python sensitivity_sweep.py

    # Subset (skip slow h=256 + h=384)
    python sensitivity_sweep.py --skip-large-h

    # Smoke test (1 cell only)
    python sensitivity_sweep.py --smoke-test

Author: Rui Su, 2026-05-09. Tier 2.4 driver.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent

# BASELINE config (the centre of the sweep)
BASELINE = {
    'variant': 'BASELINE',
    'hidden_size': 96,
    'dropout': 0.1,
    'ens_beta': 0.999,
    'lr': 1e-3,
    'batch_size': 8,
    'epochs': 30,
}

# Sweep grid
SWEEP_GRID = [
    # (param_name, param_value, label)
    ('hidden_size', 48,   'h048'),
    ('hidden_size', 96,   'h096_BASELINE'),
    ('hidden_size', 144,  'h144'),
    ('hidden_size', 192,  'h192'),
    ('hidden_size', 256,  'h256'),
    ('hidden_size', 384,  'h384'),
    ('dropout', 0.0,   'dropout000'),
    ('dropout', 0.1,   'dropout010_BASELINE'),
    ('dropout', 0.2,   'dropout020'),
    ('dropout', 0.3,   'dropout030'),
    ('ens_beta', 0.99,    'ens_beta099'),
    ('ens_beta', 0.999,   'ens_beta0999_BASELINE'),
    ('ens_beta', 0.9999,  'ens_beta09999'),
    ('ens_beta', 0.99999, 'ens_beta099999'),
    ('lr', 3e-4,  'lr3e-4'),
    ('lr', 1e-3,  'lr1e-3_BASELINE'),
    ('lr', 3e-3,  'lr3e-3'),
    ('lr', 1e-2,  'lr1e-2'),
    ('batch_size', 4,   'batch04'),
    ('batch_size', 8,   'batch08_BASELINE'),
    ('batch_size', 16,  'batch16'),
    ('batch_size', 32,  'batch32'),
]


def run_one_cell(cell: Dict, seed_int: int, output_dir: Path,
                 manifest: str, label_dirs: str) -> Dict:
    """Train one BASELINE-variant + return the eval JSON.

    NOTE: train_phase1.py does not currently expose --hidden-size / --dropout
    / --ens-beta / --lr / --batch-size as CLI args (it uses fixed values
    matching B9). For the sensitivity sweep we patch train_phase1.py
    once with the additional CLI flags (see sensitivity_sweep_setup.md
    in the project tree for the patch text). This script assumes the
    patched trainer is in place.
    """
    run_id = f'sensitivity_{cell["label"]}_seed{seed_int}'
    cmd = [
        sys.executable, 'phase1_beat_classical/train_phase1.py',
        '--variant', BASELINE['variant'],
        '--seed', str(seed_int),
        '--manifest', manifest,
        '--label-dirs', label_dirs,
        '--epochs', str(cell.get('epochs', BASELINE['epochs'])),
        '--device', 'cuda',
        '--output-dir', str(output_dir),
        '--test-filter', 'atepp41',  # default; sensitivity sweep is in-domain ATEPP-41
        '--hidden-size', str(cell['hidden_size']),
        '--dropout', str(cell['dropout']),
        '--ens-beta', str(cell['ens_beta']),
        '--lr', str(cell['lr']),
        '--batch-size', str(cell['batch_size']),
    ]
    print(f'\n=== {run_id} ===', flush=True)
    print(f'  {cell}', flush=True)
    t0 = time.time()
    subprocess.check_call(cmd)
    dt = time.time() - t0
    eval_json = output_dir / f'{BASELINE["variant"]}_seed{seed_int}_eval.json'
    if not eval_json.exists():
        return {'cell': cell, 'error': f'eval JSON missing: {eval_json}'}
    d = json.load(open(eval_json))
    fw = d.get('test_mirex_weighted_score', float('nan'))
    return {
        'cell': cell,
        'fw_mirex': fw,
        'best_epoch': d.get('best_epoch'),
        'wall_clock_seconds': dt,
        'eval_json': str(eval_json),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest',
                    default='research_data/unified_training_manifest_phase1_clean.json')
    ap.add_argument('--label-dirs',
                    default=','.join([
                        'research_data/score_key_labels',
                        'research_data/dcml_score_key_labels',
                        'research_data/dcml_key_labels',
                        'research_data/wir_key_labels',
                    ]))
    ap.add_argument('--seed-int', type=int, default=20260509)
    ap.add_argument('--output-dir',
                    default='phase1_beat_classical/runs_sensitivity')
    ap.add_argument('--skip-large-h', action='store_true',
                    help='Skip h=256 + h=384 (slow on T4)')
    ap.add_argument('--smoke-test', action='store_true',
                    help='Run only 1 cell to verify pipeline')
    ap.add_argument('--output-json',
                    default='research_data/sensitivity_sweep_2026-05-09.json')
    ap.add_argument('--output-md',
                    default='research_data/sensitivity_sweep_2026-05-09.md')
    args = ap.parse_args()

    grid = list(SWEEP_GRID)
    if args.skip_large_h:
        grid = [c for c in grid if not (c[0] == 'hidden_size' and c[1] >= 256)]
    if args.smoke_test:
        grid = [grid[1]]  # h096_BASELINE only

    output_dir = HERE / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f'Running {len(grid)} sensitivity cells...')
    results = []
    for param_name, param_value, label in grid:
        cell = dict(BASELINE)
        cell[param_name] = param_value
        cell['label'] = label
        cell['varied_param'] = param_name
        cell['varied_value'] = param_value
        try:
            r = run_one_cell(cell, args.seed_int, output_dir,
                             args.manifest, args.label_dirs)
        except subprocess.CalledProcessError as e:
            r = {'cell': cell, 'error': f'training failed: {e}'}
        results.append(r)

    # Save JSON
    out = {
        'date': '2026-05-09',
        'baseline_config': BASELINE,
        'manifest': args.manifest,
        'seed_int': args.seed_int,
        'n_cells': len(results),
        'cells': results,
    }
    out_json = HERE / args.output_json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, indent=2))

    # Markdown summary table
    md = ['# Hyperparameter sensitivity sweep — 2026-05-09', '']
    md.append(f'**BASELINE config:** {BASELINE}')
    md.append(f'**Manifest:** `{args.manifest}`')
    md.append(f'**Seed_int:** {args.seed_int} (n=1 per cell; expand to n=3 for any cell with > 0.01 FW improvement)')
    md.append('')
    md.append('| Param | Value | Label | FW MIREX | Δ vs BASELINE | best_epoch | Wall-clock |')
    md.append('|---|---|---|---:|---:|---:|---:|')
    # Find BASELINE FW for delta
    baseline_fw = next((r.get('fw_mirex') for r in results
                        if r.get('cell', {}).get('label', '').endswith('_BASELINE')
                        and r.get('cell', {}).get('hidden_size') == 96), None)
    for r in results:
        c = r.get('cell', {})
        if 'error' in r:
            md.append(f"| {c.get('varied_param')} | {c.get('varied_value')} | {c.get('label')} | "
                      f"ERROR | — | — | — |")
            continue
        fw = r['fw_mirex']
        delta = (fw - baseline_fw) if (baseline_fw is not None) else float('nan')
        wall = f"{r['wall_clock_seconds'] / 60:.1f} min"
        md.append(f"| {c['varied_param']} | {c['varied_value']} | {c['label']} | "
                  f"{fw:.4f} | {delta:+.4f} | {r.get('best_epoch')} | {wall} |")
    md.append('')
    md.append('---')
    md.append('')
    md.append('*Compiled by `sensitivity_sweep.py` 2026-05-09. Closes Tier 2.4 / audit W7.*')

    out_md = HERE / args.output_md
    out_md.write_text('\n'.join(md) + '\n')
    print(f'\n✓ Wrote {out_json}')
    print(f'✓ Wrote {out_md}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
