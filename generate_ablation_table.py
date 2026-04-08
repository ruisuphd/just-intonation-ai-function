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

    # Classical baselines
    classical = load_result('classical_baseline_eval.json')
    if classical:
        for method in ['krumhansl_kessler', 'temperley', 'albrecht_shanahan', 'ensemble']:
            if method in classical:
                r = classical[method]
                rows.append({
                    'row_id': f'B_{method[:2].upper()}',
                    'model': method.replace('_', ' ').title(),
                    'augment': '--', 'weight': '--',
                    'mirex': r['overall_mirex'],
                    'ci': r.get('bootstrap_ci'),
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

    for exp_id in ['A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9']:
        data = load_result(f'ablation_{exp_id}_eval.json')
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

        rows.append({
            'row_id': exp_id,
            'model': f'{model_type} ({exp_id})',
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


def print_markdown_table(rows: List[Dict]) -> None:
    print('\n## Ablation Study: Key Detection on ATEPP-319 Balanced Test Set\n')
    print(f'| Row | Model | Aug. | Weight | MIREX (95% CI) | Accuracy | Major | Minor | n |')
    print(f'|-----|-------|------|--------|----------------|----------|-------|-------|---|')
    for r in rows:
        mirex_str = format_mirex_ci(r['mirex'], r['ci'])
        major = f'{r["major_acc"]:.3f}' if r['major_acc'] is not None else '--'
        minor = f'{r["minor_acc"]:.3f}' if r['minor_acc'] is not None else '--'
        print(f'| {r["row_id"]} | {r["model"]} | {r["augment"]} | {r["weight"]} | '
              f'{mirex_str} | {r["accuracy"]:.3f} | {major} | {minor} | {r["n"]:,} |')


def print_latex_table(rows: List[Dict]) -> None:
    print(r'\begin{table}[htbp]')
    print(r'\centering')
    print(r'\caption{Ablation study on ATEPP-319 balanced test set.}')
    print(r'\label{tab:ablation}')
    print(r'\begin{tabular}{llcccccc}')
    print(r'\toprule')
    print(r'Row & Model & Aug. & Weight & MIREX (95\% CI) & Acc. & Major & Minor \\')
    print(r'\midrule')
    for r in rows:
        mirex_str = format_mirex_ci(r['mirex'], r['ci']).replace('--', '--')
        major = f'{r["major_acc"]:.3f}' if r['major_acc'] is not None else '--'
        minor = f'{r["minor_acc"]:.3f}' if r['minor_acc'] is not None else '--'
        print(f'{r["row_id"]} & {r["model"]} & {r["augment"]} & {r["weight"]} & '
              f'{mirex_str} & {r["accuracy"]:.3f} & {major} & {minor} \\\\')
    print(r'\bottomrule')
    print(r'\end{tabular}')
    print(r'\end{table}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate thesis ablation tables')
    parser.add_argument('--format', choices=['markdown', 'latex', 'both'], default='both')
    args = parser.parse_args()

    rows = collect_results()
    if not rows:
        print('No results found. Run experiments first.')
        return

    print(f'Found {len(rows)} result rows.')
    if args.format in ('markdown', 'both'):
        print_markdown_table(rows)
    if args.format in ('latex', 'both'):
        print('\n')
        print_latex_table(rows)


if __name__ == '__main__':
    main()
