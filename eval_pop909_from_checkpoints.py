#!/usr/bin/env python3
"""POP909 re-eval from saved checkpoints (Month 2 cross-corpus salvage).

Background
----------
The original Phase I Month 2 sweep (2026-05-08) trained BASELINE × 3 +
T6_T1 × 3 on POP909 successfully, but the trainer's hardcoded
`filter_test_to_atepp_41` silently dropped every POP909 test record
(POP909 IDs are strings; the int-coercion failed → all 182 test pieces
were dropped). The 6 saved `.pt` checkpoints survive intact.

This script bypasses the trainer entirely: it loads each checkpoint and
runs a checkpoint-only eval pass against the 182 POP909 test records,
exactly mirroring the inline-eval pattern Cell 5 uses for BPS-FH. It
produces:

  * Per-cell summary (FW MIREX mean ± σ, n seeds)
  * Same-seed paired cluster bootstrap (T6_T1 − BASELINE) on common
    pieces, B = 10 000, RNG seed 20260508
  * Canonical JSON + Markdown at the paths Cell 23 (Drive sync) expects:
      research_data/pop909_results_2026-05-08.json
      research_data/pop909_results_2026-05-08.md

Usage
-----
    python eval_pop909_from_checkpoints.py
    python eval_pop909_from_checkpoints.py \\
        --checkpoint-dir phase1_beat_classical/runs_pop909 \\
        --manifest research_data/pop909_manifest_2026-05-08.json \\
        --device cuda --n-boot 10000 --seed 20260508

Wall-clock: ~5–10 min on T4 (eval-only, no training); ~3 min on A100.

Author: Rui Su, 2026-05-09. Cross-corpus salvage script.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch
from torch.utils.data import DataLoader

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from phase1_beat_classical.phase1_dataset import (  # noqa: E402
    Phase1Dataset, collate_phase1_batch,
)
from phase1_beat_classical.phase1_variants import HarmonicContextGRUPhase1  # noqa: E402
from train_harmonic_context_model import masked_mirex  # noqa: E402


VARIANT_CFG = {
    'BASELINE': {'use_global_pcp': False, 'use_chord_heads': False},
    'T6':       {'use_global_pcp': False, 'use_chord_heads': False},
    'T6_T1':    {'use_global_pcp': True,  'use_chord_heads': False},
    'T6_T1_T2': {'use_global_pcp': True,  'use_chord_heads': True},
}


def load_pop909_test_records(manifest_path: Path) -> List[Dict]:
    """Load all manifest entries tagged split='test', read each file_path."""
    m = json.load(open(manifest_path))
    test_entries = [e for e in m.get('entries', []) if e.get('split') == 'test']
    out = []
    skipped = 0
    for e in test_entries:
        fp = Path(e['file_path'])
        if not fp.is_absolute():
            fp = HERE / fp
        if not fp.exists():
            skipped += 1
            continue
        d = json.load(open(fp))
        if not d.get('notes'):
            skipped += 1
            continue
        # Phase1Dataset only requires composition_id/piece_id/notes/is_modulating
        keys_seen = set(str(n.get('key')) for n in d['notes'] if n.get('key'))
        out.append({
            'composition_id': e['composition_id'],
            'piece_id': e['composition_id'],
            'notes': d['notes'],
            'is_modulating': len(keys_seen) >= 2,
        })
    if skipped:
        print(f'  WARN: {skipped} test entries skipped (file missing or no notes)')
    return out


def evaluate_checkpoint(records: List[Dict], checkpoint_path: Path,
                        variant: str, device: str) -> Dict:
    """Mirror Cell 5's inline-eval contract; return per-piece + FW MIREX."""
    cfg = VARIANT_CFG[variant]
    model = HarmonicContextGRUPhase1(
        hidden_size=96, **cfg,
    ).to(device).eval()
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt['model_state_dict'])

    test_results = []
    with torch.no_grad():
        for rec in records:
            single_ds = Phase1Dataset(
                [rec], use_global_pcp=cfg['use_global_pcp'],
                use_chord_labels=False, n_transpositions=1,
            )
            if len(single_ds) == 0:
                continue
            loader = DataLoader(single_ds, batch_size=16, shuffle=False,
                                collate_fn=collate_phase1_batch)
            piece_mirex_sum = 0.0
            piece_correct = 0
            piece_n = 0
            for batch in loader:
                batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                         for k, v in batch.items()}
                logits = model(batch)['key_logits']
                labels = batch['labels']
                mask = labels != -100
                sum_score, n = masked_mirex(logits, labels)
                piece_mirex_sum += sum_score
                piece_n += n
                piece_correct += int(((logits.argmax(-1) == labels) & mask).sum().item())
            if piece_n > 0:
                test_results.append({
                    'composition_id': rec['composition_id'],
                    'mirex': piece_mirex_sum / piece_n,
                    'accuracy': piece_correct / piece_n,
                    'n_predictions': piece_n,
                })
    total_n = sum(r['n_predictions'] for r in test_results)
    fw = sum(r['mirex'] * r['n_predictions'] for r in test_results) / max(1, total_n)
    return {
        'fw_mirex': float(fw),
        'n_pieces': len(test_results),
        'per_composition': test_results,
    }


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
    ap.add_argument('--checkpoint-dir',
                    default='phase1_beat_classical/runs_pop909',
                    help='Directory containing the BASELINE/T6_T1 .pt files')
    ap.add_argument('--manifest',
                    default='research_data/pop909_manifest_2026-05-08.json')
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--n-boot', type=int, default=10_000)
    ap.add_argument('--seed', type=int, default=20260508)
    ap.add_argument('--variants', nargs='+', default=['BASELINE', 'T6_T1'])
    ap.add_argument('--output-json',
                    default='research_data/pop909_results_2026-05-08.json')
    ap.add_argument('--output-md',
                    default='research_data/pop909_results_2026-05-08.md')
    args = ap.parse_args()

    ckpt_dir = Path(args.checkpoint_dir)
    if not ckpt_dir.is_dir():
        print(f'ERROR: checkpoint dir not found: {ckpt_dir}'); return 1

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f'ERROR: manifest not found: {manifest_path}'); return 1

    if args.device == 'cuda' and not torch.cuda.is_available():
        print('  CUDA requested but not available; falling back to CPU')
        args.device = 'cpu'

    print(f'Loading POP909 test records from {manifest_path}...')
    records = load_pop909_test_records(manifest_path)
    print(f'  → {len(records)} test records loaded')
    if not records:
        print('ERROR: 0 test records; aborting'); return 1

    # Load each checkpoint, evaluate, store per-seed results.
    results: Dict[str, List[Dict]] = {v: [] for v in args.variants}
    for variant in args.variants:
        ckpts = sorted(ckpt_dir.glob(f'{variant}_seed*.pt'))
        ckpts = [c for c in ckpts if c.name.split('_seed')[1][0].isdigit()]
        print(f'\n=== {variant}: {len(ckpts)} checkpoints found ===')
        for ckpt in ckpts:
            seed_int = int(ckpt.name.split('_seed')[1].split('.')[0])
            t0 = time.time()
            res = evaluate_checkpoint(records, ckpt, variant, args.device)
            dt = time.time() - t0
            results[variant].append({
                'seed_int': seed_int,
                'fw_mirex': res['fw_mirex'],
                'n_pieces': res['n_pieces'],
                'per_composition': res['per_composition'],
            })
            print(f'  {variant} / seed {seed_int}: FW = {res["fw_mirex"]:.4f}'
                  f'  (n_pieces = {res["n_pieces"]}; eval = {dt:.1f}s)')

    # Per-cell summary
    out = {
        'date': '2026-05-08',
        'corpus': 'POP909',
        'split_rng_seed': 20260508,
        'rng_seed': args.seed,
        'n_boot': args.n_boot,
        'manifest': str(manifest_path.name),
        'checkpoint_dir': str(ckpt_dir),
        'per_cell': {},
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

    # Same-seed paired bootstrap (T6_T1 − BASELINE) on common pieces
    bootstrap_out: Optional[Dict] = None
    if len(args.variants) >= 2:
        a_var, b_var = args.variants[-1], args.variants[0]
        a_seeds = {c['seed_int'] for c in results[a_var]}
        b_seeds = {c['seed_int'] for c in results[b_var]}
        common_seeds = sorted(a_seeds & b_seeds)
        if common_seeds:
            common_cids: Optional[set] = None
            for v in (a_var, b_var):
                for c in results[v]:
                    if c['seed_int'] not in common_seeds:
                        continue
                    cids = {p['composition_id'] for p in c['per_composition']}
                    common_cids = cids if common_cids is None else (common_cids & cids)
            if common_cids:
                common_cids_sorted = sorted(common_cids)

                def cell_mean_per_piece(variant: str) -> np.ndarray:
                    vecs = []
                    for c in results[variant]:
                        if c['seed_int'] not in common_seeds:
                            continue
                        pc = {p['composition_id']: p['mirex']
                              for p in c['per_composition']}
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

    # Persist per-cell per-seed results so downstream tools (e.g. bma_refit_t6t1.py)
    # have access to per-piece predictions with proper composition_ids.
    # Mirrors the structure of eval_bps_fh_from_checkpoints.py (2026-05-09 fix).
    out['per_cell_per_seed_results'] = results

    # Write JSON
    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, indent=2))

    # Write Markdown
    md = ['# POP909 cross-corpus results — 2026-05-08',
          '',
          f'**Eval reuses 6 saved checkpoints from `{ckpt_dir}` (no retraining).**',
          f'**RNG seed:** {args.seed}, B = {args.n_boot}',
          '',
          '## Per-cell summary',
          '',
          '| Variant | n seeds | n test pieces | Test FW MIREX |',
          '|---|---:|---:|---:|']
    for variant in args.variants:
        c = out['per_cell'][variant]
        n_pieces = (c['fw_per_seed'] and
                    results[variant][0]['n_pieces']) or 0
        if c['fw_mean'] is not None:
            md.append(f"| {variant} | {c['n_seeds']} | {n_pieces} | "
                      f"{c['fw_mean']:.4f} ± {c['fw_sd'] or 0:.4f} |")
    if bootstrap_out:
        md += ['',
               f'## Same-seed paired cluster bootstrap '
               f'({bootstrap_out["contrast"]})',
               '',
               f'- Mean Δ_CE = {bootstrap_out["mean_delta"]:+.4f}',
               f'- 95 % CI = [{bootstrap_out["ci_low_95"]:+.4f}, '
               f'{bootstrap_out["ci_high_95"]:+.4f}]',
               f'- Two-sided *p* = {bootstrap_out["p_two_sided"]:.4f} '
               f'(B = {bootstrap_out["n_boot"]})',
               f'- Positive pieces = {bootstrap_out["positive_pieces"]}/'
               f'{bootstrap_out["n_pieces"]}',
               f'- Common seeds = {bootstrap_out["n_common_seeds"]}, '
               f'common pieces = {bootstrap_out["n_common_pieces"]}']
    Path(args.output_md).write_text('\n'.join(md) + '\n')

    print(f'\n✓ Wrote {out_json}')
    print(f'✓ Wrote {args.output_md}')
    print()
    print(open(args.output_md).read())
    return 0


if __name__ == '__main__':
    sys.exit(main())
