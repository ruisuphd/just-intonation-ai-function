#!/usr/bin/env python3
"""
Train the first causal harmonic-state model on score-derived local-key labels.

This script expects label files produced by extract_score_key_labels.py and a
composition-level split manifest produced by build_research_splits.py.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
from typing import Dict, List, Sequence, Tuple

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from harmonic_context_model import (
    HarmonicContextGRU,
    SymbolicKeyTransformer,
    collate_harmonic_batch,
    compute_pcp,
    key_to_index,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SPLITS = os.path.join(BASE_DIR, 'research_data', 'composition_splits.json')
DEFAULT_LABEL_DIR = os.path.join(BASE_DIR, 'research_data', 'score_key_labels')
DEFAULT_CHECKPOINT = os.path.join(BASE_DIR, 'research_data', 'harmonic_context_model.pt')
SEED = 20260309


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Train a causal harmonic-state model')
    parser.add_argument('--splits', default=DEFAULT_SPLITS, help='Path to composition_splits.json')
    parser.add_argument('--label-dir', default=DEFAULT_LABEL_DIR, help='Directory with score key label JSON files')
    parser.add_argument('--epochs', type=int, default=10)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--learning-rate', type=float, default=1e-3)
    parser.add_argument('--window-size', type=int, default=256)
    parser.add_argument('--window-hop', type=int, default=128)
    parser.add_argument('--checkpoint', default=DEFAULT_CHECKPOINT)
    parser.add_argument('--device', default='auto',
                        help='Device: auto, cpu, mps, or cuda (auto picks best available)')
    parser.add_argument(
        '--model-type', choices=['gru', 'transformer'], default='gru',
        help='Model architecture: gru (baseline) or transformer (S-KEY-Symbolic)',
    )
    parser.add_argument(
        '--pretrained-checkpoint', default=None,
        help='Path to self-supervised pretrained weights (transformer only)',
    )
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)


def load_split_ids(split_path: str) -> Dict[str, set]:
    with open(split_path, 'r', encoding='utf-8') as handle:
        payload = json.load(handle)

    return {
        name: {int(item['composition_id']) for item in items}
        for name, items in payload['splits'].items()
    }


def build_active_masks(notes: Sequence[Dict[str, object]]) -> List[List[int]]:
    active_sets: List[List[int]] = []
    active_notes: List[Tuple[float, int]] = []

    for note in notes:
        onset = float(note.get('onset_beat') or 0.0)
        duration = note.get('duration_beat')
        if duration is None:
            duration = 0.25
        duration = float(duration)

        active_notes = [(end_time, pitch) for end_time, pitch in active_notes if end_time > onset]
        active_sets.append([pitch for _, pitch in active_notes])
        active_notes.append((onset + max(duration, 0.05), int(note['pitch'])))

    return active_sets


def beat_to_ms(value: float) -> float:
    return value * 500.0


def maybe_drop_notes(notes: Sequence[Dict[str, object]], drop_probability: float = 0.03) -> List[Dict[str, object]]:
    kept = []
    for idx, note in enumerate(notes):
        if idx > 0 and random.random() < drop_probability:
            continue
        kept.append(note)
    return kept


def maybe_scale_time(notes: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    factor = random.uniform(0.9, 1.1)
    scaled = []
    for note in notes:
        copy = dict(note)
        if copy.get('onset_beat') is not None:
            copy['onset_beat'] = float(copy['onset_beat']) * factor
        if copy.get('duration_beat') is not None:
            copy['duration_beat'] = float(copy['duration_beat']) * factor
        scaled.append(copy)
    return scaled


def notes_to_training_example(notes: Sequence[Dict[str, object]], augment: bool) -> Dict[str, object]:
    if augment:
        notes = maybe_scale_time(maybe_drop_notes(notes))

    active_sets = build_active_masks(notes)

    pitch_class = []
    register = []
    delta_bucket = []
    duration_bucket = []
    velocity_bucket = []
    active_mask = []
    labels = []

    previous_time_ms = None

    for note, active in zip(notes, active_sets):
        pitch = int(note['pitch'])
        onset_beat = float(note.get('onset_beat') or 0.0)
        duration_beat = float(note.get('duration_beat') or 0.25)
        onset_ms = beat_to_ms(onset_beat)
        delta_ms = 0.0 if previous_time_ms is None else max(0.0, onset_ms - previous_time_ms)
        previous_time_ms = onset_ms
        duration_ms = beat_to_ms(duration_beat)

        pitch_class.append(pitch % 12)
        register.append(max(0, min(10, (pitch // 12) - 1)))
        delta_bucket.append(sum(delta_ms > edge for edge in (0, 40, 80, 120, 180, 260, 360, 500, 700, 1000, 1400, 2000, 3000)))
        duration_bucket.append(sum(duration_ms > edge for edge in (0, 40, 80, 120, 180, 260, 360, 500, 700, 1000, 1400, 2000, 4000)))
        velocity_bucket.append(sum(96 > edge for edge in tuple(range(0, 128, 8))))

        mask = [0.0] * 12
        for active_pitch in active:
            mask[int(active_pitch) % 12] = 1.0
        active_mask.append(mask)

        labels.append(key_to_index(str(note['key'])))

    pcp = compute_pcp(pitch_class, window_size=32)

    return {
        'pitch_class': pitch_class,
        'register': register,
        'delta_bucket': delta_bucket,
        'duration_bucket': duration_bucket,
        'velocity_bucket': velocity_bucket,
        'active_mask': active_mask,
        'pcp': pcp,
        'labels': labels,
    }


class HarmonicLabelDataset(Dataset):
    def __init__(
        self,
        records: Sequence[Dict[str, object]],
        augment: bool = False,
        window_size: int = 256,
        window_hop: int = 128,
    ):
        self.windows = []
        self.augment = augment
        self.window_size = window_size
        self.window_hop = window_hop

        for record in records:
            notes = list(record['notes'])
            if not notes:
                continue

            if len(notes) <= window_size:
                self.windows.append(notes)
                continue

            for start_idx in range(0, len(notes) - window_size + 1, window_hop):
                self.windows.append(notes[start_idx:start_idx + window_size])

            if (len(notes) - window_size) % window_hop != 0:
                self.windows.append(notes[-window_size:])

    def __len__(self) -> int:
        return len(self.windows)

    def __getitem__(self, index: int) -> Dict[str, object]:
        return notes_to_training_example(self.windows[index], augment=self.augment)


def load_records(label_dir: str, composition_ids: set) -> List[Dict[str, object]]:
    records = []
    for composition_id in sorted(composition_ids):
        filename = f'{composition_id:04d}.json'
        path = os.path.join(label_dir, filename)
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8') as handle:
            records.append(json.load(handle))
    return records


def masked_accuracy(logits: torch.Tensor, labels: torch.Tensor) -> float:
    predictions = logits.argmax(dim=-1)
    mask = labels != -100
    correct = (predictions[mask] == labels[mask]).sum().item()
    total = mask.sum().item()
    return 0.0 if total == 0 else correct / total


def _get_key_logits(output: object) -> torch.Tensor:
    """Get key logits from model output (GRU returns tensor, Transformer returns dict)."""
    if isinstance(output, dict):
        return output['key_logits']
    return output


def run_evaluation(model: nn.Module, loader: DataLoader, loss_fn: nn.Module, device: str) -> Dict[str, float]:
    model.eval()
    total_loss = 0.0
    total_accuracy = 0.0
    batches = 0

    with torch.no_grad():
        for batch in loader:
            batch = {key: value.to(device) if torch.is_tensor(value) else value for key, value in batch.items()}
            logits = _get_key_logits(model(batch))
            loss = loss_fn(logits.view(-1, logits.shape[-1]), batch['labels'].view(-1))
            total_loss += loss.item()
            total_accuracy += masked_accuracy(logits, batch['labels'])
            batches += 1

    if batches == 0:
        return {'loss': math.nan, 'accuracy': math.nan}

    return {
        'loss': total_loss / batches,
        'accuracy': total_accuracy / batches,
    }


def train_epoch(model: nn.Module, loader: DataLoader, optimizer, loss_fn, device: str) -> Dict[str, float]:
    model.train()
    total_loss = 0.0
    total_accuracy = 0.0
    batches = 0

    for batch in loader:
        batch = {key: value.to(device) if torch.is_tensor(value) else value for key, value in batch.items()}
        optimizer.zero_grad()
        logits = _get_key_logits(model(batch))
        loss = loss_fn(logits.view(-1, logits.shape[-1]), batch['labels'].view(-1))
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        total_accuracy += masked_accuracy(logits, batch['labels'])
        batches += 1

    return {
        'loss': total_loss / max(batches, 1),
        'accuracy': total_accuracy / max(batches, 1),
    }


def main() -> None:
    args = parse_args()
    set_seed(SEED)

    split_ids = load_split_ids(args.splits)
    train_records = load_records(args.label_dir, split_ids['train'])
    validation_records = load_records(args.label_dir, split_ids['validation'])

    train_dataset = HarmonicLabelDataset(
        train_records,
        augment=True,
        window_size=args.window_size,
        window_hop=args.window_hop,
    )
    validation_dataset = HarmonicLabelDataset(
        validation_records,
        augment=False,
        window_size=args.window_size,
        window_hop=args.window_hop,
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate_harmonic_batch,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=collate_harmonic_batch,
    )

    if args.device == 'auto':
        if torch.backends.mps.is_available():
            args.device = 'mps'
        elif torch.cuda.is_available():
            args.device = 'cuda'
        else:
            args.device = 'cpu'
    device = torch.device(args.device)
    print(f'Using device: {device}')

    # Model instantiation: GRU (default) or Transformer
    if args.model_type == 'transformer':
        model = SymbolicKeyTransformer().to(device)
        if args.pretrained_checkpoint:
            ckpt = torch.load(
                args.pretrained_checkpoint, map_location=device, weights_only=True,
            )
            model.load_state_dict(ckpt['model_state_dict'])
            print(f'Loaded pretrained weights from {args.pretrained_checkpoint}')
        # Transformer defaults: lower LR, more epochs
        if args.learning_rate == 1e-3:  # user didn't override
            args.learning_rate = 1e-4
        if args.epochs == 10:  # user didn't override
            args.epochs = 20
        print(f'Transformer mode: LR={args.learning_rate}, epochs={args.epochs}')
    else:
        model = HarmonicContextGRU().to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    loss_fn = nn.CrossEntropyLoss(ignore_index=-100)

    best_validation = float('inf')
    os.makedirs(os.path.dirname(args.checkpoint), exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        train_metrics = train_epoch(model, train_loader, optimizer, loss_fn, str(device))
        validation_metrics = run_evaluation(model, validation_loader, loss_fn, str(device))

        print(
            f"epoch={epoch} "
            f"train_loss={train_metrics['loss']:.4f} "
            f"train_acc={train_metrics['accuracy']:.4f} "
            f"val_loss={validation_metrics['loss']:.4f} "
            f"val_acc={validation_metrics['accuracy']:.4f}"
        )

        if validation_metrics['loss'] < best_validation:
            best_validation = validation_metrics['loss']
            torch.save(
                {
                    'model_state_dict': model.state_dict(),
                    'validation_loss': validation_metrics['loss'],
                    'validation_accuracy': validation_metrics['accuracy'],
                    'seed': SEED,
                },
                args.checkpoint,
            )

    print(f'Saved best checkpoint to {args.checkpoint}')


if __name__ == '__main__':
    main()
