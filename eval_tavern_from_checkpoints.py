#!/usr/bin/env python3
"""TAVERN eval (BASELINE + T6_T1 × 5 each) from saved checkpoints.

Closes Tier 2.3 (TAVERN cross-corpus secondary test) of the rigour plan.
Mirrors `eval_bps_fh_from_checkpoints.py` exactly; only the dataset
ingestion differs.

TAVERN provides ~1,060 phrases (after parse_tavern.py) across 17
Beethoven + 10 Mozart theme-and-variations sets. Per-composer subgroup
analysis is reported below the main per-cell summary.

Outputs
-------
  research_data/tavern_eval_2026-05-09.json
  research_data/tavern_eval_2026-05-09.md

Usage
-----
    python eval_tavern_from_checkpoints.py \\
        --tavern-dir research_data/tavern_score_key_labels \\
        --checkpoint-dir phase1_beat_classical/runs \\
        --device cuda

Wall-clock: ~10–20 min on T4, ~5 min on A100 (5 BASELINE + 5 T6_T1
checkpoints × ~1060 phrases; eval-only, no training).

Author: Rui Su, 2026-05-09. Tier 2.3 closure script.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from collections import defaultdict
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


def load_tavern_records(tavern_dir: Path) -> List[Dict]:
    """Load all TAVERN per-phrase JSONs in canonical Strategy-A schema.

    Per-phrase JSONs are output of parse_tavern.py and contain `id`,
    `composer`, `opus`, `notes`. We tag records with `composer` for
    per-subgroup analysis downstream.
    """
    out = []
    for path in sorted(glob.glob(str(tavern_dir / '*.json'))):
        d = json.load(open(path))
        if not d.get('notes'):
            continue
        keys_seen = set(str(n.get('key')) for n in d['notes'] if n.get('key'))
        out.append({
            'composition_id': d['id'],
            'piece_id': d['id'],
            'composer': d.get('composer', 'unknown'),
            'opus': d.get('opus', 'unknown'),
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
                    'composer': rec.get('composer'),
                    'opus': rec.get('opus'),
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


def per_subgroup_summary(per_seed_results: Dict[str, List[Dict]]) -> Dict:
    """Compute per-cell per-composer subgroup FW.

    Returns: {variant: {composer: {fw_per_seed, fw_mean, fw_sd, n_phrases}}}
    """
    out: Dict[str, Dict] = {}
    for variant, cells in per_seed_results.items():
        out[variant] = {}
        # Aggregate per-composer per-seed
        per_seed_per_composer: Dict[str, List[float]] = {}
        per_composer_n: Dict[str, int] = {}
        for c in cells:
            by_composer_mirex = defaultdict(list)
            by_composer_n = defaultdict(int)
            for p in c['per_composition']:
                composer = p.get('composer', 'unknown')
                by_composer_mirex[composer].append((p['mirex'], p['n_predictions']))
                by_composer_n[composer] += p['n_predictions']
            for composer, items in by_composer_mirex.items():
                total_n = sum(n for _, n in items)
                fw = sum(m * n for m, n in items) / max(1, total_n)
                per_seed_per_composer.setdefault(composer, []).append(fw)
                per_composer_n[composer] = max(per_composer_n.get(composer, 0), len(by_composer_mirex[composer]))
        for composer, fws in per_seed_per_composer.items():
            out[variant][composer] = {
                'fw_per_seed': fws,
                'fw_mean': float(np.mean(fws)),
                'fw_sd': float(np.std(fws, ddof=1)) if len(fws) > 1 else 0.0,
                'n_phrases': per_composer_n.get(composer, 0),
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tavern-dir',
                    default='research_data/tavern_score_key_labels',
                    help='Directory of per-phrase TAVERN JSONs (output of parse_tavern.py)')
    ap.add_argument('--checkpoint-dir',
                    default='phase1_beat_classical/runs',
                    help='Directory with the ATEPP-canonical Phase I checkpoints')
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--n-boot', type=int, default=10_000)
    ap.add_argument('--seed', type=int, default=20260509)
    ap.add_argument('--variants', nargs='+', default=['BASELINE', 'T6_T1'])
    ap.add_argument('--output-json',
                    default='research_data/tavern_eval_2026-05-09.json')
    ap.add_argument('--output-md',
                    default='research_data/tavern_eval_2026-05-09.md')
    args = ap.parse_args()

    tavern_dir = Path(args.tavern_dir)
    if not tavern_dir.is_dir():
        print(f'ERROR: tavern-dir not found: {tavern_dir}'); return 1
    ckpt_dir = Path(args.checkpoint_dir)
    if not ckpt_dir.is_dir():
        print(f'ERROR: checkpoint-dir not found: {ckpt_dir}'); return 1
    if args.device == 'cuda' and not torch.cuda.is_available():
        print('  CUDA requested but not available; falling back to CPU')
        args.device = 'cpu'

    print(f'Loading TAVERN records from {tavern_dir}...')
    records = load_tavern_records(tavern_dir)
    print(f'  → {len(records)} phrases loaded')
    if not records:
        return 1
    composer_tally = defaultdict(int)
    for r in records:
        composer_tally[r['composer']] += 1
    for c, n in composer_tally.items():
        print(f'    {c}: {n} phrases')

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
                  f'  (n_phrases = {res["n_pieces"]}; eval = {dt:.1f}s)')

    # Per-cell summary
    out = {
        'date': '2026-05-09',
        'corpus': 'TAVERN (Theme-and-Variations: 17 Beethoven + 10 Mozart works; ~1060 phrases)',
        'reference': 'Devaney, J., Arthur, C., Condit-Schultz, N., & Nisula, K. (2015), ISMIR 728-734.',
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

    # Same-seed paired cluster bootstrap (T6_T1 − BASELINE)
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

    # Per-composer subgroup
    out['per_composer_subgroup'] = per_subgroup_summary(results)

    # Save JSON
    out_json = HERE / args.output_json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, indent=2))

    # Save MD
    md = ['# TAVERN cross-corpus evaluation — 2026-05-09', '']
    md.append(f'**Corpus:** {out["corpus"]}; reference: {out["reference"]}')
    md.append(f'**RNG seed:** {args.seed}, B = {args.n_boot}')
    md.append('')
    md.append('## Per-cell summary')
    md.append('')
    md.append('| Variant | n seeds | n phrases | Test FW MIREX | Reference (ATEPP-41) | Reference (BPS-FH) |')
    md.append('|---|---:|---:|---:|---:|---:|')
    refs_atepp = {'BASELINE': '0.5844 ± 0.0196', 'T6_T1': '0.6707 ± 0.0103'}
    refs_bps = {'BASELINE': '0.7563 ± 0.0241', 'T6_T1': '0.8065 ± 0.0069'}
    n_phrases = len(records)
    for variant in args.variants:
        c = out['per_cell'][variant]
        if c['fw_mean'] is not None:
            md.append(f"| {variant} | {c['n_seeds']} | {n_phrases} | "
                      f"{c['fw_mean']:.4f} ± {c['fw_sd'] or 0:.4f} | "
                      f"{refs_atepp.get(variant, '—')} | {refs_bps.get(variant, '—')} |")

    if bootstrap_out:
        md += ['', f'## Within-corpus paired cluster bootstrap '
               f'({bootstrap_out["contrast"]})', '',
               f'- Mean Δ_CE = {bootstrap_out["mean_delta"]:+.4f}',
               f'- 95 % CI = [{bootstrap_out["ci_low_95"]:+.4f}, '
               f'{bootstrap_out["ci_high_95"]:+.4f}]',
               f'- Two-sided *p* = {bootstrap_out["p_two_sided"]:.4f} (B = {bootstrap_out["n_boot"]})',
               f'- Positive pieces = {bootstrap_out["positive_pieces"]}/{bootstrap_out["n_pieces"]}']

    # σ-collapse summary across THREE corpora (now 4 if TAVERN replicates)
    sd_baseline = out['per_cell'].get('BASELINE', {}).get('fw_sd')
    sd_t6_t1 = out['per_cell'].get('T6_T1', {}).get('fw_sd')
    if sd_baseline is not None and sd_t6_t1 is not None:
        md += ['', '## σ-collapse cross-corpus replication (4-corpus tally)', '',
               '| Corpus | Mode | σ_BASELINE | σ_T6_T1 | σ-ratio |',
               '|---|---|---:|---:|---:|',
               '| ATEPP-41 (Su 2026p) | in-domain | 0.0196 | 0.0103 | 0.52 |',
               '| BPS-FH (Su 2026r) | cross-corpus zero-shot | 0.0241 | 0.0069 | 0.29 |',
               '| POP909 v2 (Su 2026r) | in-domain | 0.0122 | 0.0055 | 0.45 |',
               f'| **TAVERN (this run)** | **cross-corpus zero-shot** | **{sd_baseline:.4f}** | **{sd_t6_t1:.4f}** | **{sd_t6_t1/sd_baseline:.2f}** |',
               '',
               'σ-collapse REPLICATES on a 4th corpus if σ_T6_T1 < σ_BASELINE on TAVERN.']

    # Per-composer subgroup
    md += ['', '## Per-composer subgroup analysis (composer-overlap audit)', '']
    md += [f'**Why this matters:** TAVERN includes Beethoven (overlap with DCML string '
           f'quartets in training) AND Mozart (overlap with `dcml_corpora/mozart_piano_sonatas` '
           f'in training). Per-composer FW lets us check whether the σ-collapse holds '
           f'within both subgroups separately.', '']
    md.append('| Variant | Composer | n seeds | FW MIREX |')
    md.append('|---|---|---:|---:|')
    for variant in args.variants:
        for composer, c in out['per_composer_subgroup'][variant].items():
            n_seeds = len(c['fw_per_seed'])
            c['n_seeds'] = n_seeds  # also persist into JSON
            md.append(f"| {variant} | {composer} | {n_seeds} | "
                      f"{c['fw_mean']:.4f} ± {c['fw_sd']:.4f} |")

    out_md = HERE / args.output_md
    out_md.write_text('\n'.join(md) + '\n')
    print(f'\n✓ Wrote {out_json}')
    print(f'✓ Wrote {out_md}')
    print()
    print(open(args.output_md).read())
    return 0


if __name__ == '__main__':
    sys.exit(main())
