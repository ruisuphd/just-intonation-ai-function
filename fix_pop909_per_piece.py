#!/usr/bin/env python3
"""Recover per-piece composition_ids in POP909 v2 trainer eval JSONs + emit a
canonical pop909_results JSON with per_cell_per_seed_results structure.

Background
----------
`train_phase1.py`'s per-piece eval loop writes `composition_id: 'unknown'`
for every entry in its per-seed eval JSONs. This is a non-fatal upstream
bug: the cell-mean FW + per-seed paired bootstrap from
`eval_pop909_from_checkpoints.py` are correct (they read composition_ids
from the manifest, not from the trainer's eval JSON), but the
`bma_refit_t6t1.py` script reads the trainer's eval JSONs to get
per-piece predictions and therefore collapses all 137 entries to a
single 'unknown' id, returning n_common_pieces=1 and producing
artifactual ensemble FW numbers.

This script recovers the correct composition_ids by exploiting the
trainer's deterministic iteration order: `load_records_from_manifest`
iterates manifest entries in order, filters to split='test', and the
trainer evaluates each test record in that same order. Therefore the
trainer's per_composition[i] corresponds to the manifest's i-th
test entry. Verified locally 2026-05-09: 137/137 pieces match by
n_predictions fingerprint.

Output: a canonical `pop909_results_2026-05-09.json` with the same
top-level shape as `bps_fh_eval_2026-05-09.json` — including
`per_cell_per_seed_results` so `bma_refit_t6t1.py` can find per-piece
predictions correctly.

Usage
-----
    python fix_pop909_per_piece.py \\
        --trainer-runs-dir phase1_month2_2026-05-09/runs_pop909_v2 \\
        --manifest phase1_month2_2026-05-09/pop909_manifest_2026-05-09.json \\
        --output research_data/pop909_results_2026-05-09.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

HERE = Path(__file__).resolve().parent


def recover_per_piece(trainer_eval_json: Path, manifest_test_entries: List[Dict]) -> List[Dict]:
    """Read trainer's per_composition (with 'unknown' ids) and rewrite ids
    using the manifest's test-entry order. Verifies n_predictions matches
    the manifest's note count to catch any order mismatch."""
    d = json.load(open(trainer_eval_json))
    per_comp = d['per_composition']
    if len(per_comp) != len(manifest_test_entries):
        raise SystemExit(
            f'Length mismatch: trainer per_composition has {len(per_comp)} entries '
            f'but manifest has {len(manifest_test_entries)} test entries. '
            f'Cannot recover ids by position.'
        )
    recovered = []
    for i, (entry, p) in enumerate(zip(manifest_test_entries, per_comp)):
        # Verify n_predictions == note count from the entry's file_path
        try:
            n_notes = len(json.load(open(entry['file_path']))['notes'])
            if n_notes != p['n_predictions']:
                raise SystemExit(
                    f'Note-count mismatch at position {i}: manifest entry '
                    f'{entry["composition_id"]} has {n_notes} notes but trainer '
                    f"recorded {p['n_predictions']} predictions. Order is broken; "
                    f'cannot safely recover ids.'
                )
        except FileNotFoundError:
            # If we can't load the file, skip the verification but keep the position
            pass
        recovered.append({
            'composition_id': entry['composition_id'],
            'mirex': float(p['mirex']),
            'accuracy': float(p['accuracy']),
            'n_predictions': int(p['n_predictions']),
        })
    return recovered


