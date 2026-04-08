#!/usr/bin/env python3
"""
Evaluate a trained harmonic-context model on held-out splits.

Supports both GRU baseline and SymbolicKeyTransformer.
Reports: accuracy, MIREX weighted score, confusion matrix, tonicization subset.
"""

from __future__ import annotations

import argparse
import json
import os
import random
from typing import Dict, List, Tuple

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from harmonic_context_model import (
    HarmonicContextGRU,
    SymbolicKeyTransformer,
    KEY_LABELS,
    collate_harmonic_batch,
)
from train_harmonic_context_model import (
    HarmonicLabelDataset,
    _get_key_logits,
    load_records,
    load_records_from_manifest,
    load_split_ids,
)


def _find_composer_ids(
    label_dir: str, test_ids: list, composers: set,
) -> list:
    """Find composition IDs in the test set matching target composers.

    Reads the label JSON files to check for composer metadata.
    Logs warnings for malformed or missing files.
    """
    matching = []
    for cid in test_ids:
        path = os.path.join(label_dir, f'{cid:04d}.json')
        if not os.path.isfile(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                print(f'[WARN] {path}: expected JSON object, got {type(data).__name__}')
                continue
            composer = data.get('composer')
            if not composer or not isinstance(composer, str):
                continue
            if any(c in composer.lower() for c in composers):
                matching.append(cid)
        except (json.JSONDecodeError, IOError) as exc:
            print(f'[WARN] {path}: {exc}')
            continue
    return matching


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SPLITS = os.path.join(BASE_DIR, 'research_data', 'composition_splits.json')
DEFAULT_LABEL_DIR = os.path.join(BASE_DIR, 'research_data', 'score_key_labels')
DEFAULT_CHECKPOINT = os.path.join(BASE_DIR, 'research_data', 'harmonic_context_model.pt')
DEFAULT_OUTPUT = os.path.join(BASE_DIR, 'research_data', 'harmonic_context_eval.json')


def mirex_weighted_score(predicted_idx: int, true_idx: int) -> float:
    """MIREX key evaluation metric.

    Scoring:
      Exact match = 1.0
      Fifth relation (same mode, root 5 or 7 semitones apart) = 0.5
      Relative key (different mode, root 3 or 9 semitones apart) = 0.3
      Parallel key (same root, different mode) = 0.2
      Other = 0.0

    Key indices: 0-11 = C..B major, 12-23 = Cm..Bm minor.
    """
    if predicted_idx == true_idx:
        return 1.0

    pred_pc = predicted_idx % 12
    true_pc = true_idx % 12
    pred_minor = predicted_idx >= 12
    true_minor = true_idx >= 12
    pc_diff = (pred_pc - true_pc) % 12

    if pred_pc == true_pc and pred_minor != true_minor:
        return 0.2

    if pred_minor == true_minor and pc_diff in (5, 7):
        return 0.5

    if pred_minor != true_minor and pc_diff in (3, 9):
        return 0.3

    return 0.0


def evaluate_extended(
    model: nn.Module,
    loader: DataLoader,
    loss_fn: nn.Module,
    device: str,
) -> Dict[str, object]:
    """Evaluate with accuracy, MIREX, and confusion matrix."""
    model.eval()
    total_loss = 0.0
    total_correct = 0
    total_mirex = 0.0
    total_count = 0
    batches = 0
    confusion = [[0] * 24 for _ in range(24)]

    with torch.no_grad():
        for batch in loader:
            batch = {
                k: v.to(device) if isinstance(v, torch.Tensor) else v
                for k, v in batch.items()
            }
            logits = _get_key_logits(model(batch))
            labels = batch['labels']
            loss = loss_fn(
                logits.view(-1, logits.shape[-1]), labels.view(-1),
            )
            total_loss += loss.item()
            batches += 1

            predictions = logits.argmax(dim=-1)
            mask = labels != -100

            for pred, true in zip(
                predictions[mask].cpu().tolist(),
                labels[mask].cpu().tolist(),
            ):
                total_count += 1
                if pred == true:
                    total_correct += 1
                total_mirex += mirex_weighted_score(pred, true)
                confusion[true][pred] += 1

    if total_count == 0:
        return {'loss': float('nan'), 'accuracy': 0.0, 'mirex_weighted_score': 0.0,
                'total_predictions': 0, 'confusion_matrix': confusion}

    return {
        'loss': total_loss / max(batches, 1),
        'accuracy': total_correct / total_count,
        'mirex_weighted_score': total_mirex / total_count,
        'total_predictions': total_count,
        'confusion_matrix': confusion,
    }


def compute_per_class_metrics(confusion: list) -> Dict:
    """Compute per-class accuracy and aggregate minor/major metrics."""
    per_class = {}
    for c in range(24):
        total = sum(confusion[c])
        correct = confusion[c][c]
        per_class[KEY_LABELS[c]] = {
            'accuracy': correct / total if total > 0 else 0.0,
            'correct': correct,
            'total': total,
        }
    major_accs = [per_class[KEY_LABELS[c]]['accuracy'] for c in range(12)
                  if per_class[KEY_LABELS[c]]['total'] > 0]
    minor_accs = [per_class[KEY_LABELS[c]]['accuracy'] for c in range(12, 24)
                  if per_class[KEY_LABELS[c]]['total'] > 0]
    return {
        'per_class': per_class,
        'mean_major_accuracy': sum(major_accs) / len(major_accs) if major_accs else 0.0,
        'mean_minor_accuracy': sum(minor_accs) / len(minor_accs) if minor_accs else 0.0,
        'num_major_classes_with_data': len(major_accs),
        'num_minor_classes_with_data': len(minor_accs),
    }


def evaluate_per_composition(
    model: nn.Module,
    records: List[Dict],
    device: str,
    window_size: int = 256,
    window_hop: int = 128,
    batch_size: int = 16,
) -> List[Dict]:
    """Return per-composition metrics for bootstrap CI and McNemar tests."""
    model.eval()
    results = []

    for record in records:
        comp_id = record.get('composition_id', record.get('piece_id', 'unknown'))
        dataset = HarmonicLabelDataset(
            [record], augment=False, window_size=window_size, window_hop=window_hop,
        )
        if len(dataset) == 0:
            continue
        loader = DataLoader(
            dataset, batch_size=batch_size, shuffle=False,
            collate_fn=collate_harmonic_batch,
        )
        preds_and_trues = []
        softmax_list = []
        with torch.no_grad():
            for batch in loader:
                batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                         for k, v in batch.items()}
                logits = _get_key_logits(model(batch))
                labels = batch['labels']
                predictions = logits.argmax(dim=-1)
                probs = torch.softmax(logits, dim=-1)
                mask = labels != -100
                for p, t in zip(predictions[mask].cpu().tolist(),
                                labels[mask].cpu().tolist()):
                    preds_and_trues.append((p, t))
                # Save softmax: round to 4 decimals to reduce JSON size
                for prob_vec in probs[mask].cpu().tolist():
                    softmax_list.append([round(v, 4) for v in prob_vec])

        if not preds_and_trues:
            continue

        correct = sum(1 for p, t in preds_and_trues if p == t)
        mirex_sum = sum(mirex_weighted_score(p, t) for p, t in preds_and_trues)
        n = len(preds_and_trues)
        results.append({
            'composition_id': comp_id,
            'mirex': mirex_sum / n,
            'accuracy': correct / n,
            'n_predictions': n,
            'predictions': preds_and_trues,
            'softmax': softmax_list,
        })
    return results


