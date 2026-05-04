#!/usr/bin/env python3
"""Formal CI on the σ-ratio for the cross-corpus σ-collapse claim.

Closes R1.1 of POSTDOC_REVIEWER_PASS_2026-05-09.md ("σ-collapse formal CI
via bootstrap on σ-ratio").

Background
----------
The σ-collapse cross-corpus replication (RESEARCH_FINDINGS_2026-05-09.md
§4.2) reports per-cell σ values as point estimates:

  σ_BASELINE on ATEPP-41    = 0.0196   (n = 5)
  σ_T6_T1    on ATEPP-41    = 0.0103   (n = 5)
  σ_BASELINE on BPS-FH      = 0.0241   (n = 5)
  σ_T6_T1    on BPS-FH      = 0.0069   (n = 5)

At n = 5, a single σ point estimate has approximately a factor-of-2
uncertainty (the χ²(4) distribution gives a 95% CI on σ that is
approximately [0.6σ_hat, 2.9σ_hat]). The descriptive observation that
"σ_T6_T1 < σ_BASELINE on both corpora" and "σ_T6_T1 / σ_BASELINE
TIGHTENS from 0.53 (in-domain) to 0.29 (cross-corpus)" is at risk of
being challenged by a strict statistician on these grounds.

This script computes:

  (a) Per-corpus, per-cell σ point estimates and parametric χ² 95% CIs
      (the 'closed-form' answer; for sanity).
  (b) Per-corpus σ-ratio σ_T6_T1 / σ_BASELINE, with a bootstrap CI
      (B = 10,000 resamples of the n = 5 per-seed FW vectors with
      replacement; ratio recomputed per resample). RNG seed 20260509 for
      reproducibility.
  (c) The CROSS-CORPUS σ-asymmetry test: is the change in σ from
      ATEPP-41 to BPS-FH significantly different between cells? This is
      a permutation test under the null that "the (corpus → σ) change
      is symmetric across cells", i.e. σ_BASELINE_BPS / σ_BASELINE_ATEPP
      ≈ σ_T6_T1_BPS / σ_T6_T1_ATEPP. Permutes the (cell, corpus) labels
      and recomputes the asymmetry statistic; reports a one-sided
      p-value.
  (d) Levene's test for variance equality across cells within each
      corpus, as a non-parametric sanity check.

Output
------
  research_data/sigma_collapse_formal_tests_2026-05-09.json
  research_data/sigma_collapse_formal_tests_2026-05-09.md

The Markdown is the chapter-citable form; the JSON is the audit trail.

Usage
-----
    python compute_sigma_ratio_bootstrap.py
    python compute_sigma_ratio_bootstrap.py --n-boot 10000 --seed 20260509

The script does NOT require new training; it reads existing per-seed FW
values from:
  - phase1_beat_classical/runs/{BASELINE,T6_T1}_seed*_eval.json (ATEPP)
  - research_data/bps_fh_eval_2026-05-09.json (BPS-FH cross-corpus)

Author: Rui Su, 2026-05-09. R1.1 closure script.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent

# ─────────────────────────────────────────────────────────────────────────
# Per-cell per-seed FW vectors (the n = 5 numbers driving everything)

def load_atepp_per_seed(runs_dir: Path) -> Dict[str, List[float]]:
    """Read per-seed FW from phase1_beat_classical/runs/{VARIANT}_seed*_eval.json.

    Returns {variant: [fw_seed_a, fw_seed_b, ..., fw_seed_e]} sorted by seed_int.
    """
    out: Dict[str, List[Tuple[int, float]]] = {}
    for variant in ('BASELINE', 'T6', 'T6_T1', 'T6_T1_T2'):
        for path in sorted(runs_dir.glob(f'{variant}_seed*_eval.json')):
            stem = path.name.removesuffix('_eval.json')
            seed_str = stem.split('_seed', 1)[1]
            if not seed_str.isdigit():
                continue  # skip label-aliased files; integer is canonical
            d = json.load(open(path))
            fw = d.get('test_mirex_weighted_score')
            if fw is None or not isinstance(fw, (int, float)):
                continue
            out.setdefault(variant, []).append((int(seed_str), float(fw)))
    return {v: [fw for _, fw in sorted(items)] for v, items in out.items()}


def load_bps_fh_per_seed(eval_json: Path) -> Dict[str, List[float]]:
    """Read per-seed FW from research_data/bps_fh_eval_2026-05-09.json."""
    if not eval_json.exists():
        raise SystemExit(f'BPS-FH eval JSON not found: {eval_json}\n'
                         f'Run eval_bps_fh_from_checkpoints.py first, or sync from Drive.')
    d = json.load(open(eval_json))
    out: Dict[str, List[float]] = {}
    for v in ('BASELINE', 'T6_T1'):
        cell = d.get('per_cell', {}).get(v)
        if cell is None:
            continue
        out[v] = [float(x) for x in cell['fw_per_seed']]
    return out


def load_corpus_per_seed(eval_json: Path, corpus_label: str = '') -> Dict[str, List[float]]:
    """Generic per-seed loader for any cross-corpus eval JSON that has a
    `per_cell.{BASELINE,T6_T1}.fw_per_seed` structure (matches both
    bps_fh_eval_2026-05-09.json and pop909_results_2026-05-09.json and
    tavern_eval_2026-05-09.json).
    """
    if not eval_json.exists():
        raise SystemExit(
            f'{corpus_label or "corpus"} eval JSON not found: {eval_json}\n'
            f'Run the appropriate eval script first, or sync from Drive.'
        )
    d = json.load(open(eval_json))
    out: Dict[str, List[float]] = {}
    for v in ('BASELINE', 'T6_T1'):
        cell = d.get('per_cell', {}).get(v)
        if cell is None:
            continue
        out[v] = [float(x) for x in cell['fw_per_seed']]
    return out


# ─────────────────────────────────────────────────────────────────────────
# Statistics

def chi2_sigma_ci(sigma_hat: float, n: int, alpha: float = 0.05) -> Tuple[float, float]:
    """Closed-form parametric χ²(n-1) CI on σ given a sample-σ point estimate.

    Under the assumption that the underlying per-seed FW values are i.i.d.
    Gaussian (a strong assumption, but the n = 5 case is too small to
    test empirically), the (1-α) CI on σ is:

      [sigma_hat * sqrt((n-1) / chi2_upper),
       sigma_hat * sqrt((n-1) / chi2_lower)]

    where chi2_lower / chi2_upper are the α/2 and 1-α/2 quantiles of
    χ²(n-1).
    """
    from scipy.stats import chi2 as _chi2  # noqa: WPS433  (lazy import)
    df = n - 1
    chi2_lower = _chi2.ppf(alpha / 2, df)
    chi2_upper = _chi2.ppf(1 - alpha / 2, df)
    ci_low = sigma_hat * math.sqrt(df / chi2_upper)
    ci_high = sigma_hat * math.sqrt(df / chi2_lower)
    return float(ci_low), float(ci_high)


def bootstrap_sigma_ratio(fws_a: List[float], fws_b: List[float],
                          n_boot: int, seed: int) -> Dict:
    """Bootstrap 95% CI on σ_a / σ_b where each σ is the sample sd (ddof=1)
    of the per-seed FW vector.

    Resamples fws_a and fws_b with replacement (sample size preserved).
    Returns observed ratio, 95% CI, and a sanity statistic.
    """
    fws_a = np.asarray(fws_a, dtype=float)
    fws_b = np.asarray(fws_b, dtype=float)
    n_a, n_b = len(fws_a), len(fws_b)
    if n_a < 2 or n_b < 2:
        raise ValueError(f'Need at least 2 seeds per cell; got {n_a}, {n_b}')

    rng = np.random.default_rng(seed)
    sigma_a = float(np.std(fws_a, ddof=1))
    sigma_b = float(np.std(fws_b, ddof=1))
    obs_ratio = sigma_a / sigma_b

    boot_ratios = []
    for _ in range(n_boot):
        a_resample = rng.choice(fws_a, size=n_a, replace=True)
        b_resample = rng.choice(fws_b, size=n_b, replace=True)
        sa = float(np.std(a_resample, ddof=1))
        sb = float(np.std(b_resample, ddof=1))
        if sb < 1e-12:
            continue  # degenerate resample; skip
        boot_ratios.append(sa / sb)
    boot_ratios = np.asarray(boot_ratios)
    ci_low, ci_high = np.percentile(boot_ratios, [2.5, 97.5])

    return {
        'observed_ratio': obs_ratio,
        'sigma_a': sigma_a,
        'sigma_b': sigma_b,
        'ci_low_95': float(ci_low),
        'ci_high_95': float(ci_high),
        'n_boot': int(n_boot),
        'n_a': int(n_a),
        'n_b': int(n_b),
        'fraction_below_1': float(np.mean(boot_ratios < 1.0)),
    }


def cross_corpus_asymmetry_permutation(
    atepp_a: List[float], atepp_b: List[float],
    bps_a: List[float], bps_b: List[float],
    n_perm: int, seed: int,
) -> Dict:
    """Permutation test for the cross-corpus σ-asymmetry.

    Asymmetry statistic A = (σ_a_BPS / σ_a_ATEPP) / (σ_b_BPS / σ_b_ATEPP).
    Under the null that "cell-specific σ change under domain shift is
    symmetric", A should be close to 1.

    Permutes the (cell label) within each corpus's per-seed vector (so the
    paired structure is preserved across corpora) and recomputes A.
    Reports a two-sided p-value on |log A|.

    With n = 5 seeds per cell × 2 cells × 2 corpora = 20 numbers, the
    full permutation space has 2^5 = 32 cell-swap combinations PER CORPUS
    × 32 = 1024 unique combinations, so n_perm = 10000 is comfortably above
    the discrete space; we sample with replacement from the cell-swap
    distribution.
    """
    atepp_a = np.asarray(atepp_a, dtype=float)
    atepp_b = np.asarray(atepp_b, dtype=float)
    bps_a = np.asarray(bps_a, dtype=float)
    bps_b = np.asarray(bps_b, dtype=float)

    # Sanity: ensure all four cells have the same length
    n = len(atepp_a)
    assert len(atepp_b) == n and len(bps_a) == n and len(bps_b) == n, \
        f'σ-asymmetry test requires equal n; got {len(atepp_a)}/{len(atepp_b)}/{len(bps_a)}/{len(bps_b)}'

    def asymmetry(aa, ab, ba, bb):
        sigma_a_atepp = float(np.std(aa, ddof=1))
        sigma_b_atepp = float(np.std(ab, ddof=1))
        sigma_a_bps = float(np.std(ba, ddof=1))
        sigma_b_bps = float(np.std(bb, ddof=1))
        # Guards
        if min(sigma_a_atepp, sigma_b_atepp, sigma_a_bps, sigma_b_bps) < 1e-12:
            return float('nan')
        ratio_a = sigma_a_bps / sigma_a_atepp
        ratio_b = sigma_b_bps / sigma_b_atepp
        return ratio_a / ratio_b  # = asymmetry statistic A

    obs_A = asymmetry(atepp_a, atepp_b, bps_a, bps_b)
    obs_log_A = math.log(obs_A) if obs_A > 0 else float('nan')

    rng = np.random.default_rng(seed)
    perm_log_A = []
    for _ in range(n_perm):
        # Random per-seed cell-label swaps within each corpus
        atepp_swap = rng.integers(0, 2, size=n).astype(bool)
        bps_swap = rng.integers(0, 2, size=n).astype(bool)
        new_atepp_a = np.where(atepp_swap, atepp_b, atepp_a)
        new_atepp_b = np.where(atepp_swap, atepp_a, atepp_b)
        new_bps_a = np.where(bps_swap, bps_b, bps_a)
        new_bps_b = np.where(bps_swap, bps_a, bps_b)
        A = asymmetry(new_atepp_a, new_atepp_b, new_bps_a, new_bps_b)
        if not math.isnan(A) and A > 0:
            perm_log_A.append(math.log(A))

    perm_log_A = np.asarray(perm_log_A)
    if len(perm_log_A) == 0:
        return {'observed_A': obs_A, 'p_two_sided': float('nan'), 'n_perm_valid': 0}

    p_two = float(np.mean(np.abs(perm_log_A) >= abs(obs_log_A))) if not math.isnan(obs_log_A) else float('nan')

    return {
        'observed_A': float(obs_A),
        'observed_log_A': float(obs_log_A) if not math.isnan(obs_log_A) else None,
        'p_two_sided': float(p_two),
        'n_perm': int(n_perm),
        'n_perm_valid': int(len(perm_log_A)),
        'interpretation': (
            'p_two_sided < 0.05 → reject null of symmetric cross-corpus σ change. '
            'A > 1 means cell A becomes relatively more variable under shift; '
            'A < 1 means cell A becomes relatively less variable. '
            'For BASELINE-vs-T6_T1 with BASELINE in slot a: A < 1 supports '
            'the "T6_T1 stabilises under shift" claim.'
        ),
    }


def levene_test(fws_a: List[float], fws_b: List[float]) -> Dict:
    """Levene's test for equality of variances (non-parametric sanity check)."""
    try:
        from scipy.stats import levene
        stat, p = levene(fws_a, fws_b, center='median')
        return {'statistic': float(stat), 'p_value': float(p)}
    except ImportError:
        return {'statistic': None, 'p_value': None,
                'note': 'scipy.stats.levene not available; install scipy'}


