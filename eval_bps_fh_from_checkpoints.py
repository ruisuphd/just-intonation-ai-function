#!/usr/bin/env python3
"""BPS-FH eval (BASELINE + T6_T1 × 5 each) from saved checkpoints.

Background
----------
The 2026-05-08 Month 2 sweep evaluated T6_T1 × 5 zero-shot on BPS-FH and
got cell-mean FW = 0.8065 ± 0.0069 — but the BASELINE comparator was
never run on BPS-FH, so the 14-percentage-point lift over in-domain
ATEPP-41 (T6_T1 = 0.6707) cannot be cleanly attributed to T6_T1 vs
test-set difficulty. This script closes the gap: it runs BASELINE × 5
on BPS-FH using the same 5 ATEPP-canonical seeds, then computes the
within-corpus same-seed paired bootstrap (T6_T1 − BASELINE) on BPS-FH
that the chapter prose actually needs.

Outputs
-------
  research_data/bps_fh_eval_2026-05-09.json  (canonical: per-cell
       summary + per-piece + paired bootstrap; supersedes the previous
       T6_T1-only `bps_fh_t6_t1_eval_2026-05-08.json`)
  research_data/bps_fh_eval_2026-05-09.md    (chapter-ready summary)

Usage
-----
    python eval_bps_fh_from_checkpoints.py \\
        --bps-fh-dir research_data/bps_fh_score_key_labels \\
        --checkpoint-dir phase1_beat_classical/runs \\
        --device cuda

Wall-clock: ~30 min on T4, ~10 min on A100 (5 BASELINE + 5 T6_T1
checkpoints × 32 BPS-FH pieces; eval-only, no training).

Author: Rui Su, 2026-05-09. BPS-FH BASELINE comparator script.
"""
from __future__ import annotations

import argparse
import glob
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


def load_bps_fh_records(bps_dir: Path) -> List[Dict]:
    """Load all BPS-FH per-piece JSONs in the canonical Strategy-A schema.

    The file layout is one JSON per BPS-FH piece (32 total), as produced
    by `parse_bps_fh.py`. Each JSON has `id`, `notes`, `source` etc.
    """
    out = []
    for path in sorted(glob.glob(str(bps_dir / '*.json'))):
        d = json.load(open(path))
        if not d.get('notes'):
            continue
        keys_seen = set(str(n.get('key')) for n in d['notes'] if n.get('key'))
        out.append({
            'composition_id': d['id'],
            'piece_id': d['id'],
            'notes': d['notes'],
            'is_modulating': len(keys_seen) >= 2,
        })
    return out


def evaluate_checkpoint(records: List[Dict], checkpoint_path: Path,
                        variant: str, device: str) -> Dict:
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
    ap.add_argument('--bps-fh-dir',
                    default='research_data/bps_fh_score_key_labels',
                    help='Directory with BPS_FH_*.json (output of parse_bps_fh.py)')
    ap.add_argument('--checkpoint-dir',
                    default='phase1_beat_classical/runs',
                    help='Directory with the ATEPP-canonical Phase I checkpoints')
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--n-boot', type=int, default=10_000)
    ap.add_argument('--seed', type=int, default=20260508)
    ap.add_argument('--variants', nargs='+', default=['BASELINE', 'T6_T1'])
    ap.add_argument('--output-json',
                    default='research_data/bps_fh_eval_2026-05-09.json')
    ap.add_argument('--output-md',
                    default='research_data/bps_fh_eval_2026-05-09.md')
    args = ap.parse_args()

    bps_dir = Path(args.bps_fh_dir)
    if not bps_dir.is_dir():
        print(f'ERROR: bps-fh-dir not found: {bps_dir}'); return 1

    ckpt_dir = Path(args.checkpoint_dir)
    if not ckpt_dir.is_dir():
        print(f'ERROR: checkpoint-dir not found: {ckpt_dir}'); return 1

    if args.device == 'cuda' and not torch.cuda.is_available():
        print('  CUDA requested but not available; falling back to CPU')
        args.device = 'cpu'

    print(f'Loading BPS-FH records from {bps_dir}...')
    records = load_bps_fh_records(bps_dir)
    print(f'  → {len(records)} pieces loaded (expected 32)')
    if len(records) != 32:
        print(f'  WARN: expected 32 BPS-FH pieces, got {len(records)}')
    if not records:
        return 1

    results: Dict[str, List[Dict]] = {v: [] for v in args.variants}
    for variant in args.variants:
        ckpts = sorted(ckpt_dir.glob(f'{variant}_seed*.pt'))
        # Drop label-aliased checkpoints (we use the canonical integer-named ones)
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

    out = {
        'date': '2026-05-09',
        'corpus': 'BPS-FH (Beethoven Piano Sonatas, first movements; n=32)',
        'reference': 'Chen & Su (2018), ISMIR',
        'rng_seed': args.seed,
        'n_boot': args.n_boot,
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
    out['per_cell_per_seed_results'] = results

    # Save JSON
    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, indent=2))

    # Save Markdown
    md = ['# BPS-FH within-classical evaluation — 2026-05-09',
          '',
          '**Eval reuses ATEPP-canonical Phase I checkpoints (no retraining).**',
          f'**Corpus:** {out["corpus"]}; reference: {out["reference"]}',
          f'**RNG seed:** {args.seed}, B = {args.n_boot}',
          '',
          '## Per-cell summary (n_test = 32)',
          '',
          '| Variant | n seeds | Test FW MIREX | Reference (ATEPP-41) |',
          '|---|---:|---:|---:|']
    refs = {'BASELINE': '0.5844 ± 0.0196', 'T6_T1': '0.6707 ± 0.0103',
            'T6': '0.6426 ± 0.0266', 'T6_T1_T2': '0.6606 ± 0.0122'}
    for variant in args.variants:
        c = out['per_cell'][variant]
        if c['fw_mean'] is not None:
            md.append(f"| {variant} | {c['n_seeds']} | "
                      f"{c['fw_mean']:.4f} ± {c['fw_sd'] or 0:.4f} | "
                      f"{refs.get(variant, '—')} |")

    if bootstrap_out:
        md += ['',
               f'## Within-corpus same-seed paired cluster bootstrap '
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

    # σ-collapse summary line
    sd_baseline = out['per_cell'].get('BASELINE', {}).get('fw_sd')
    sd_t6_t1 = out['per_cell'].get('T6_T1', {}).get('fw_sd')
    if sd_baseline is not None and sd_t6_t1 is not None:
        md += ['',
               '## σ-collapse cross-corpus replication',
               '',
               f'| Cell | σ on ATEPP-41 (Su 2026p) | σ on BPS-FH (this run) | ratio |',
               f'|---|---:|---:|---:|',
               f'| BASELINE | 0.0196 | {sd_baseline:.4f} | '
               f'{sd_baseline/0.0196:.2f}× |',
               f'| T6_T1 | 0.0103 | {sd_t6_t1:.4f} | '
               f'{sd_t6_t1/0.0103:.2f}× |',
               '',
               'σ-collapse ranking is REPLICATED if σ_T6_T1 < σ_BASELINE on BPS-FH.']

    Path(args.output_md).write_text('\n'.join(md) + '\n')
    print(f'\n✓ Wrote {out_json}')
    print(f'✓ Wrote {args.output_md}')
    print()
    print(open(args.output_md).read())
    return 0


if __name__ == '__main__':
    sys.exit(main())