def bootstrap_mirex_ci(
    per_composition_results: List[Dict],
    n_bootstrap: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> Dict[str, float]:
    """Bootstrap CI for MIREX, resampling at composition level (correct for hierarchical data)."""
    rng = np.random.RandomState(seed)
    n_comps = len(per_composition_results)

    bootstrap_scores = []
    for _ in range(n_bootstrap):
        indices = rng.choice(n_comps, size=n_comps, replace=True)
        total_mirex = 0.0
        total_notes = 0
        for idx in indices:
            r = per_composition_results[idx]
            total_mirex += r['mirex'] * r['n_predictions']
            total_notes += r['n_predictions']
        bootstrap_scores.append(total_mirex / max(total_notes, 1))

    bootstrap_scores = np.array(bootstrap_scores)
    alpha = (1.0 - ci) / 2.0
    return {
        'mirex_mean': float(np.mean(bootstrap_scores)),
        'mirex_ci_lower': float(np.percentile(bootstrap_scores, 100 * alpha)),
        'mirex_ci_upper': float(np.percentile(bootstrap_scores, 100 * (1 - alpha))),
        'mirex_std': float(np.std(bootstrap_scores)),
        'n_bootstrap': n_bootstrap,
        'n_compositions': n_comps,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Evaluate a trained harmonic-context model',
    )
    parser.add_argument('--splits', default=DEFAULT_SPLITS)
    parser.add_argument('--label-dir', default=DEFAULT_LABEL_DIR)
    parser.add_argument('--manifest', default=None,
                        help='Path to unified_training_manifest.json for multi-source loading')
    parser.add_argument('--label-dirs', default=None,
                        help='Comma-separated label directories (used with --manifest)')
    parser.add_argument('--checkpoint', default=DEFAULT_CHECKPOINT)
    parser.add_argument('--output', default=DEFAULT_OUTPUT)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--window-size', type=int, default=256)
    parser.add_argument('--window-hop', type=int, default=128)
    parser.add_argument('--device', default='cpu')
    parser.add_argument(
        '--model-type', choices=['gru', 'transformer'], default='gru',
    )
    parser.add_argument(
        '--include-synthetic', action='store_true', default=False,
        help='Include Strategy B synthetic data in evaluation (default: skip for meaningful MIREX scores)',
    )
    parser.add_argument(
        '--save-predictions', default=None,
        help='Save per-note predictions to JSON file (for McNemar tests between models)',
    )
    parser.add_argument(
        '--bootstrap-n', type=int, default=1000,
        help='Number of bootstrap iterations for MIREX CI (default: 1000, 0=skip)',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = torch.device(args.device)

    if args.manifest:
        label_dirs = [d.strip() for d in args.label_dirs.split(',')] if args.label_dirs else [args.label_dir]
        print(f'Model: {args.model_type}, Checkpoint: {args.checkpoint}')
        if args.include_synthetic:
            print('NOTE: Including Strategy B synthetic data in evaluation (--include-synthetic flag set)')
        else:
            print('NOTE: Skipping Strategy B synthetic files for meaningful evaluation')

        validation_records, _, val_composition = load_records_from_manifest(
            args.manifest, label_dirs, 'val', include_synthetic=args.include_synthetic
        )
        test_records, _, test_composition = load_records_from_manifest(
            args.manifest, label_dirs, 'test', include_synthetic=args.include_synthetic
        )

        print(f'\nValidation set data composition:')
        print(f'  ATEPP files (real notes):        {val_composition["atepp_files"]:6d} files, {val_composition["atepp_notes"]:8d} notes')
        print(f'  Strategy A files (real scores):  {val_composition["strategy_a_files"]:6d} files, {val_composition["strategy_a_notes"]:8d} notes')
        print(f'  Strategy B files SKIPPED:        {val_composition["strategy_b_files_skipped"]:6d} files, {val_composition["strategy_b_notes_skipped"]:8d} notes')

        print(f'\nTest set data composition:')
        print(f'  ATEPP files (real notes):        {test_composition["atepp_files"]:6d} files, {test_composition["atepp_notes"]:8d} notes')
        print(f'  Strategy A files (real scores):  {test_composition["strategy_a_files"]:6d} files, {test_composition["strategy_a_notes"]:8d} notes')
        print(f'  Strategy B files SKIPPED:        {test_composition["strategy_b_files_skipped"]:6d} files, {test_composition["strategy_b_notes_skipped"]:8d} notes')
    else:
        split_ids = load_split_ids(args.splits)
        validation_records = load_records(args.label_dir, split_ids['validation'])
        test_records = load_records(args.label_dir, split_ids['test'])
        print(f'Model: {args.model_type}, Checkpoint: {args.checkpoint}')

    validation_dataset = HarmonicLabelDataset(
        validation_records, augment=False,
        window_size=args.window_size, window_hop=args.window_hop,
    )
    test_dataset = HarmonicLabelDataset(
        test_records, augment=False,
        window_size=args.window_size, window_hop=args.window_hop,
    )
    validation_loader = DataLoader(
        validation_dataset, batch_size=args.batch_size,
        shuffle=False, collate_fn=collate_harmonic_batch,
    )
    test_loader = DataLoader(
        test_dataset, batch_size=args.batch_size,
        shuffle=False, collate_fn=collate_harmonic_batch,
    )

    checkpoint = torch.load(args.checkpoint, map_location=device, weights_only=True)
    if args.model_type == 'transformer':
        model = SymbolicKeyTransformer().to(device)
    else:
        # Read model config from checkpoint metadata (backwards-compatible)
        bidirectional = checkpoint.get('bidirectional', False)
        gru_pcp = checkpoint.get('gru_pcp', False)
        model = HarmonicContextGRU(
            bidirectional=bidirectional,
            use_pcp=gru_pcp,
        ).to(device)
        if bidirectional:
            print(f'  Model: bidirectional GRU')
        if gru_pcp:
            print(f'  Model: GRU with PCP feature')
    model.load_state_dict(checkpoint['model_state_dict'])

    loss_fn = nn.CrossEntropyLoss(ignore_index=-100)

    validation_metrics = evaluate_extended(model, validation_loader, loss_fn, str(device))
    test_metrics = evaluate_extended(model, test_loader, loss_fn, str(device))

    for name, m in [('Validation', validation_metrics), ('Test', test_metrics)]:
        print(
            f'{name}: loss={m["loss"]:.4f}, '
            f'accuracy={m["accuracy"]:.4f}, '
            f'MIREX={m["mirex_weighted_score"]:.4f}, '
            f'n={m["total_predictions"]}'
        )

    confusion = test_metrics['confusion_matrix']
    confusions = []
    for t in range(24):
        for p in range(24):
            if t != p and confusion[t][p] > 0:
                confusions.append((confusion[t][p], KEY_LABELS[t], KEY_LABELS[p]))
    confusions.sort(reverse=True)
    print('\nTop 10 confusions (test):')
    for count, true_key, pred_key in confusions[:10]:
        print(f'  {true_key} -> {pred_key}: {count}')

    # --- Per-class accuracy breakdown ---
    class_metrics = compute_per_class_metrics(confusion)
    print(f'\nPer-class accuracy (test):')
    print(f'  {"Key":<6} {"Acc":>6} {"Correct":>8} {"Total":>8}')
    print(f'  {"-"*30}')
    for c in range(24):
        m = class_metrics['per_class'][KEY_LABELS[c]]
        marker = ' *' if m['total'] > 0 and m['accuracy'] == 0.0 else ''
        print(f'  {KEY_LABELS[c]:<6} {m["accuracy"]:>6.3f} {m["correct"]:>8} {m["total"]:>8}{marker}')
    print(f'\n  Mean major accuracy: {class_metrics["mean_major_accuracy"]:.4f}')
    print(f'  Mean minor accuracy: {class_metrics["mean_minor_accuracy"]:.4f}')

    # --- Tonicization-subset evaluation ---
    # Schubert and Debussy are the most tonicization-heavy composers in ATEPP.
    # Evaluate separately to measure performance on chromatic passages.
    tonic_metrics = None
    if not args.manifest:
        tonic_composers = {'schubert', 'debussy'}
        tonic_ids = _find_composer_ids(args.label_dir, split_ids['test'], tonic_composers)
        if tonic_ids:
            tonic_records = load_records(args.label_dir, tonic_ids)
            tonic_dataset = HarmonicLabelDataset(
                tonic_records, augment=False,
                window_size=args.window_size, window_hop=args.window_hop,
            )
            tonic_loader = DataLoader(
                tonic_dataset, batch_size=args.batch_size,
                shuffle=False, collate_fn=collate_harmonic_batch,
            )
            tonic_metrics = evaluate_extended(model, tonic_loader, loss_fn, str(device))
            print(
                f'\nTonicization subset ({len(tonic_ids)} compositions, '
                f'{", ".join(sorted(tonic_composers))}): '
                f'accuracy={tonic_metrics["accuracy"]:.4f}, '
                f'MIREX={tonic_metrics["mirex_weighted_score"]:.4f}, '
                f'n={tonic_metrics["total_predictions"]}'
            )

    # --- Bootstrap confidence interval (composition-level resampling) ---
    bootstrap_result = None
    per_comp_results = None
    if args.bootstrap_n > 0:
        print(f'\nComputing bootstrap CI ({args.bootstrap_n} iterations, composition-level)...')
        per_comp_results = evaluate_per_composition(
            model, test_records, str(device),
            window_size=args.window_size, window_hop=args.window_hop,
            batch_size=args.batch_size,
        )
        bootstrap_result = bootstrap_mirex_ci(per_comp_results, n_bootstrap=args.bootstrap_n)
        print(f'  MIREX = {bootstrap_result["mirex_mean"]:.4f} '
              f'(95% CI: {bootstrap_result["mirex_ci_lower"]:.4f}'
              f'–{bootstrap_result["mirex_ci_upper"]:.4f}), '
              f'n_compositions={bootstrap_result["n_compositions"]}')

    # --- Save per-note predictions for McNemar tests ---
    if args.save_predictions:
        if per_comp_results is None:
            per_comp_results = evaluate_per_composition(
                model, test_records, str(device),
                window_size=args.window_size, window_hop=args.window_hop,
                batch_size=args.batch_size,
            )
        pred_payload = {
            'checkpoint': args.checkpoint,
            'model_type': args.model_type,
            'has_softmax': True,
            'compositions': [
                {
                    'composition_id': r['composition_id'],
                    'mirex': r['mirex'],
                    'accuracy': r['accuracy'],
                    'n_predictions': r['n_predictions'],
                    'predictions': r['predictions'],
                    'softmax': r.get('softmax', []),
                }
                for r in per_comp_results
            ],
        }
        os.makedirs(os.path.dirname(args.save_predictions) or '.', exist_ok=True)
        with open(args.save_predictions, 'w', encoding='utf-8') as f:
            json.dump(pred_payload, f)
        print(f'\nSaved per-note predictions to {args.save_predictions}')

    payload = {
        'checkpoint': args.checkpoint,
        'model_type': args.model_type,
        'validation': {k: v for k, v in validation_metrics.items() if k != 'confusion_matrix'},
        'test': test_metrics,
        'class_metrics': class_metrics,
    }
    if bootstrap_result:
        payload['bootstrap_ci'] = bootstrap_result
    if tonic_metrics:
        payload['tonicization_subset'] = {
            k: v for k, v in tonic_metrics.items() if k != 'confusion_matrix'
        }
        payload['tonicization_subset']['composers'] = sorted(tonic_composers)
        payload['tonicization_subset']['composition_ids'] = tonic_ids

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    print(f'\nSaved to {args.output}')


if __name__ == '__main__':
    main()