# ─────────────────────────────────────────────────────────────────────────
# Driver

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--atepp-runs-dir',
                    default='phase1_beat_classical/runs',
                    help='ATEPP-canonical Phase I runs directory')
    ap.add_argument('--bps-fh-eval-json',
                    default='research_data/bps_fh_eval_2026-05-09.json',
                    help='BPS-FH eval JSON (output of eval_bps_fh_from_checkpoints.py)')
    ap.add_argument('--pop909-eval-json',
                    default='research_data/pop909_results_2026-05-09.json',
                    help='POP909 eval JSON (in-domain; output of '
                         'eval_pop909_from_checkpoints.py + fix_pop909_per_piece.py)')
    ap.add_argument('--tavern-eval-json',
                    default='research_data/tavern_eval_2026-05-09.json',
                    help='TAVERN eval JSON (cross-corpus zero-shot; output of '
                         'eval_tavern_from_checkpoints.py)')
    ap.add_argument('--skip-pop909', action='store_true',
                    help='Skip POP909 (e.g., if its eval JSON is unavailable)')
    ap.add_argument('--skip-tavern', action='store_true')
    ap.add_argument('--n-boot', type=int, default=10_000,
                    help='Bootstrap resample count (default 10000)')
    ap.add_argument('--n-perm', type=int, default=10_000,
                    help='Permutation count for σ-asymmetry test (default 10000)')
    ap.add_argument('--seed', type=int, default=20260509,
                    help='RNG seed (default 20260509 = today)')
    ap.add_argument('--output-json',
                    default='research_data/sigma_collapse_formal_tests_2026-05-09.json')
    ap.add_argument('--output-md',
                    default='research_data/sigma_collapse_formal_tests_2026-05-09.md')
    args = ap.parse_args()

    atepp_runs = (HERE / args.atepp_runs_dir).resolve()
    bps_eval = (HERE / args.bps_fh_eval_json).resolve()

    print(f'Loading per-seed FW values...')
    print(f'  ATEPP-41 in-domain runs dir: {atepp_runs}')
    atepp_per_seed = load_atepp_per_seed(atepp_runs)
    print(f'  BPS-FH cross-corpus eval JSON: {bps_eval}')
    bps_per_seed = load_bps_fh_per_seed(bps_eval)

    for v in ('BASELINE', 'T6_T1'):
        if v not in atepp_per_seed or len(atepp_per_seed[v]) != 5:
            raise SystemExit(f'ATEPP {v}: need 5 seeds, got {len(atepp_per_seed.get(v, []))}')
        if v not in bps_per_seed or len(bps_per_seed[v]) != 5:
            raise SystemExit(f'BPS-FH {v}: need 5 seeds, got {len(bps_per_seed.get(v, []))}')

    print(f'  ATEPP BASELINE per-seed FW: {[round(x, 4) for x in atepp_per_seed["BASELINE"]]}')
    print(f'  ATEPP T6_T1    per-seed FW: {[round(x, 4) for x in atepp_per_seed["T6_T1"]]}')
    print(f'  BPS   BASELINE per-seed FW: {[round(x, 4) for x in bps_per_seed["BASELINE"]]}')
    print(f'  BPS   T6_T1    per-seed FW: {[round(x, 4) for x in bps_per_seed["T6_T1"]]}')

    # Load POP909 + TAVERN if available
    extra_per_seed: Dict[str, Dict[str, List[float]]] = {}
    if not args.skip_pop909:
        pop_path = (HERE / args.pop909_eval_json).resolve()
        try:
            extra_per_seed['pop909'] = load_corpus_per_seed(pop_path, 'POP909')
            print(f'  POP909 BASELINE per-seed FW: {[round(x, 4) for x in extra_per_seed["pop909"]["BASELINE"]]}')
            print(f'  POP909 T6_T1    per-seed FW: {[round(x, 4) for x in extra_per_seed["pop909"]["T6_T1"]]}')
        except SystemExit as e:
            print(f'  POP909 SKIPPED: {e}')
    if not args.skip_tavern:
        tav_path = (HERE / args.tavern_eval_json).resolve()
        try:
            extra_per_seed['tavern'] = load_corpus_per_seed(tav_path, 'TAVERN')
            print(f'  TAVERN BASELINE per-seed FW: {[round(x, 4) for x in extra_per_seed["tavern"]["BASELINE"]]}')
            print(f'  TAVERN T6_T1    per-seed FW: {[round(x, 4) for x in extra_per_seed["tavern"]["T6_T1"]]}')
        except SystemExit as e:
            print(f'  TAVERN SKIPPED: {e}')

    # Build the canonical 4-corpus iteration list (preserves ordering).
    # ATEPP-41 is the in-domain reference; the cross-corpus zero-shot tests
    # use ATEPP-canonical checkpoints evaluated on BPS-FH or TAVERN; POP909
    # is in-domain (separately trained) and so participates in the σ-collapse
    # pattern check (a/b/d below) but NOT in the cross-corpus σ-asymmetry test
    # (c) which is a zero-shot-only comparison.
    all_corpora = [('atepp', atepp_per_seed), ('bps_fh', bps_per_seed)]
    if 'pop909' in extra_per_seed:
        all_corpora.append(('pop909', extra_per_seed['pop909']))
    if 'tavern' in extra_per_seed:
        all_corpora.append(('tavern', extra_per_seed['tavern']))

    # ─── (a) Per-cell σ + parametric χ² CI ─────────────────────────────
    print('\n--- (a) Per-cell σ point estimate + parametric χ² 95 % CI ---')
    chi2_results = {}
    for corpus, per_seed_map in all_corpora:
        chi2_results[corpus] = {}
        for v, fws in per_seed_map.items():
            sigma_hat = float(np.std(fws, ddof=1))
            ci_low, ci_high = chi2_sigma_ci(sigma_hat, n=len(fws))
            chi2_results[corpus][v] = {
                'sigma_hat': sigma_hat,
                'n': len(fws),
                'chi2_ci_95': [ci_low, ci_high],
            }
            print(f'  {corpus:8s} {v:12s} σ̂ = {sigma_hat:.4f}  '
                  f'(χ² 95 % CI [{ci_low:.4f}, {ci_high:.4f}])')

    # ─── (b) Per-corpus σ-ratio bootstrap ──────────────────────────────
    print('\n--- (b) σ_T6_T1 / σ_BASELINE per-corpus bootstrap (B = '
          f'{args.n_boot}) ---')
    bootstrap_results = {}
    for corpus, per_seed_map in all_corpora:
        # NB: ratio is T6_T1 / BASELINE so SMALLER means more stabilised by T6_T1.
        boot = bootstrap_sigma_ratio(
            per_seed_map['T6_T1'], per_seed_map['BASELINE'],
            n_boot=args.n_boot, seed=args.seed,
        )
        bootstrap_results[corpus] = boot
        verdict = ('T6_T1 σ < BASELINE σ' if boot['ci_high_95'] < 1
                   else 'cannot distinguish from σ_T6_T1 = σ_BASELINE')
        print(f'  {corpus:8s}  σ_T6_T1 / σ_BASELINE = {boot["observed_ratio"]:.4f}  '
              f'95 % CI [{boot["ci_low_95"]:.4f}, {boot["ci_high_95"]:.4f}]  '
              f'fraction_below_1 = {boot["fraction_below_1"]:.4f}  '
              f'→ {verdict}')

    # ─── (c) Cross-corpus σ-asymmetry permutation test ──────────────────
    # The asymmetry test compares HOW σ changes under cross-corpus zero-shot
    # transfer. ATEPP is the in-domain reference; BPS-FH and TAVERN are the
    # zero-shot comparisons. POP909 is in-domain (separately trained) and is
    # excluded — its σ-change is not a "shift" in the same sense as zero-shot.
    #
    # For 1 zero-shot comparison (BPS-FH only): the original 2-corpus
    # permutation test as before.
    # For 2 zero-shot comparisons (BPS-FH + TAVERN): we test the COMBINED
    # asymmetry — the geometric mean of the two A statistics — under the
    # null that "BASELINE σ-change == T6_T1 σ-change at each of the 2
    # cross-corpus shifts." This effectively halves the permutation noise.
    print(f'\n--- (c) Cross-corpus σ-asymmetry permutation test (n_perm = '
          f'{args.n_perm}) ---')
    cross_corpora = []
    if 'tavern' in extra_per_seed:
        cross_corpora.append(('tavern', extra_per_seed['tavern']))
    cross_corpora.insert(0, ('bps_fh', bps_per_seed))  # bps_fh first

    perm_per_pair = {}
    log_As = []
    for cross_name, cross_data in cross_corpora:
        perm = cross_corpus_asymmetry_permutation(
            atepp_per_seed['BASELINE'], atepp_per_seed['T6_T1'],
            cross_data['BASELINE'], cross_data['T6_T1'],
            n_perm=args.n_perm, seed=args.seed,
        )
        perm_per_pair[f'atepp_vs_{cross_name}'] = perm
        if perm['observed_log_A'] is not None and not math.isnan(perm['observed_log_A']):
            log_As.append(perm['observed_log_A'])
        print(f'  ATEPP vs {cross_name}: A = {perm["observed_A"]:.4f}, '
              f'p = {perm["p_two_sided"]:.4f}')

    # Combined asymmetry: geometric mean of the per-pair log A statistics
    # under permutation of cell labels jointly. Stronger test if both
    # pairs show A > 1 in the same direction.
    perm = {'per_pair': perm_per_pair}
    if len(cross_corpora) >= 2 and len(log_As) >= 2:
        # Combined asymmetry statistic
        combined_log_A = float(np.mean(log_As))
        combined_A = math.exp(combined_log_A)
        # Permutation: jointly permute cell labels in ATEPP + each comparison corpus
        rng = np.random.default_rng(args.seed)
        atepp_a = np.asarray(atepp_per_seed['BASELINE'])
        atepp_b = np.asarray(atepp_per_seed['T6_T1'])
        n = len(atepp_a)
        perm_combined_log_As = []
        for _ in range(args.n_perm):
            atepp_swap = rng.integers(0, 2, size=n).astype(bool)
            new_atepp_a = np.where(atepp_swap, atepp_b, atepp_a)
            new_atepp_b = np.where(atepp_swap, atepp_a, atepp_b)
            log_As_perm = []
            for _, cross_data in cross_corpora:
                cross_a = np.asarray(cross_data['BASELINE'])
                cross_b = np.asarray(cross_data['T6_T1'])
                cross_swap = rng.integers(0, 2, size=n).astype(bool)
                new_cross_a = np.where(cross_swap, cross_b, cross_a)
                new_cross_b = np.where(cross_swap, cross_a, cross_b)
                sa_atepp = float(np.std(new_atepp_a, ddof=1))
                sb_atepp = float(np.std(new_atepp_b, ddof=1))
                sa_cross = float(np.std(new_cross_a, ddof=1))
                sb_cross = float(np.std(new_cross_b, ddof=1))
                if min(sa_atepp, sb_atepp, sa_cross, sb_cross) < 1e-12:
                    continue
                A = (sa_cross / sa_atepp) / (sb_cross / sb_atepp)
                if A > 0:
                    log_As_perm.append(math.log(A))
            if len(log_As_perm) >= 2:
                perm_combined_log_As.append(float(np.mean(log_As_perm)))
        perm_combined_log_As = np.asarray(perm_combined_log_As)
        if len(perm_combined_log_As) > 0:
            p_combined = float(np.mean(np.abs(perm_combined_log_As) >= abs(combined_log_A)))
        else:
            p_combined = float('nan')
        perm['combined'] = {
            'observed_log_A_geomean': combined_log_A,
            'observed_A_geomean': combined_A,
            'p_two_sided': p_combined,
            'n_pairs': len(cross_corpora),
            'n_perm_valid': len(perm_combined_log_As),
        }
        print(f'\n  COMBINED ({len(cross_corpora)} cross-corpus pairs):')
        print(f'    geomean A = {combined_A:.4f}  (log = {combined_log_A:+.4f})')
        print(f'    Two-sided p (on |geomean log A|): {p_combined:.4f}')

    # ─── (d) Levene's variance-equality test per corpus ────────────────
    print('\n--- (d) Levene\'s test for σ_T6_T1 = σ_BASELINE per corpus ---')
    levene_results = {}
    for corpus, per_seed_map in all_corpora:
        lev = levene_test(per_seed_map['T6_T1'], per_seed_map['BASELINE'])
        levene_results[corpus] = lev
        if lev['p_value'] is not None:
            print(f'  {corpus:8s}  W = {lev["statistic"]:.4f}  p = {lev["p_value"]:.4f}  '
                  f'({"reject σ equality" if lev["p_value"] < 0.05 else "fail to reject"})')
        else:
            print(f'  {corpus:8s}  scipy.stats.levene unavailable')

    # ─── Save JSON + Markdown ───────────────────────────────────────────
    per_seed_FW_out = {
        'atepp': {v: list(fws) for v, fws in atepp_per_seed.items() if v in ('BASELINE', 'T6_T1')},
        'bps_fh': bps_per_seed,
    }
    if 'pop909' in extra_per_seed:
        per_seed_FW_out['pop909'] = extra_per_seed['pop909']
    if 'tavern' in extra_per_seed:
        per_seed_FW_out['tavern'] = extra_per_seed['tavern']
    out_doc = {
        'date': '2026-05-09',
        'rng_seed': args.seed,
        'n_boot': args.n_boot,
        'n_perm': args.n_perm,
        'per_seed_FW': per_seed_FW_out,
        'sigma_chi2_ci': chi2_results,
        'sigma_ratio_bootstrap': bootstrap_results,
        'cross_corpus_asymmetry_permutation': perm,
        'levene_test': levene_results,
    }
    out_json = HERE / args.output_json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out_doc, indent=2))

    # Markdown
    md = ['# σ-collapse formal tests — 2026-05-09', '']
    md.append(f'**RNG seed:** {args.seed}; bootstrap B = {args.n_boot}; '
              f'permutation N = {args.n_perm}')
    md.append('')
    md.append('## (a) Per-cell σ point estimate + parametric χ² 95 % CI')
    md.append('')
    md.append('| Corpus | Cell | n | σ̂ (sample sd, ddof=1) | χ² 95 % CI |')
    md.append('|---|---|---:|---:|---:|')
    corpus_labels = [
        ('ATEPP-41 (in-domain)', 'atepp'),
        ('BPS-FH (cross-corpus zero-shot)', 'bps_fh'),
        ('POP909 (in-domain)', 'pop909'),
        ('TAVERN (cross-corpus zero-shot)', 'tavern'),
    ]
    for corpus_name, key in corpus_labels:
        if key not in chi2_results:
            continue
        for v in ('BASELINE', 'T6_T1'):
            if v not in chi2_results[key]:
                continue
            r = chi2_results[key][v]
            md.append(f'| {corpus_name} | {v} | {r["n"]} | {r["sigma_hat"]:.4f} | '
                      f'[{r["chi2_ci_95"][0]:.4f}, {r["chi2_ci_95"][1]:.4f}] |')
    md.append('')
    md.append('## (b) σ-ratio bootstrap per corpus')
    md.append('')
    md.append('Tests "is σ_T6_T1 / σ_BASELINE < 1?" — i.e. is T6_T1 stabilising?')
    md.append('')
    md.append('| Corpus | σ_T6_T1 | σ_BASELINE | Ratio | 95 % CI | P(ratio < 1) |')
    md.append('|---|---:|---:|---:|---:|---:|')
    for corpus_name, key in corpus_labels:
        if key not in bootstrap_results:
            continue
        r = bootstrap_results[key]
        md.append(f'| {corpus_name} | {r["sigma_a"]:.4f} | {r["sigma_b"]:.4f} | '
                  f'{r["observed_ratio"]:.4f} | [{r["ci_low_95"]:.4f}, '
                  f'{r["ci_high_95"]:.4f}] | {r["fraction_below_1"]:.4f} |')
    md.append('')
    md.append('## (c) Cross-corpus σ-asymmetry permutation test')
    md.append('')
    md.append('Tests "is the σ change under distribution shift symmetric across cells?"')
    md.append('Asymmetry statistic A = (σ_BASELINE_cross / σ_BASELINE_ATEPP) / '
              '(σ_T6_T1_cross / σ_T6_T1_ATEPP).')
    md.append('A > 1 means BASELINE σ inflates relative to T6_T1 σ under shift.')
    md.append('')
    md.append('**Per-pair (each cross-corpus zero-shot vs ATEPP-41 in-domain):**')
    md.append('')
    md.append('| Comparison | Observed A | log A | Two-sided *p* |')
    md.append('|---|---:|---:|---:|')
    for pair_key, pair_perm in perm.get('per_pair', {}).items():
        nice = pair_key.replace('atepp_vs_', 'ATEPP vs ').replace('bps_fh', 'BPS-FH').replace('tavern', 'TAVERN')
        log_a = pair_perm.get('observed_log_A')
        log_a_s = f'{log_a:+.4f}' if (log_a is not None and not math.isnan(log_a)) else '—'
        md.append(f'| {nice} | {pair_perm["observed_A"]:.4f} | '
                  f'{log_a_s} | {pair_perm["p_two_sided"]:.4f} |')
    md.append('')
    if 'combined' in perm:
        c = perm['combined']
        md.append(f'**Combined ({c["n_pairs"]} cross-corpus pairs, geometric-mean A):**')
        md.append('')
        md.append(f'- **Geomean A = {c["observed_A_geomean"]:.4f}** '
                  f'(log = {c["observed_log_A_geomean"]:+.4f})')
        md.append(f'- **Two-sided permutation p: {c["p_two_sided"]:.4f}** '
                  f'(N = {c["n_perm_valid"]} valid permutations)')
        md.append('')
        if c['p_two_sided'] < 0.05:
            md.append('Verdict: **REJECT the null of symmetric cross-corpus σ change** '
                      'at α = 0.05. The σ-asymmetry observation '
                      '(BASELINE σ inflates more than T6_T1 σ under cross-corpus '
                      'shift) is statistically distinguishable from null across '
                      f'{c["n_pairs"]} zero-shot test corpora.')
        else:
            md.append('Verdict: **fail to reject the null** at α = 0.05. The '
                      f'σ-asymmetry is descriptive across {c["n_pairs"]} cross-corpus '
                      'pairs; further corpora (e.g., Schubert, Brahms) would help '
                      'gain power.')
    md.append('')
    md.append('## (d) Levene\'s test for σ equality per corpus')
    md.append('')
    md.append("Non-parametric sanity check: H_0 is σ_T6_T1 = σ_BASELINE.")
    md.append('')
    md.append('| Corpus | Levene W | p-value | Verdict at α = 0.05 |')
    md.append('|---|---:|---:|---|')
    for corpus_name, key in corpus_labels:
        if key not in levene_results:
            continue
        lev = levene_results[key]
        if lev.get('p_value') is not None:
            verd = 'reject σ equality' if lev['p_value'] < 0.05 else 'fail to reject'
            md.append(f'| {corpus_name} | {lev["statistic"]:.4f} | {lev["p_value"]:.4f} | {verd} |')
        else:
            md.append(f'| {corpus_name} | — | — | scipy.stats.levene unavailable |')
    md.append('')
    md.append('---')
    md.append('')
    md.append('*Compiled by `compute_sigma_ratio_bootstrap.py` 2026-05-09. '
              'Closes R1.1 of POSTDOC_REVIEWER_PASS_2026-05-09.md.*')

    out_md = HERE / args.output_md
    out_md.write_text('\n'.join(md) + '\n')

    print(f'\n✓ Wrote {out_json}')
    print(f'✓ Wrote {out_md}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