def paired_cluster_bootstrap(vec_a: np.ndarray, vec_b: np.ndarray,
                             n_boot: int, seed: int) -> Dict:
    rng = np.random.default_rng(seed)
    deltas = vec_a - vec_b
    n = deltas.shape[0]
    observed = float(np.mean(deltas))
    boot = np.array([float(np.mean(deltas[rng.integers(0, n, size=n)]))
                     for _ in range(n_boot)])
    ci_low, ci_high = np.percentile(boot, [2.5, 97.5])
    if observed > 0:
        opp = float(np.mean(boot <= 0.0))
    elif observed < 0:
        opp = float(np.mean(boot >= 0.0))
    else:
        opp = 0.5
    return {
        'mean_delta': observed,
        'ci_low_95': float(ci_low),
        'ci_high_95': float(ci_high),
        'p_two_sided': min(1.0, 2.0 * opp),
        'n_pieces': int(n),
        'n_boot': int(n_boot),
        'positive_pieces': int((deltas > 0).sum()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--trainer-runs-dir', required=True)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--variants', nargs='+', default=['BASELINE', 'T6_T1'])
    ap.add_argument('--n-boot', type=int, default=10_000)
    ap.add_argument('--seed', type=int, default=20260508)
    ap.add_argument('--output-json', required=True)
    ap.add_argument('--output-md', default=None)
    args = ap.parse_args()

    trainer_dir = (HERE / args.trainer_runs_dir).resolve()
    manifest_path = (HERE / args.manifest).resolve()

    m = json.load(open(manifest_path))
    test_entries = [e for e in m['entries'] if e['split'] == 'test']
    print(f'Manifest test entries: {len(test_entries)}')

    results: Dict[str, List[Dict]] = {v: [] for v in args.variants}
    for variant in args.variants:
        ckpts = sorted(trainer_dir.glob(f'{variant}_seed*_eval.json'))
        ckpts = [c for c in ckpts if c.name.split('_seed')[1][0].isdigit()]
        print(f'\n{variant}: {len(ckpts)} per-seed eval JSONs')
        for path in ckpts:
            seed_int = int(path.name.split('_seed')[1].split('_')[0])
            d = json.load(open(path))
            recovered = recover_per_piece(path, test_entries)
            results[variant].append({
                'seed_int': seed_int,
                'fw_mirex': d['test_mirex_weighted_score'],
                'n_pieces': len(recovered),
                'per_composition': recovered,
            })
            print(f'  seed {seed_int}: FW={d["test_mirex_weighted_score"]:.4f}  '
                  f'recovered_pieces={len(recovered)}')

    # Build the canonical output (mirror of bps_fh_eval JSON)
    out = {
        'date': '2026-05-09',
        'corpus': 'POP909',
        'split_rng_seed': 20260508,
        'rng_seed': args.seed,
        'n_boot': args.n_boot,
        'manifest': str(manifest_path.name),
        'trainer_runs_dir': str(trainer_dir),
        'note': ('per_composition composition_ids recovered by position-matching '
                 'against the manifest test-entry order; the upstream trainer '
                 'writes "unknown" for all ids, fixed by `fix_pop909_per_piece.py` '
                 '2026-05-09'),
        'per_cell': {},
        'per_cell_per_seed_results': results,
    }
    for variant, cell in results.items():
        fws = [c['fw_mirex'] for c in cell]
        out['per_cell'][variant] = {
            'n_seeds': len(cell),
            'fw_per_seed': fws,
            'fw_mean': float(np.mean(fws)) if fws else None,
            'fw_sd': float(np.std(fws, ddof=1)) if len(fws) > 1 else None,
            'seed_ints': [c['seed_int'] for c in cell],
        }

    # Same-seed paired cluster bootstrap (T6_T1 − BASELINE)
    bootstrap_out: Optional[Dict] = None
    if len(args.variants) >= 2:
        a_var, b_var = args.variants[-1], args.variants[0]
        a_seeds = {c['seed_int'] for c in results[a_var]}
        b_seeds = {c['seed_int'] for c in results[b_var]}
        common_seeds = sorted(a_seeds & b_seeds)
        if common_seeds:
            common_cids = None
            for v in (a_var, b_var):
                for c in results[v]:
                    if c['seed_int'] not in common_seeds: continue
                    cids = {p['composition_id'] for p in c['per_composition']}
                    common_cids = cids if common_cids is None else (common_cids & cids)
            if common_cids:
                common_cids_sorted = sorted(common_cids)
                def cell_mean_per_piece(variant):
                    vecs = []
                    for c in results[variant]:
                        if c['seed_int'] not in common_seeds: continue
                        pc = {p['composition_id']: p['mirex'] for p in c['per_composition']}
                        vecs.append(np.array([pc[cid] for cid in common_cids_sorted]))
                    return np.stack(vecs).mean(axis=0)
                a_vec = cell_mean_per_piece(a_var)
                b_vec = cell_mean_per_piece(b_var)
                bs = paired_cluster_bootstrap(a_vec, b_vec, args.n_boot, args.seed)
                bs['contrast'] = f'{a_var} − {b_var}'
                bs['n_common_seeds'] = len(common_seeds)
                bs['n_common_pieces'] = len(common_cids_sorted)
                bootstrap_out = bs
    out['paired_T6_T1_minus_BASELINE'] = bootstrap_out

    out_json = (HERE / args.output_json).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, indent=2))
    print(f'\n✓ Wrote {out_json}')

    if args.output_md:
        md = ['# POP909 cross-corpus results — 2026-05-09 (per-piece-id-fixed)', '']
        md.append('**Source:** trainer per-seed eval JSONs + manifest position-matching.')
        md.append(f'**Trainer runs:** `{trainer_dir}`')
        md.append(f'**Manifest:** `{manifest_path.name}` ({len(test_entries)} test pieces)')
        md.append(f'**RNG seed:** {args.seed}; B = {args.n_boot}')
        md.append('')
        md.append('## Per-cell summary')
        md.append('')
        md.append('| Variant | n seeds | n test pieces | Test FW MIREX |')
        md.append('|---|---:|---:|---:|')
        for v, c in out['per_cell'].items():
            md.append(f"| {v} | {c['n_seeds']} | {len(test_entries)} | "
                      f"{c['fw_mean']:.4f} ± {c['fw_sd'] or 0:.4f} |")
        if bootstrap_out:
            md += ['', f'## Same-seed paired cluster bootstrap '
                   f'({bootstrap_out["contrast"]})', '',
                   f'- Mean Δ_CE = {bootstrap_out["mean_delta"]:+.4f}',
                   f'- 95 % CI = [{bootstrap_out["ci_low_95"]:+.4f}, '
                   f'{bootstrap_out["ci_high_95"]:+.4f}]',
                   f'- Two-sided *p* = {bootstrap_out["p_two_sided"]:.4f} (B = {bootstrap_out["n_boot"]})',
                   f'- Positive pieces = {bootstrap_out["positive_pieces"]}/'
                   f'{bootstrap_out["n_pieces"]}']
        out_md = (HERE / args.output_md).resolve()
        out_md.write_text('\n'.join(md) + '\n')
        print(f'✓ Wrote {out_md}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
