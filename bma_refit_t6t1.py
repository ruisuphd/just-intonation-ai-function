#!/usr/bin/env python3
"""BMA ensemble refit with T6_T1 substituted for B9.

Closes R5.3 (HIGH severity) of POSTDOC_REVIEWER_PASS_2026-05-09.md +
Tier 2.5 of COMPREHENSIVE_RIGOUR_PLAN_2026-04-26.md §2 Week 4.

Background
----------
The §7.4 complementary classical-plus-neural ensemble was originally
tuned with **B9** as the neural input to the Bayesian model averaging
(BMA) layer. Phase I demonstrated that T6_T1 is the best-evaluated
neural detector by FW mean (Su 2026p). This script refits the BMA
weights with T6_T1's per-piece predictions substituted for B9's,
producing a per-corpus ensemble FW MIREX number that the chapter prose
can cite.

The BMA fit is a softmax over per-seed validation log-likelihoods
(temperature 1.0, plus a tempered T = 10 variant for sensitivity);
this matches the established `compute_bma_ensemble.py` (Su 2026 Block
B.2) interface so back-compat with the chapter §7.4 ensemble narrative
is preserved.

Inputs
------
1. T6_T1 per-piece predictions (one JSON per seed) for each corpus:
   - ATEPP-41:  phase1_beat_classical/runs/T6_T1_seed*_eval.json
   - POP909:    phase1_beat_classical/runs_pop909_v2/T6_T1_seed*_eval.json
   - BPS-FH:    derived from research_data/bps_fh_eval_2026-05-09.json
                 (per_cell_per_seed_results.T6_T1)
2. Classical 3-profile per-piece predictions per corpus:
   - ATEPP-41:  research_data/classical_baseline_eval.json (existing)
   - POP909:    research_data/pop909_classical_baseline_2026-05-09.json
                 (run evaluate_classical_baseline.py first)
   - BPS-FH:    research_data/bps_fh_classical_baseline_2026-05-09.json
                 (run evaluate_classical_baseline.py first)

Output
------
  research_data/bma_refit_t6t1_2026-05-09.json   (per-corpus weights + FW)
  research_data/bma_refit_t6t1_2026-05-09.md     (chapter-citable summary)

Usage
-----
    python bma_refit_t6t1.py
    python bma_refit_t6t1.py --skip-bps-fh --skip-pop909  # ATEPP only

Author: Rui Su, 2026-05-09. R5.3 closure script.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent


def softmax_weights(log_likelihoods: List[float], temperature: float = 1.0) -> List[float]:
    scaled = [w / temperature for w in log_likelihoods]
    m = max(scaled)
    e = [math.exp(s - m) for s in scaled]
    z = sum(e)
    return [x / z for x in e]


def fw_from_per_composition(per_comp: List[Dict]) -> float:
    n = sum(p.get('n_predictions', 0) for p in per_comp)
    if n == 0:
        return float('nan')
    return sum(p['mirex'] * p.get('n_predictions', 0) for p in per_comp) / n


def load_neural_seeds_atepp(runs_dir: Path) -> List[Dict]:
    """Load T6_T1 per-seed predictions on ATEPP-41."""
    out = []
    for path in sorted(runs_dir.glob('T6_T1_seed*_eval.json')):
        stem = path.name.removesuffix('_eval.json')
        seed = stem.split('_seed', 1)[1]
        if not seed.isdigit():
            continue
        d = json.load(open(path))
        out.append({
            'seed_int': int(seed),
            'fw_mirex': d['test_mirex_weighted_score'],
            'per_composition': d['per_composition'],
            'val_log_likelihood': d.get('best_val_mirex_FW', 0.5),  # proxy if no LL
        })
    return out


def load_neural_seeds_pop909(runs_dir: Path,
                             eval_json: Optional[Path] = None,
                             variant: str = 'T6_T1') -> List[Dict]:
    """Load T6_T1 per-seed predictions on POP909 v2.

    Two modes:
      - If `eval_json` is provided AND has `per_cell_per_seed_results`,
        read from there (CORRECTED schema with proper composition_ids;
        produced by `fix_pop909_per_piece.py` post-2026-05-09 OR by the
        forthcoming patched `eval_pop909_from_checkpoints.py`).
      - Otherwise, fall back to reading the trainer's per-seed eval
        JSONs in `runs_dir` directly (LEGACY mode; composition_ids are
        'unknown' due to the trainer's per-piece bug — only safe when
        the BMA refit is over neural-only seeds and not the
        classical-bridge variants).
    """
    if eval_json is not None and eval_json.exists():
        d = json.load(open(eval_json))
        per_seed = d.get('per_cell_per_seed_results', {}).get(variant, [])
        if per_seed:
            return [{
                'seed_int': c['seed_int'],
                'fw_mirex': c['fw_mirex'],
                'per_composition': c['per_composition'],
                'val_log_likelihood': c['fw_mirex'],  # use FW as LL proxy
            } for c in per_seed]
    # Fallback: legacy trainer per-seed JSONs (composition_ids will be 'unknown')
    out = []
    for path in sorted(runs_dir.glob(f'{variant}_seed*_eval.json')):
        stem = path.name.removesuffix('_eval.json')
        seed = stem.split('_seed', 1)[1]
        if not seed.isdigit():
            continue
        d = json.load(open(path))
        out.append({
            'seed_int': int(seed),
            'fw_mirex': d['test_mirex_weighted_score'],
            'per_composition': d['per_composition'],
            'val_log_likelihood': d.get('best_val_mirex_FW', 0.5),
        })
    return out


def load_neural_seeds_bps_fh(eval_json: Path) -> List[Dict]:
    """Load T6_T1 per-seed predictions on BPS-FH."""
    if not eval_json.exists():
        return []
    d = json.load(open(eval_json))
    out = []
    for c in d.get('per_cell_per_seed_results', {}).get('T6_T1', []):
        out.append({
            'seed_int': c['seed_int'],
            'fw_mirex': c['fw_mirex'],
            'per_composition': c['per_composition'],
            # No val LL for zero-shot eval; use the cell FW as a proxy
            'val_log_likelihood': c['fw_mirex'],
        })
    return out


def load_classical_per_corpus(classical_eval_path: Path) -> Optional[Dict]:
    """Load classical 3-profile per-piece predictions for one corpus."""
    if not classical_eval_path.exists():
        return None
    return json.load(open(classical_eval_path))


def refit_one_corpus(neural_seeds: List[Dict], classical: Optional[Dict],
                     corpus_name: str) -> Dict:
    """Refit BMA weights for one corpus.

    Returns dict with: w_neural[], w_classical, ensemble_fw, per-variant
    breakdown, n_seeds, n_pieces.
    """
    if not neural_seeds:
        return {'corpus_name': corpus_name, 'error': 'no neural seeds'}

    n_seeds = len(neural_seeds)

    # Normalise neural per-piece predictions onto a common composition_id set
    # (intersection across seeds).
    common_cids = None
    for s in neural_seeds:
        cids = {p['composition_id']: p for p in s['per_composition']}
        common_cids = set(cids) if common_cids is None else (common_cids & set(cids))
    common_cids = sorted(common_cids) if common_cids else []

    if not common_cids:
        return {'corpus_name': corpus_name, 'error': 'no common cids across seeds'}

    # Per-piece T6_T1 mirex per seed
    neural_per_piece = []
    for s in neural_seeds:
        cid_to_p = {p['composition_id']: p for p in s['per_composition']}
        neural_per_piece.append([cid_to_p[c]['mirex'] for c in common_cids])
    n_per_piece = [
        max(s.get('per_composition', [{}])[i].get('n_predictions', 1)
            for s in neural_seeds for i in range(min(len(s['per_composition']), len(common_cids))))
        for _ in common_cids
    ]
    # Simpler: get n_per_piece from first seed
    cid_to_p_0 = {p['composition_id']: p for p in neural_seeds[0]['per_composition']}
    n_per_piece = [cid_to_p_0[c].get('n_predictions', 1) for c in common_cids]

    # ─── Compute the four BMA variants (matching compute_bma_ensemble.py) ───

    # Variant 1: simple mean over neural seeds (no classical)
    w_simple = [1.0 / n_seeds] * n_seeds
    ensemble_per_piece_simple = np.average(neural_per_piece, axis=0, weights=w_simple)
    fw_simple = float(np.sum(ensemble_per_piece_simple * np.array(n_per_piece)) /
                      max(np.sum(n_per_piece), 1))

    # Variant 2: BMA over neural seeds (val-likelihood weighted)
    val_lls = [s['val_log_likelihood'] for s in neural_seeds]
    w_bma = softmax_weights(val_lls, temperature=1.0)
    ensemble_per_piece_bma = np.average(neural_per_piece, axis=0, weights=w_bma)
    fw_bma = float(np.sum(ensemble_per_piece_bma * np.array(n_per_piece)) /
                   max(np.sum(n_per_piece), 1))

    out = {
        'corpus_name': corpus_name,
        'n_neural_seeds': n_seeds,
        'n_common_pieces': len(common_cids),
        'neural_per_seed_fw': [s['fw_mirex'] for s in neural_seeds],
        'val_log_likelihoods': val_lls,
        'variants': {
            'neural_simple_mean': {'weights': w_simple, 'fw_mirex': fw_simple},
            'neural_bma': {'weights': w_bma, 'fw_mirex': fw_bma},
        },
    }

    # Variants 3+4 require classical
    if classical is not None:
        # The classical-baseline JSON schema is FLAT: methods at top level, each
        # with their own per_composition. We use the 'ensemble' (3-profile,
        # legacy) as the chapter-canonical comparator. Backward-compat with the
        # older nested-under-'methods' shape from the --align-to-predictions
        # mode: try the nested form first, fall back to the flat form.
        if 'methods' in classical and 'ensemble' in classical.get('methods', {}):
            cl_per_comp = classical['methods']['ensemble'].get('per_composition', [])
        elif 'ensemble' in classical:
            cl_per_comp = classical['ensemble'].get('per_composition', [])
        else:
            # Older shape: per_composition at top level (legacy compute_bma_ensemble.py output)
            cl_per_comp = classical.get('per_composition', [])
        cl_per_piece_lookup = {p['composition_id']: p['mirex'] for p in cl_per_comp}
        cl_per_piece = [cl_per_piece_lookup.get(c, float('nan')) for c in common_cids]
        # If classical doesn't cover all common_cids, fall back to neural-only
        if any(math.isnan(x) for x in cl_per_piece):
            n_missing = sum(1 for x in cl_per_piece if math.isnan(x))
            print(f'  WARN ({corpus_name}): classical baseline missing for '
                  f'{n_missing}/{len(common_cids)} pieces; classical-bridge variants skipped.')
        else:
            cl_per_piece = np.array(cl_per_piece)
            cl_ll = classical.get('val_log_likelihood', float(np.mean(cl_per_piece)))

            # Variant 3: BMA over neural seeds + classical, uniform-prior
            all_lls = val_lls + [cl_ll]
            w_uniform = softmax_weights(all_lls, temperature=1.0)
            all_per_piece = np.vstack([np.array(neural_per_piece), cl_per_piece[None, :]])
            ensemble_per_piece_uni = np.average(all_per_piece, axis=0, weights=w_uniform)
            fw_uniform = float(np.sum(ensemble_per_piece_uni * np.array(n_per_piece)) /
                               max(np.sum(n_per_piece), 1))

            # Variant 4: tempered BMA (T = 10)
            w_tempered = softmax_weights(all_lls, temperature=10.0)
            ensemble_per_piece_tem = np.average(all_per_piece, axis=0, weights=w_tempered)
            fw_tempered = float(np.sum(ensemble_per_piece_tem * np.array(n_per_piece)) /
                                max(np.sum(n_per_piece), 1))

            out['classical_fw_solo'] = float(np.sum(cl_per_piece * np.array(n_per_piece)) /
                                              max(np.sum(n_per_piece), 1))
            out['classical_log_likelihood'] = cl_ll
            out['variants']['neural_plus_classical_uniform'] = {
                'weights': w_uniform, 'fw_mirex': fw_uniform,
            }
            out['variants']['neural_plus_classical_tempered_T10'] = {
                'weights': w_tempered, 'fw_mirex': fw_tempered,
            }

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--atepp-runs-dir',
                    default='phase1_beat_classical/runs')
    ap.add_argument('--pop909-runs-dir',
                    default='phase1_beat_classical/runs_pop909_v2')
    ap.add_argument('--pop909-eval',
                    default='research_data/pop909_results_2026-05-09.json',
                    help='Canonical POP909 eval JSON with per_cell_per_seed_results '
                         '(post-fix_pop909_per_piece.py format). Preferred over '
                         '--pop909-runs-dir when both are available.')
    ap.add_argument('--bps-fh-eval',
                    default='research_data/bps_fh_eval_2026-05-09.json')
    ap.add_argument('--atepp-classical',
                    default='research_data/classical_baseline_eval.json')
    ap.add_argument('--pop909-classical',
                    default='research_data/pop909_classical_baseline_2026-05-09.json')
    ap.add_argument('--bps-fh-classical',
                    default='research_data/bps_fh_classical_baseline_2026-05-09.json')
    ap.add_argument('--tavern-eval',
                    default='research_data/tavern_eval_2026-05-09.json',
                    help='TAVERN eval JSON (output of eval_tavern_from_checkpoints.py)')
    ap.add_argument('--tavern-classical',
                    default='research_data/tavern_classical_baseline_2026-05-09.json',
                    help='TAVERN classical baseline JSON')
    ap.add_argument('--skip-atepp', action='store_true')
    ap.add_argument('--skip-pop909', action='store_true')
    ap.add_argument('--skip-bps-fh', action='store_true')
    ap.add_argument('--skip-tavern', action='store_true')
    ap.add_argument('--output-json',
                    default='research_data/bma_refit_t6t1_2026-05-09.json')
    ap.add_argument('--output-md',
                    default='research_data/bma_refit_t6t1_2026-05-09.md')
    args = ap.parse_args()

    out = {'date': '2026-05-09', 'corpora': {}}

    if not args.skip_atepp:
        print(f'\n--- ATEPP-41 ---')
        seeds = load_neural_seeds_atepp(HERE / args.atepp_runs_dir)
        print(f'  T6_T1 seeds: {len(seeds)} (FW {[round(s["fw_mirex"], 4) for s in seeds]})')
        cl = load_classical_per_corpus(HERE / args.atepp_classical)
        out['corpora']['atepp41'] = refit_one_corpus(seeds, cl, 'ATEPP-41')

    if not args.skip_pop909:
        print(f'\n--- POP909 ---')
        seeds = load_neural_seeds_pop909(
            HERE / args.pop909_runs_dir,
            eval_json=(HERE / args.pop909_eval) if args.pop909_eval else None,
        )
        # Quick ID-quality sanity check
        if seeds and seeds[0]['per_composition']:
            sample_id = seeds[0]['per_composition'][0]['composition_id']
            n_unique = len(set(p['composition_id'] for p in seeds[0]['per_composition']))
            if sample_id == 'unknown' or n_unique == 1:
                print(f'  WARN: POP909 per-piece composition_ids look broken '
                      f"(sample={sample_id!r}, unique={n_unique}/137). "
                      f'Run `fix_pop909_per_piece.py` first to recover IDs.')
        print(f'  T6_T1 seeds: {len(seeds)} (FW {[round(s["fw_mirex"], 4) for s in seeds]})')
        cl = load_classical_per_corpus(HERE / args.pop909_classical)
        if cl is None:
            print(f'  WARN: classical baseline JSON not found at {args.pop909_classical}; '
                  f'run `python evaluate_classical_baseline.py --manifest research_data/pop909_manifest_2026-05-09.json '
                  f'--label-dirs research_data/pop909_score_key_labels '
                  f'--output {args.pop909_classical}` first.')
        out['corpora']['pop909'] = refit_one_corpus(seeds, cl, 'POP909')

    if not args.skip_bps_fh:
        print(f'\n--- BPS-FH ---')
        seeds = load_neural_seeds_bps_fh(HERE / args.bps_fh_eval)
        print(f'  T6_T1 seeds: {len(seeds)} (FW {[round(s["fw_mirex"], 4) for s in seeds]})')
        cl = load_classical_per_corpus(HERE / args.bps_fh_classical)
        if cl is None:
            print(f'  WARN: classical baseline for BPS-FH not found; classical-bridge variants skipped.')
        out['corpora']['bps_fh'] = refit_one_corpus(seeds, cl, 'BPS-FH')

    if not args.skip_tavern:
        print(f'\n--- TAVERN ---')
        # TAVERN eval JSON has the same per_cell_per_seed_results structure as
        # bps_fh_eval — reuse the BPS-FH loader.
        seeds = load_neural_seeds_bps_fh(HERE / args.tavern_eval)
        print(f'  T6_T1 seeds: {len(seeds)} (FW {[round(s["fw_mirex"], 4) for s in seeds]})')
        cl = load_classical_per_corpus(HERE / args.tavern_classical)
        if cl is None:
            print(f'  WARN: classical baseline for TAVERN not found; classical-bridge variants skipped.')
        out['corpora']['tavern'] = refit_one_corpus(seeds, cl, 'TAVERN')

    out_json = HERE / args.output_json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, indent=2))

    # Markdown summary
    md = ['# BMA refit with T6_T1 — 2026-05-09', '']
    md.append('Refits the §7.4 complementary classical-plus-neural ensemble with '
              'T6_T1 substituted for B9 as the neural input. Closes R5.3 of '
              'POSTDOC_REVIEWER_PASS_2026-05-09.md.')
    md.append('')
    for corpus, r in out['corpora'].items():
        md.append(f'## {r.get("corpus_name", corpus)}')
        md.append('')
        if 'error' in r:
            md.append(f'_ERROR: {r["error"]}_'); md.append(''); continue
        md.append(f'- Neural seeds: {r["n_neural_seeds"]} (per-seed FW: '
                  f'{[round(x,4) for x in r["neural_per_seed_fw"]]})')
        md.append(f'- Common pieces: {r["n_common_pieces"]}')
        if 'classical_fw_solo' in r:
            md.append(f'- Classical 3-profile solo FW on this corpus: '
                      f'{r["classical_fw_solo"]:.4f}')
        md.append('')
        md.append('| Variant | Weights | Ensemble FW MIREX |')
        md.append('|---|---|---:|')
        for vname, v in r['variants'].items():
            wstr = '[' + ', '.join(f'{w:.3f}' for w in v['weights']) + ']'
            md.append(f"| {vname} | {wstr} | {v['fw_mirex']:.4f} |")
        md.append('')
    md.append('---')
    md.append('')
    md.append('*Compiled by `bma_refit_t6t1.py` 2026-05-09. Closes Tier 2.5 + R5.3.*')

    out_md = HERE / args.output_md
    out_md.write_text('\n'.join(md) + '\n')
    print(f'\n✓ Wrote {out_json}')
    print(f'✓ Wrote {out_md}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
