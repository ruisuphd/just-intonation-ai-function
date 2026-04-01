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
from typing import Dict

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
    load_split_ids,
)


def _find_composer_ids(
    label_dir: str, test_ids: list, composers: set,
) -> list:
    """Find composition IDs in the test set matching target composers.

    Reads the label JSON files to check for composer metadata.
    Falls back to filename heuristics if metadata is absent.
    """
    matching = []
    for cid in test_ids:
        path = os.path.join(label_dir, f'{cid:04d}.json')
        if not os.path.isfile(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            composer = data.get('composer', '').lower()
            if any(c in composer for c in composers):
                matching.append(cid)
        except (json.JSONDecodeError, KeyError):
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
        return {'loss': float('nan'), 'accuracy': 0.0, 'mirex_weighted_score': 0.0}

    return {
        'loss': total_loss / max(batches, 1),
        'accuracy': total_correct / total_count,
        'mirex_weighted_score': total_mirex / total_count,
        'total_predictions': total_count,
        'confusion_matrix': confusion,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Evaluate a trained harmonic-context model',
    )
    parser.add_argument('--splits', default=DEFAULT_SPLITS)
    parser.add_argument('--label-dir', default=DEFAULT_LABEL_DIR)
    parser.add_argument('--checkpoint', default=DEFAULT_CHECKPOINT)
    parser.add_argument('--output', default=DEFAULT_OUTPUT)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--window-size', type=int, default=256)
    parser.add_argument('--window-hop', type=int, default=128)
    parser.add_argument('--device', default='cpu')
    parser.add_argument(
        '--model-type', choices=['gru', 'transformer'], default='gru',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = torch.device(args.device)

    split_ids = load_split_ids(args.splits)
    validation_records = load_records(args.label_dir, split_ids['validation'])
    test_records = load_records(args.label_dir, split_ids['test'])

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
        model = HarmonicContextGRU().to(device)
    model.load_state_dict(checkpoint['model_state_dict'])

    loss_fn = nn.CrossEntropyLoss(ignore_index=-100)

    print(f'Model: {args.model_type}, Checkpoint: {args.checkpoint}')

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

    # --- Tonicization-subset evaluation ---
    # Schubert and Debussy are the most tonicization-heavy composers in ATEPP.
    # Evaluate separately to measure performance on chromatic passages.
    tonic_metrics = None
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

    payload = {
        'checkpoint': args.checkpoint,
        'model_type': args.model_type,
        'validation': {k: v for k, v in validation_metrics.items() if k != 'confusion_matrix'},
        'test': test_metrics,
    }
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
