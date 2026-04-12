#!/usr/bin/env python3
"""
Generate thesis-ready ablation tables from evaluation results.

Reads all evaluation JSONs and produces formatted tables in LaTeX and Markdown.

Usage:
    python generate_ablation_table.py
    python generate_ablation_table.py --format latex
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, 'research_data')


def load_result(filename: str) -> Optional[Dict]:
    path = os.path.join(RESULTS_DIR, filename)
    if not os.path.isfile(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)


def format_mirex_ci(mirex: float, ci: Optional[Dict]) -> str:
    if ci:
        return f'{mirex:.3f} ({ci["mirex_ci_lower"]:.3f}--{ci["mirex_ci_upper"]:.3f})'
    return f'{mirex:.3f}'


def collect_results() -> List[Dict]:
    rows = []

    # Classical baselines (legacy: own test set, profile correlation only)
    classical = load_result('classical_baseline_eval.json')
    if classical:
        # Updated method list to include the new Bellman-Budge, Aarden-Essen,
        # and 5-profile ensemble (added 2026-04-12 from Nápoles 2019).
        for method in ['krumhansl_kessler', 'temperley', 'albrecht_shanahan',
                       'bellman_budge', 'aarden_essen', 'ensemble', 'ensemble_5']:
            if method in classical:
                r = classical[method]
                # Pretty row IDs: B_KK, B_TE, B_AS, B_BB, B_AE, B_EN, B_E5
                row_id_map = {
                    'krumhansl_kessler': 'B_KK', 'temperley': 'B_TE',
                    'albrecht_shanahan': 'B_AS', 'bellman_budge': 'B_BB',
                    'aarden_essen': 'B_AE', 'ensemble': 'B_EN', 'ensemble_5': 'B_E5',
                }
                rows.append({
                    'row_id': row_id_map.get(method, f'B_{method[:2].upper()}'),
                    'model': method.replace('_', ' ').title(),
                    'augment': '--', 'weight': '--',
                    'mirex': r['overall_mirex'],
                    'ci': r.get('bootstrap_ci'),
                    'accuracy': r['overall_accuracy'],
                    'major_acc': None, 'minor_acc': None,
                    'n': r['total_predictions'],
                })

    # Aligned classical baseline (fair classical-vs-neural comparison)
    aligned = load_result('classical_baseline_aligned.json')
    if aligned and 'methods' in aligned:
        for method, r in aligned['methods'].items():
            row_id_map = {
                'krumhansl_kessler': 'BA_KK', 'temperley': 'BA_TE',
                'albrecht_shanahan': 'BA_AS', 'bellman_budge': 'BA_BB',
                'aarden_essen': 'BA_AE', 'ensemble': 'BA_EN', 'ensemble_5': 'BA_E5',
            }
            rows.append({
                'row_id': row_id_map.get(method, f'BA_{method[:2].upper()}'),
                'model': f'{method.replace("_", " ").title()} (aligned)',
                'augment': '--', 'weight': '--',
                'mirex': r['overall_mirex'],
                'ci': r.get('bootstrap_ci'),
                'accuracy': r['overall_accuracy'],
                'major_acc': None, 'minor_acc': None,
                'n': r['total_predictions'],
            })

    # Justkeydding HMM results (Nápoles 2019, ported to Python)
    jkd_hmm = load_result('justkeydding_hmm_eval.json')
    if jkd_hmm and 'profiles' in jkd_hmm:
        transition = jkd_hmm.get('transition', '?')
        for profile, r in jkd_hmm['profiles'].items():
            row_id_map = {
                'krumhansl_kessler': 'JKD_KK', 'temperley': 'JKD_TE',
                'albrecht_shanahan': 'JKD_AS', 'bellman_budge': 'JKD_BB',
                'aarden_essen': 'JKD_AE',
            }
            rows.append({
                'row_id': row_id_map.get(profile, f'JKD_{profile[:2].upper()}'),
                'model': f'JKD HMM {profile.replace("_", " ").title()} ({transition})',
                'augment': '--', 'weight': 'HMM',
                'mirex': r['overall_mirex'],
                'ci': None,  # HMM eval doesn't currently store bootstrap CI
                'accuracy': r['overall_accuracy'],
                'major_acc': None, 'minor_acc': None,
                'n': r['total_predictions'],
            })

    # Existing baselines
    for label, filename in [
        ('GRU 24-key balanced', 'gru_24key_eval.json'),
        ('Transformer+S-KEY PT', 'transformer_24key_pretrained_eval.json'),
        ('Transformer no-PT', 'transformer_24key_nopretrain_eval.json'),
    ]:
        data = load_result(filename)
        if data is None:
            continue
        test = data.get('test', {})
        classes = data.get('class_metrics', {})
        rows.append({
            'row_id': f'E_{label[:6]}',
            'model': label, 'augment': '?', 'weight': '?',
            'mirex': test.get('mirex_weighted_score', 0),
            'ci': data.get('bootstrap_ci'),
            'accuracy': test.get('accuracy', 0),
            'major_acc': classes.get('mean_major_accuracy'),
            'minor_acc': classes.get('mean_minor_accuracy'),
            'n': test.get('total_predictions', 0),
        })

    # Ablation results (Phase 1 + Phase 2)
    # Load all available summaries for config lookup
    phase1_summary = load_result('ablation_summary.json') or []
    phase2_summary = load_result('phase2_ablation_summary.json') or []
    all_summaries = phase1_summary + phase2_summary

    # A1's eval JSON is named ablation_A1_eval_softmax.json after Phase 2 re-eval
    eval_filename_overrides = {
        'A1': 'ablation_A1_eval_softmax.json',
    }
    for exp_id in ['A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'A10', 'A11']:
        fname = eval_filename_overrides.get(exp_id, f'ablation_{exp_id}_eval.json')
        data = load_result(fname)
        if data is None:
            continue
        test = data.get('test', {})
        classes = data.get('class_metrics', {})
        config = None
        for entry in all_summaries:
            if entry.get('exp_id') == exp_id:
                config = entry.get('config', {})
                break

        # Build model name with architecture details
        model_type = config.get('model_type', '?').upper() if config else '?'
        extras = []
        if config and config.get('bidirectional'):
            extras.append('Bi')
            model_type = f'Bi{model_type}'
        if config and config.get('gru_pcp'):
            extras.append('+PCP')
            model_type += '+PCP'
        if config and config.get('focal_loss'):
            extras.append('focal')

        # Mark bidirectional models with dagger: non-causal, offline upper bound only
        is_bidirectional = config and config.get('bidirectional', False)
        model_label = f'{model_type} ({exp_id})'
        if is_bidirectional:
            model_label += r' $\dagger$' if False else ' \u2020'  # Unicode dagger for markdown

        rows.append({
            'row_id': exp_id,
            'model': model_label,
            'augment': 'Yes' if config and not config.get('no_augment') else 'No' if config else '?',
            'weight': ('focal' if config and config.get('focal_loss')
                       else config.get('weight_mode', '?') if config else '?'),
            'mirex': test.get('mirex_weighted_score', 0),
            'ci': data.get('bootstrap_ci'),
            'accuracy': test.get('accuracy', 0),
            'major_acc': classes.get('mean_major_accuracy'),
            'minor_acc': classes.get('mean_minor_accuracy'),
            'n': test.get('total_predictions', 0),
        })

    # Post-processing results
    hmm = load_result('hmm_postprocessing_eval.json')
    if hmm:
        rows.append({
            'row_id': 'PP_HMM', 'model': 'Best + HMM',
            'augment': '--', 'weight': '--',
            'mirex': hmm.get('hmm_mirex', 0), 'ci': None,
            'accuracy': hmm.get('hmm_accuracy', 0),
            'major_acc': None, 'minor_acc': None,
            'n': hmm.get('total_predictions', 0),
        })

    ens = load_result('ensemble_eval.json')
    if ens:
        rows.append({
            'row_id': 'PP_ENS',
            'model': f'Neural+Classical (a={ens.get("alpha", "?")})',
            'augment': '--', 'weight': '--',
            'mirex': ens.get('ensemble_mirex', 0), 'ci': None,
            'accuracy': ens.get('ensemble_accuracy', 0),
            'major_acc': None, 'minor_acc': None,
            'n': ens.get('total_predictions', 0),
        })

    return rows


def render_markdown_table(rows: List[Dict]) -> str:
    """Render the markdown table to a string (for both stdout and disk save)."""
    lines = []
    lines.append('\n## Ablation Study: Key Detection on ATEPP-319 Balanced Test Set\n')
    lines.append(f'| Row | Model | Aug. | Weight | MIREX (95% CI) | Accuracy | Major | Minor | n |')
    lines.append(f'|-----|-------|------|--------|----------------|----------|-------|-------|---|')
    has_bidirectional = False
    for r in rows:
        mirex_str = format_mirex_ci(r['mirex'], r['ci'])
        major = f'{r["major_acc"]:.3f}' if r['major_acc'] is not None else '--'
        minor = f'{r["minor_acc"]:.3f}' if r['minor_acc'] is not None else '--'
        if '\u2020' in r['model']:
            has_bidirectional = True
        lines.append(f'| {r["row_id"]} | {r["model"]} | {r["augment"]} | {r["weight"]} | '
                     f'{mirex_str} | {r["accuracy"]:.3f} | {major} | {minor} | {r["n"]:,} |')
    if has_bidirectional:
        lines.append(f'\n\u2020 Non-causal (bidirectional): offline upper bound only, not deployable in the real-time tuner.')
    lines.append(f'\nClassical baseline profiles sourced from Nápoles (2019) "Key-Finding Based on '
                 f'an HMM and Key Profiles," DLfM 2019 (https://github.com/napulen/justkeydding). '
                 f'JKD HMM rows reproduce the algorithm in pure Python.')
    return '\n'.join(lines)


def render_latex_table(rows: List[Dict]) -> str:
    """Render the LaTeX table to a string."""
    lines = []
    lines.append(r'\begin{table}[htbp]')
    lines.append(r'\centering')
    lines.append(r'\caption{Ablation study on ATEPP-319 balanced test set. '
                 r'$\dagger$~Non-causal (bidirectional): offline upper bound, not deployable in real-time. '
                 r'Classical profiles from N\'apoles (2019); JKD HMM rows are our pure-Python port.}')
    lines.append(r'\label{tab:ablation}')
    lines.append(r'\begin{tabular}{llcccccc}')
    lines.append(r'\toprule')
    lines.append(r'Row & Model & Aug. & Weight & MIREX (95\% CI) & Acc. & Major & Minor \\')
    lines.append(r'\midrule')
    for r in rows:
        model_name = r['model'].replace('\u2020', r'$\dagger$').replace('_', r'\_').replace('#', r'\#')
        mirex_str = format_mirex_ci(r['mirex'], r['ci'])
        major = f'{r["major_acc"]:.3f}' if r['major_acc'] is not None else '--'
        minor = f'{r["minor_acc"]:.3f}' if r['minor_acc'] is not None else '--'
        lines.append(f'{r["row_id"]} & {model_name} & {r["augment"]} & {r["weight"]} & '
                     f'{mirex_str} & {r["accuracy"]:.3f} & {major} & {minor} \\\\')
    lines.append(r'\bottomrule')
    lines.append(r'\end{tabular}')
    lines.append(r'\end{table}')
    return '\n'.join(lines)


# Backward-compat wrappers
def print_markdown_table(rows: List[Dict]) -> None:
    print(render_markdown_table(rows))


def print_latex_table(rows: List[Dict]) -> None:
    print(render_latex_table(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate thesis ablation tables')
    parser.add_argument('--format', choices=['markdown', 'latex', 'both'], default='both')
    parser.add_argument('--save', action='store_true', default=False,
                        help='Save markdown to research_data/ablation_table.md and '
                             'LaTeX to research_data/ablation_table.tex (fixes Issue 5).')
    args = parser.parse_args()

    rows = collect_results()
    if not rows:
        print('No results found. Run experiments first.')
        return

    print(f'Found {len(rows)} result rows.')
    md_text = render_markdown_table(rows)
    tex_text = render_latex_table(rows)

    if args.format in ('markdown', 'both'):
        print(md_text)
    if args.format in ('latex', 'both'):
        print('\n')
        print(tex_text)

    if args.save:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        md_path = os.path.join(RESULTS_DIR, 'ablation_table.md')
        tex_path = os.path.join(RESULTS_DIR, 'ablation_table.tex')
        with open(md_path, 'w') as f:
            f.write(md_text)
        with open(tex_path, 'w') as f:
            f.write(tex_text)
        print(f'\nSaved markdown to {md_path}')
        print(f'Saved LaTeX to {tex_path}')


if __name__ == '__main__':
    main()
