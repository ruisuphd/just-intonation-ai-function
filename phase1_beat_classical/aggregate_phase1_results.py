#!/usr/bin/env python3
"""Aggregate Phase I results into a publishable table + paired bootstraps.

Consumes every `runs/{VARIANT}_seed{SEED}_eval.json` produced by
`train_phase1.py` (or the same files extracted from the Drive zips)
and produces:

  * `phase1_beat_classical/phase1_results_<DATE>.json` — all-variant
    aggregate with per-variant mean / σ of test MIREX (FW) and paired
    cluster bootstraps against the B9 5-seed baseline and against
    classical 3-profile.
  * `phase1_beat_classical/phase1_results_<DATE>.md` — chapter-ready
    markdown with the cumulative-technique table and verdict.

Usage:
    # Default: ATEPP-41 (back-compat with thesis chapter results)
    python phase1_beat_classical/aggregate_phase1_results.py

    # Cross-corpus (Month 2 — POP909 / BPS-FH; reference baselines off):
    python phase1_beat_classical/aggregate_phase1_results.py \\
        --input-dir phase1_beat_classical/runs_pop909 \\
        --composition-id-set all \\
        --skip-reference-baselines \\
        --variants BASELINE T6_T1 \\
        --output-md research_data/pop909_results_2026-05-08.md \\
        --output-json research_data/pop909_results_2026-05-08.json

Audit fixes (M2, applied 2026-05-01):
  - BASELINE is now reported alongside T6 / T6_T1 / T6_T1_T2.
  - --input-dir / --output-md / --output-json arguments accepted (matches
    the Colab runner's documented invocation in colab_phase1_beat_classical.py).
  - De-duplication of label / integer alias JSONs by (variant, seed_int).
  - Equality check between alias pairs: warns if two files for the same
    (variant, seed_int) disagree on test_mirex_weighted_score.
  - FW MIREX is recomputed from per-composition (mirex × n_predictions
    sum / total_predictions) for cross-archive consistency.

Cross-corpus fixes (Month 2, applied 2026-05-08):
  - --composition-id-set {atepp41|all|<path>} controls which composition
    IDs are aggregated. Default 'atepp41' preserves chapter back-compat;
    'all' uses every per_composition entry in the eval JSON (POP909 /
    BPS-FH); a JSON path lets users supply a custom allow-list.
  - --skip-reference-baselines disables the ATEPP-41-specific B9 and
    classical 3-profile comparisons (they are not meaningful for
    cross-corpus runs).
  - --variants takes an explicit list of variants to aggregate (defaults
    to the canonical 4: BASELINE, T6, T6_T1, T6_T1_T2).
  - EVAL_PATTERN seed_int regex relaxed from {10,} to {1,} digits so
    smaller hash values (e.g., 940114980 = 9 digits) are not silently
    dropped. This also closes a latent ATEPP-41 bug: seed 440397851
    (the canonical 20260425e seed_int) is 9 digits and was being
    dropped whenever only integer-named files were present.
  - Composition IDs are treated as strings throughout (POP909 uses
    string IDs like 'POP909_001'; ATEPP uses integer IDs like 7);
    no int() coercion is required at any point.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_RUNS = HERE / 'runs'

VARIANTS_TO_REPORT = ['BASELINE', 'T6', 'T6_T1', 'T6_T1_T2']
N_BOOT = 10_000
BOOT_SEED = 20260501

CLASSICAL_JSON = ROOT / 'research_data' / 'phaseA_track1_results' / 'ensemble_eval_seed20260309.json'
B9_RESTORATION_DIR_DEFAULT = ROOT / 'B9_extra_seeds_a100_2026-04-28'  # if extracted
B9_RESTORATION_ZIP = ROOT / 'B9_extra_seeds_a100_2026-04-28-20260429T015448Z-3-001.zip'


# ─────────────────────────────────────────────────────────────────────────
# Per-piece data loading

ATEPP_41 = {
    7, 60, 77, 120, 122, 215, 515, 541, 546, 547, 550, 602, 610, 650, 670,
    672, 728, 876, 907, 910, 1076, 1128, 1132, 1144, 1147, 1164, 1190, 1200,
    1212, 1215, 1227, 1240, 1248, 1256, 1257, 1259, 1263, 1495, 1512, 1518,
    1542,
}
ATEPP_41_STR = {str(c) for c in ATEPP_41}


def _cid_str(value) -> str:
    """Stringify a composition_id without coercing through int().

    POP909 / BPS-FH use string IDs ('POP909_001', 'BPS_FH_07');
    ATEPP uses integer IDs (7, 60, ...). The aggregator stores
    everything as a string and lets the allow-list match either form.
    """
    return str(value)


def _in_id_set(cid_str: str, allowed: Optional[set]) -> bool:
    """Membership test: True iff allowed is None ('all') or cid in allowed."""
    if allowed is None:
        return True
    if cid_str in allowed:
        return True
    # Tolerate ATEPP-41 stored as int in the JSON ('7' vs 7 — both ok)
    try:
        return int(cid_str) in {int(c) for c in allowed if str(c).lstrip('-').isdigit()}
    except (ValueError, TypeError):
        return False


def fw_from_per_composition(per_comp, allowed: Optional[set] = ATEPP_41_STR) -> float:
    """Frame-weighted MIREX from per_composition list.

    `allowed` is a set of composition-id strings (default: ATEPP-41 for
    chapter back-compat). Pass `None` to include every entry (POP909 /
    BPS-FH cross-corpus runs).
    """
    pcs = [p for p in per_comp if _in_id_set(_cid_str(p['composition_id']), allowed)]
    total_n = sum(p['n_predictions'] for p in pcs)
    if not total_n:
        return float('nan')
    return sum(p['mirex'] * p['n_predictions'] for p in pcs) / total_n


# ─────────────────────────────────────────────────────────────────────────
# Eval-JSON enumeration with alias dedup

# Variants pattern: longer names first so the alternation matches greedily
# (re-tested 2026-05-08; T6_T1 must match before T6).
_VARIANT_RE_GROUP = r'(BASELINE|T6_T1_T2|T6_T1|T6)'
EVAL_PATTERN = re.compile(
    # seed_int relaxed from {10,} → {1,}: 9-digit hashes (e.g., 940114980,
    # 440397851) and shorter were silently dropped by the previous regex.
    rf'^{_VARIANT_RE_GROUP}_seed(?:(\d+)|(20260425[a-e]))(?:_eval)?\.json$'
)
# A wider regex that also recognises arbitrary alphanumeric date-style
# seed labels (e.g., '20260508a', '20260508b', '20260508c' for the
# Month 2 POP909 / BPS-FH sweep). Used when --allow-arbitrary-labels is
# passed.
EVAL_PATTERN_LOOSE = re.compile(
    rf'^{_VARIANT_RE_GROUP}_seed(\w+?)(?:_eval)?\.json$'
)

SEED_LABEL_TO_INT = {
    '20260425a': 3886265411,
    '20260425b': 3128166492,
    '20260425c': 1252837625,
    '20260425d': 3629727882,
    '20260425e': 440397851,
}


def find_runs(input_dir: Path,
              variants: Optional[List[str]] = None,
              allow_arbitrary_labels: bool = False) -> Dict[str, Dict[int, Path]]:
    """Return {variant: {seed_int: chosen_file_path}} after de-duplication.

    Args:
        input_dir: Directory containing eval JSONs.
        variants: Optional list of variants to keep (filters after regex
            match). Default keeps every variant the regex matches.
        allow_arbitrary_labels: If True, also accept seed labels that are
            not in `SEED_LABEL_TO_INT` and not pure-digit seed_ints; the
            label is hashed to a stable seed_int via a SHA-256 prefix
            (matching the Colab Month 2 convention). Use this for
            POP909 / BPS-FH-style alphanumeric seed labels.
    """
    import hashlib

    def _label_to_int(label: str) -> int:
        return int(hashlib.sha256(label.encode()).hexdigest()[:8], 16)

    by_key: Dict[Tuple[str, int], List[Path]] = {}
    for path in sorted(input_dir.glob('*.json')):
        m = EVAL_PATTERN.match(path.name)
        if m:
            variant = m.group(1)
            if m.group(2):  # pure-digit seed_int
                seed_int = int(m.group(2))
            else:           # canonical 20260425a-e label
                seed_int = SEED_LABEL_TO_INT[m.group(3)]
        elif allow_arbitrary_labels:
            m2 = EVAL_PATTERN_LOOSE.match(path.name)
            if not m2:
                continue
            variant = m2.group(1)
            seed_token = m2.group(2)
            if seed_token.isdigit():
                seed_int = int(seed_token)
            elif seed_token in SEED_LABEL_TO_INT:
                seed_int = SEED_LABEL_TO_INT[seed_token]
            else:
                seed_int = _label_to_int(seed_token)
        else:
            continue
        if variants is not None and variant not in variants:
            continue
        by_key.setdefault((variant, seed_int), []).append(path)

    # De-duplicate; warn if alias pair disagrees on test_mirex_weighted_score
    chosen: Dict[str, Dict[int, Path]] = {}
    for (variant, seed_int), paths in by_key.items():
        if len(paths) > 1:
            mirexes = []
            for p in paths:
                d = json.load(open(p))
                mirexes.append(d.get('test_mirex_weighted_score', float('nan')))
            spread = max(mirexes) - min(mirexes) if all(np.isfinite(mirexes)) else float('inf')
            if spread > 1e-9:
                print(f'  WARN: alias pair disagrees for {variant}/seed_int={seed_int}: '
                      f'{[(p.name, m) for p, m in zip(paths, mirexes)]}')
            # Prefer integer-named (canonical per pre-registration); 1+ digits accepted
            paths_sorted = sorted(paths,
                                   key=lambda p: (0 if re.search(r'_seed\d+(?:_eval)?\.json$', p.name)
                                                  else 1, p.name))
            chosen.setdefault(variant, {})[seed_int] = paths_sorted[0]
        else:
            chosen.setdefault(variant, {})[seed_int] = paths[0]
    return chosen


def load_classical_per_piece() -> Dict[int, float]:
    d = json.load(open(CLASSICAL_JSON))
    out = {}
    for c in d['per_composition']:
        cid = int(c['composition_id'])
        if cid in ATEPP_41:
            out[cid] = float(c['classical_mirex'])
    return out


def load_b9_per_piece(b9_dir: Path) -> Dict[int, np.ndarray]:
    """B9 5-seed restored per-piece MIREX. Returns {cid: array of 5 seeds}."""
    seeds = ['20260309', '20260310', '20260311', '20260312', '20260313']
    per_piece: Dict[int, list] = {cid: [] for cid in ATEPP_41}
    for s in seeds:
        path = b9_dir / f'B9_seed{s}_predictions.json'
        if not path.exists():
            return {}
        d = json.load(open(path))
        for c in d['compositions']:
            cid = int(c['composition_id'])
            if cid in ATEPP_41:
                per_piece[cid].append(float(c['mirex']))
    return {cid: np.array(v) for cid, v in per_piece.items() if len(v) == 5}


# ─────────────────────────────────────────────────────────────────────────
# Bootstrap

def paired_cluster_bootstrap(vec_a: np.ndarray, vec_b: np.ndarray,
                             n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> Dict:
    rng = np.random.default_rng(seed)
    n = vec_a.shape[0]
    deltas = vec_a - vec_b
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
        'ci_low': float(ci_low),
        'ci_high': float(ci_high),
        'p_two_sided': min(1.0, 2.0 * opp),
        'n_compositions': int(n),
        'n_boot': int(n_boot),
    }


# ─────────────────────────────────────────────────────────────────────────
# Aggregation

def per_variant_per_piece(variant_files: Dict[int, Path],
                          allowed: Optional[Set[str]] = ATEPP_41_STR
                          ) -> Tuple[List[str], np.ndarray, float, float]:
    """Return (cids_sorted, n_seeds×n_pieces array, FW mean over seeds, FW σ ddof=1).

    `allowed` is a set of composition-id strings (None = include all).
    Composition IDs are intersected across seeds, so the returned vector
    is square (n_seeds × n_common_pieces). Cross-corpus runs don't
    guarantee identical per_composition lists across seeds (e.g., a
    piece may be skipped if it has zero predicted frames), so the
    intersection guards the bootstrap from KeyError on missing pieces.
    """
    # 1) Read every seed's per-composition map (string IDs throughout).
    per_seed_maps: List[Dict[str, float]] = []
    fw_per_seed: List[float] = []
    for seed_int in sorted(variant_files):
        d = json.load(open(variant_files[seed_int]))
        pc = {_cid_str(p['composition_id']): float(p['mirex'])
              for p in d['per_composition']
              if _in_id_set(_cid_str(p['composition_id']), allowed)}
        per_seed_maps.append(pc)
        fw_per_seed.append(fw_from_per_composition(d['per_composition'], allowed))

    # 2) Common composition IDs across all seeds (within the allow-list).
    if per_seed_maps:
        common = set.intersection(*(set(m) for m in per_seed_maps))
    else:
        common = set()
    # Stable sort: numeric if all-integer, otherwise lexical
    if common and all(c.lstrip('-').isdigit() for c in common):
        cids_sorted = [str(c) for c in sorted(int(c) for c in common)]
    else:
        cids_sorted = sorted(common)

    # 3) Build the seeds × pieces matrix
    seed_vecs = [np.array([m[cid] for cid in cids_sorted]) for m in per_seed_maps]
    arr = np.stack(seed_vecs) if seed_vecs else np.array([])
    fw_mean = float(np.mean(fw_per_seed)) if fw_per_seed else float('nan')
    fw_sd = float(np.std(fw_per_seed, ddof=1)) if len(fw_per_seed) > 1 else 0.0
    return cids_sorted, arr, fw_mean, fw_sd


def _resolve_id_set(spec: str) -> Tuple[Optional[Set[str]], str]:
    """Resolve --composition-id-set into (allowed_set, label_for_output).

    spec ∈ {'atepp41', 'all', '<path-to-json>'}
      - 'atepp41' → (set of 41 string IDs, 'ATEPP-41')
      - 'all'     → (None, 'all-pieces')
      - <path>    → (set from JSON file's top-level list, basename of path)
    """
    if spec == 'atepp41':
        return ATEPP_41_STR, 'ATEPP-41'
    if spec == 'all':
        return None, 'all-pieces'
    p = Path(spec)
    if not p.exists():
        raise SystemExit(f'--composition-id-set: file not found: {p}')
    data = json.load(open(p))
    if not isinstance(data, list):
        raise SystemExit(f'--composition-id-set: {p} must contain a JSON list of IDs')
    return {str(x) for x in data}, p.stem


def main() -> int:
    ap = argparse.ArgumentParser(description='Phase I results aggregator')
    ap.add_argument('--input-dir', default=str(DEFAULT_RUNS),
                    help='Directory with {VARIANT}_seed*.json eval files')
    ap.add_argument('--b9-dir', default=str(B9_RESTORATION_DIR_DEFAULT),
                    help='Directory with B9 5-seed restoration B9_seed*_predictions.json files')
    ap.add_argument('--output-md', default=str(HERE / 'phase1_results.md'),
                    help='Output Markdown path')
    ap.add_argument('--output-json', default=str(HERE / 'phase1_results.json'),
                    help='Output JSON path')
    ap.add_argument('--n-boot', type=int, default=N_BOOT)
    ap.add_argument('--seed', type=int, default=BOOT_SEED)
    ap.add_argument('--composition-id-set', default='atepp41',
                    help="Which composition IDs to aggregate: 'atepp41' (default — "
                         "thesis-chapter back-compat), 'all' (every per_composition "
                         "entry; for POP909 / BPS-FH cross-corpus runs), or a path "
                         "to a JSON file containing a list of allowed IDs.")
    ap.add_argument('--skip-reference-baselines', action='store_true',
                    help='Skip the ATEPP-41-specific B9 5-seed and classical 3-profile '
                         'comparisons (set this for cross-corpus aggregations).')
    ap.add_argument('--variants', nargs='+', default=None,
                    help='Variants to aggregate (default: BASELINE T6 T6_T1 T6_T1_T2). '
                         'Use e.g. "--variants BASELINE T6_T1" for two-cell runs.')
    ap.add_argument('--allow-arbitrary-labels', action='store_true',
                    help='Accept seed labels that are not pure-digit and not in '
                         'SEED_LABEL_TO_INT (e.g., 20260508a / 20260508b for the '
                         'Month 2 POP909 / BPS-FH sweep). Labels are SHA-256 hashed '
                         'to a stable seed_int, matching the Colab convention.')
    ap.add_argument('--corpus-tag', default='ATEPP-41',
                    help='Free-form corpus label for the output table (e.g., POP909, BPS-FH).')
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f'ERROR: input dir does not exist: {input_dir}')
        return 1

    allowed, id_set_label = _resolve_id_set(args.composition_id_set)
    variants_list = args.variants or VARIANTS_TO_REPORT

    runs = find_runs(input_dir, variants=variants_list,
                     allow_arbitrary_labels=args.allow_arbitrary_labels)
    print(f'Found runs in {input_dir} (composition_id_set = {id_set_label}):')
    for variant in variants_list:
        if variant in runs:
            print(f'  {variant:<10}: {len(runs[variant])} seeds')
        else:
            print(f'  {variant:<10}: 0 seeds (skipping)')

    if args.skip_reference_baselines:
        classical_vec = None
        b9_vec = None
        print('Reference baselines (B9 5-seed, classical 3-profile) skipped (--skip-reference-baselines).')
    else:
        classical = load_classical_per_piece()
        classical_vec = np.array([classical[cid] for cid in sorted(ATEPP_41)
                                  if cid in classical])
        if len(classical_vec) != 41:
            print(f'WARN: classical baseline only has {len(classical_vec)}/41 ATEPP IDs; '
                  f'classical bootstrap may be unreliable')

        b9_per_piece = load_b9_per_piece(Path(args.b9_dir))
        if b9_per_piece:
            b9_vec = np.array([b9_per_piece[cid].mean() for cid in sorted(ATEPP_41)])
            print(f'B9 5-seed restored loaded: cell-mean CE = {b9_vec.mean():.4f}')
        else:
            b9_vec = None
            print(f'WARN: B9 restoration archives not found at {args.b9_dir}; bootstraps vs B9 skipped')

    results = []
    for variant in variants_list:
        if variant not in runs or not runs[variant]:
            continue
        cids, arr, fw_mean, fw_sd = per_variant_per_piece(runs[variant], allowed)
        if arr.size == 0:
            print(f'  WARN: {variant} has no per-composition entries within '
                  f'composition-id-set={id_set_label}; skipping')
            continue
        ce_per_seed_per_piece = arr  # shape (n_seeds, n_pieces)
        cell_per_piece = ce_per_seed_per_piece.mean(axis=0)
        result = {
            'variant': variant,
            'n_seeds': arr.shape[0],
            'seeds': sorted(runs[variant].keys()),
            'mean_test_mirex_FW': fw_mean,
            'std_test_mirex_FW': fw_sd,
            'cell_mean_CE': float(cell_per_piece.mean()),
            'n_compositions': int(arr.shape[1]),
        }
        if classical_vec is not None and arr.shape[1] == len(classical_vec):
            result['vs_classical'] = paired_cluster_bootstrap(
                cell_per_piece, classical_vec, args.n_boot, args.seed)
        if b9_vec is not None and arr.shape[1] == len(b9_vec):
            result['vs_B9_5seed'] = paired_cluster_bootstrap(
                cell_per_piece, b9_vec, args.n_boot, args.seed)
        results.append(result)

    # Same-corpus same-seed paired bootstrap between two variants (e.g.,
    # T6_T1 − BASELINE on POP909). Computed across the intersection of
    # seeds AND pieces (so missing seeds in one cell don't break the
    # comparison).
    same_corpus_paired = None
    if len(results) >= 2:
        a_var = results[-1]['variant']  # last in --variants order: comparison cell
        b_var = results[0]['variant']   # first: reference cell
        a_seeds = set(runs[a_var]); b_seeds = set(runs[b_var])
        common_seeds = sorted(a_seeds & b_seeds)
        if common_seeds:
            # Re-load both cells restricted to common seeds, then
            # intersect pieces to handle any per-piece skips.
            a_files = {s: runs[a_var][s] for s in common_seeds}
            b_files = {s: runs[b_var][s] for s in common_seeds}
            a_cids, a_arr, _, _ = per_variant_per_piece(a_files, allowed)
            b_cids, b_arr, _, _ = per_variant_per_piece(b_files, allowed)
            common_cids = sorted(set(a_cids) & set(b_cids),
                                 key=lambda c: int(c) if c.lstrip('-').isdigit() else c)
            if common_cids:
                a_idx = [a_cids.index(c) for c in common_cids]
                b_idx = [b_cids.index(c) for c in common_cids]
                a_vec = a_arr[:, a_idx].mean(axis=0)
                b_vec = b_arr[:, b_idx].mean(axis=0)
                same_corpus_paired = paired_cluster_bootstrap(
                    a_vec, b_vec, args.n_boot, args.seed)
                same_corpus_paired['contrast'] = f'{a_var} − {b_var}'
                same_corpus_paired['n_common_seeds'] = len(common_seeds)
                same_corpus_paired['n_common_pieces'] = len(common_cids)

    # Save JSON
    out_doc = {
        'date': '2026-05-01',
        'rng_seed': args.seed,
        'n_boot': args.n_boot,
        'composition_id_set': id_set_label,
        'corpus_tag': args.corpus_tag,
        'variants': results,
    }
    if classical_vec is not None and len(classical_vec) > 0:
        out_doc['n_test_compositions'] = 41
        out_doc['classical_baseline_FW_atepp41'] = float(
            np.sum(classical_vec) / len(classical_vec))  # CE not FW; for ref
        out_doc['classical_baseline_CE_atepp41'] = float(classical_vec.mean())
    if same_corpus_paired is not None:
        out_doc['same_corpus_paired'] = same_corpus_paired
    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out_doc, indent=2))

    # Save Markdown
    lines = [
        '# Phase I — Cumulative Ablation Results',
        '',
        f'**Generated by:** `aggregate_phase1_results.py`',
        f'**Bootstrap RNG seed:** {args.seed} (B = {args.n_boot})',
        f'**Corpus:** {args.corpus_tag} (composition-id set = {id_set_label})',
        '',
        '## 1. Per-cell summary',
        '',
        '| Variant | n seeds | n pieces | Test MIREX (FW) | Cell-mean (CE) |',
        '|---|---:|---:|---:|---:|',
    ]
    for r in results:
        lines.append(
            f'| {r["variant"]} | {r["n_seeds"]} | {r["n_compositions"]} | '
            f'{r["mean_test_mirex_FW"]:.4f} ± {r["std_test_mirex_FW"]:.4f} | '
            f'{r["cell_mean_CE"]:.4f} |'
        )
    if classical_vec is not None and len(classical_vec) > 0:
        lines.append('| Classical 3-profile (ATEPP-41) | — | 41 | '
                     '0.6201 (FW from `evaluate_classical_baseline.py`) | '
                     f'{out_doc["classical_baseline_CE_atepp41"]:.4f} |')

    if b9_vec is not None and any('vs_B9_5seed' in r for r in results):
        lines += [
            '',
            '## 2. Paired cluster bootstrap vs B9 5-seed restored (n = 5 vs n = 5)',
            '',
            '| Variant | Δ_CE | 95 % CI | Two-sided p |',
            '|---|---:|---|---:|',
        ]
        for r in results:
            b = r.get('vs_B9_5seed')
            if not b:
                continue
            lines.append(
                f'| {r["variant"]} − B9 | {b["mean_delta"]:+.4f} | '
                f'[{b["ci_low"]:+.4f}, {b["ci_high"]:+.4f}] | {b["p_two_sided"]:.4f} |'
            )

    if classical_vec is not None and any('vs_classical' in r for r in results):
        lines += [
            '',
            '## 3. Paired cluster bootstrap vs classical 3-profile (auxiliary)',
            '',
            '| Variant | Δ_CE | 95 % CI | Two-sided p |',
            '|---|---:|---|---:|',
        ]
        for r in results:
            c = r.get('vs_classical')
            if not c:
                continue
            lines.append(
                f'| {r["variant"]} − classical | {c["mean_delta"]:+.4f} | '
                f'[{c["ci_low"]:+.4f}, {c["ci_high"]:+.4f}] | {c["p_two_sided"]:.4f} |'
            )

    if same_corpus_paired is not None:
        lines += [
            '',
            f'## 4. Same-corpus paired cluster bootstrap ({same_corpus_paired["contrast"]})',
            '',
            f'- Mean Δ_CE = {same_corpus_paired["mean_delta"]:+.4f}',
            f'- 95 % CI = [{same_corpus_paired["ci_low"]:+.4f}, '
            f'{same_corpus_paired["ci_high"]:+.4f}]',
            f'- Two-sided p = {same_corpus_paired["p_two_sided"]:.4f} '
            f'(B = {args.n_boot})',
            f'- n common seeds = {same_corpus_paired["n_common_seeds"]}',
            f'- n common pieces = {same_corpus_paired["n_common_pieces"]}',
        ]

    Path(args.output_md).write_text('\n'.join(lines) + '\n')
    print(f'Wrote: {out_json}')
    print(f'Wrote: {args.output_md}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
