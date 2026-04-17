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
from typing import Dict, List, Sequence, Tuple, Union

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from harmonic_context_model import (
    HarmonicContextGRU,
    KEY_LABELS,
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
    parser.add_argument('--manifest', default=None, help='Path to unified_training_manifest.json for multi-source loading')
    parser.add_argument('--label-dirs', default=None, help='Comma-separated label directories to search (used with --manifest)')
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
    parser.add_argument(
        '--include-synthetic', action='store_true', default=False,
        help='Include Strategy B synthetic data (default: skip for better pitch sensitivity)',
    )
    parser.add_argument(
        '--weight-mode', choices=['inverse', 'sqrt', 'none', 'ens'], default='sqrt',
        help='Class weighting mode: inverse (raw 1/freq, ~24x ratio), '
             'sqrt (sqrt of 1/freq, ~5x ratio, default), none (uniform), '
             'ens (effective number of samples, Cui et al. CVPR 2019)',
    )
    parser.add_argument(
        '--ens-beta', type=float, default=0.999,
        help='Beta for ENS weighting (default: 0.999). Only used with --weight-mode ens.',
    )
    parser.add_argument(
        '--selection-metric', choices=['val_loss', 'val_mirex', 'val_accuracy'],
        default='val_mirex',
        help='Metric used to select the best checkpoint. Default val_mirex, because '
             'with class-weighted loss the minimum val_loss need not coincide with the '
             'maximum val-MIREX. Phase A rigor restoration (2026-04-14): previously '
             'val_loss was hardcoded, contributing to large val-to-test drift (−0.09 '
             'MIREX on A1). See PHASE2_POSTDOC_FINDINGS_2026-04-14.md §4.5.',
    )
    parser.add_argument(
        '--warmup-epochs', type=int, default=5,
        help='Linear warmup epochs before cosine decay (default: 5)',
    )
    parser.add_argument(
        '--patience', type=int, default=10,
        help='Early stopping patience in epochs (default: 10, 0=disabled)',
    )
    parser.add_argument(
        '--no-augment', action='store_true', default=False,
        help='Disable pitch-transposition and time-scaling augmentation (for ablation)',
    )
    parser.add_argument(
        '--bidirectional', action='store_true', default=False,
        help='Use bidirectional GRU (doubles hidden state, non-causal). '
             'NOTE: bidirectional training violates the <20ms no-lookahead real-time '
             'constraint. Use only for offline oracle bounds; pair with --allow-oracle '
             'when --require-causal is active.',
    )
    parser.add_argument(
        '--require-causal', action='store_true', default=False,
        help='Abort training if --bidirectional is set (enforces real-time deployability). '
             'Pair with --allow-oracle to explicitly opt into an offline oracle run.',
    )
    parser.add_argument(
        '--allow-oracle', action='store_true', default=False,
        help='When --require-causal is active, explicitly permit a bidirectional '
             'training run as an offline oracle bound. Checkpoint metadata records '
             'the oracle status so downstream evaluation can filter it out.',
    )
    parser.add_argument(
        '--gru-pcp', action='store_true', default=False,
        help='Add PCP (pitch-class profile) feature to GRU input (like Transformer branch 1)',
    )
    parser.add_argument(
        '--hidden-size', type=int, default=96,
        help='GRU hidden-state size (default 96 = Phase A config; 192 for Phase B h=192 cells).',
    )
    parser.add_argument(
        '--focal-loss', action='store_true', default=False,
        help='Use focal loss (Lin et al., ICCV 2017) instead of cross-entropy',
    )
    parser.add_argument(
        '--focal-gamma', type=float, default=2.0,
        help='Gamma parameter for focal loss (default: 2.0)',
    )
    # --- Research-grade training improvements ---
    parser.add_argument(
        '--clip-grad', type=float, default=1.0,
        help='Gradient clipping max-norm (Pascanu et al., ICML 2013). '
             '0 to disable. Default: 1.0',
    )
    parser.add_argument(
        '--weight-decay', type=float, default=0.01,
        help='Weight decay for AdamW (Loshchilov & Hutter, ICLR 2019). Default: 0.01',
    )
    parser.add_argument(
        '--label-smoothing', type=float, default=0.0,
        help='Circle-of-fifths label smoothing epsilon (novel adaptation of '
             'Szegedy et al., CVPR 2016). 0.0 = disabled, recommended 0.1',
    )
    parser.add_argument(
        '--amp', action='store_true', default=False,
        help='Enable mixed-precision training (Micikevicius et al., ICLR 2018). '
             'Only effective on CUDA devices.',
    )
    parser.add_argument(
        '--seed', type=int, default=None,
        help='Random seed for reproducibility. Defaults to the module SEED constant '
             '(20260309). Set to a specific value to reproduce a particular run.',
    )
    parser.add_argument(
        '--deterministic', action='store_true', default=False,
        help='Enable full CUDA determinism (cudnn.deterministic=True, '
             'cudnn.benchmark=False). Slows training by ~10-15% but produces '
             'bit-for-bit reproducible results across runs. Required for thesis '
             'reproducibility claims.',
    )
    return parser.parse_args()


def set_seed(seed: int, deterministic: bool = False) -> None:
    """Set random seeds across all relevant libraries.

    Args:
        seed: Integer seed to use for Python random, numpy, and PyTorch
            (CPU + all CUDA devices).
        deterministic: If True, force CUDA cuDNN to use deterministic
            algorithms. This makes training bit-for-bit reproducible at the
            cost of ~10-15% throughput. Required for thesis reproducibility.

    Note: Even with deterministic=True, some operations (e.g. atomic
    floating-point reductions on CUDA) may produce slightly non-deterministic
    results across hardware. For full hardware-independent reproducibility,
    use the same GPU model.
    """
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if deterministic:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        # PyTorch 1.8+ deterministic algorithms (best-effort)
        try:
            torch.use_deterministic_algorithms(True, warn_only=True)
        except (AttributeError, TypeError):
            pass
        # Set environment variable for some CUDA backend determinism
        os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')


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


def augment_transpose(
    notes: Sequence[Dict[str, object]], semitones: int,
) -> List[Dict[str, object]]:
    """Transpose all notes by *semitones*, shifting pitch and key label together.

    Pitch is clamped to MIDI range [0, 127].  Key labels are rotated within
    their mode (major 0-11, minor 12-23).  Scale-degree and JI-ratio fields
    are left unchanged because they are relative to the key.
    """
    transposed: List[Dict[str, object]] = []
    for note in notes:
        new_note = dict(note)
        new_pitch = int(note['pitch']) + semitones
        if new_pitch < 0 or new_pitch > 127:
            continue  # drop notes that fall outside MIDI range
        new_note['pitch'] = new_pitch

        # Rotate key label by the same interval
        old_key_idx = key_to_index(str(note['key']))
        is_minor = old_key_idx >= 12
        old_tonic_pc = old_key_idx % 12
        new_tonic_pc = (old_tonic_pc + semitones) % 12
        new_key_idx = new_tonic_pc + (12 if is_minor else 0)
        new_note['key'] = KEY_LABELS[new_key_idx]

        # Update tonic_pc if present (used by some label files)
        if 'tonic_pc' in note:
            new_note['tonic_pc'] = new_tonic_pc

        transposed.append(new_note)
    return transposed


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
        # Pitch-transposition augmentation: shift by ±5 semitones
        semitones = random.randint(-5, 6)
        if semitones != 0:
            transposed = augment_transpose(notes, semitones)
            if transposed:  # Guard: keep original if all notes fell out of range
                notes = transposed
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
        vel = int(note.get('velocity', 96))
        velocity_bucket.append(sum(vel > edge for edge in tuple(range(0, 128, 8))))

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


class FocalLoss(nn.Module):
    """Focal loss (Lin et al., ICCV 2017) for class-imbalanced classification.

    FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)

    Down-weights well-classified examples (high p_t) so the model focuses on
    hard, misclassified examples. Particularly useful when minor keys are
    easy to detect in some contexts but hard in others — standard CE treats
    all examples equally, but focal loss concentrates on the difficult ones.

    Args:
        weight: Per-class weights (same as CrossEntropyLoss)
        gamma: Focusing parameter. gamma=0 is standard CE. gamma=2 is typical.
        ignore_index: Label index to ignore (padding).
    """

    def __init__(
        self,
        weight: torch.Tensor | None = None,
        gamma: float = 2.0,
        ignore_index: int = -100,
    ):
        super().__init__()
        self.gamma = gamma
        self.ignore_index = ignore_index
        self.register_buffer('weight', weight)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce_loss = nn.functional.cross_entropy(
            logits, targets, weight=self.weight,
            ignore_index=self.ignore_index, reduction='none',
        )
        # p_t = probability of true class
        log_probs = nn.functional.log_softmax(logits, dim=-1)
        # Gather the log-prob of the true class for each sample
        mask = targets != self.ignore_index
        safe_targets = targets.clone()
        safe_targets[~mask] = 0
        log_pt = log_probs.gather(dim=-1, index=safe_targets.unsqueeze(-1)).squeeze(-1)
        pt = log_pt.exp()

        focal_weight = (1 - pt) ** self.gamma
        loss = focal_weight * ce_loss

        # Only average over non-ignored positions
        if mask.sum() > 0:
            return loss[mask].mean()
        return loss.sum()  # 0 if all masked


class MusicTheoreticLabelSmoothing(nn.Module):
    """Circle-of-fifths label smoothing for musical key classification.

    Novel adaptation of Szegedy et al. (CVPR 2016) that distributes smoothing
    mass according to MIREX key-evaluation similarity rather than uniformly.
    This encodes music-theoretic structure: predicting a closely-related key
    (e.g. the dominant or relative minor) is less wrong than predicting a
    distant key.

    The smoothing kernel assigns weights based on MIREX relations:
      - Fifth relation (same mode, pitch-class diff in {5, 7}):  0.5
      - Relative key  (diff mode, pitch-class diff in {3, 9}):   0.3
      - Parallel key   (same root, diff mode):                    0.2
      - Other:                                                    0.0

    For each true key k, the target distribution is:
      q(k) = 1 - epsilon                                   (true class)
      q(j) = epsilon * kernel_row(k, j)                    for j != k

    Uses KL divergence loss and supports combination with class weights
    and focal loss.

    Args:
        epsilon: Smoothing strength (0.0 = no smoothing = standard CE).
        weight: Per-class weights tensor (24,). Applied as multiplicative
            scaling on the per-sample loss.
        focal_gamma: If > 0, applies focal-loss modulation on top of the
            smoothed KL loss. 0.0 = no focal modulation.
        ignore_index: Label index to ignore (padding).
    """

    def __init__(
        self,
        epsilon: float = 0.1,
        weight: torch.Tensor | None = None,
        focal_gamma: float = 0.0,
        ignore_index: int = -100,
    ):
        super().__init__()
        self.epsilon = epsilon
        self.focal_gamma = focal_gamma
        self.ignore_index = ignore_index

        # Precompute the 24x24 smoothing kernel
        kernel = self._build_mirex_kernel()
        self.register_buffer('kernel', kernel)

        if weight is not None:
            self.register_buffer('weight', weight)
        else:
            self.weight = None

    @staticmethod
    def _build_mirex_kernel() -> torch.Tensor:
        """Build a 24x24 MIREX-similarity smoothing kernel.

        Rows correspond to true keys (0-11 major, 12-23 minor).
        Columns give the raw similarity weight to each other key.
        Each row is normalised to sum to 1 so it can be used as a
        mixing distribution for the epsilon mass.
        """
        kernel = torch.zeros(24, 24)
        for k in range(24):
            k_pc = k % 12
            k_mode = k // 12  # 0 = major, 1 = minor
            for j in range(24):
                if j == k:
                    continue  # self-weight handled outside kernel
                j_pc = j % 12
                j_mode = j // 12
                pc_diff = (j_pc - k_pc) % 12
                same_mode = (k_mode == j_mode)
                same_root = (k_pc == j_pc)

                if same_mode and pc_diff in (5, 7):
                    # Fifth relation (dominant / subdominant, same mode)
                    kernel[k, j] = 0.5
                elif (not same_mode) and pc_diff in (3, 9):
                    # Relative key (e.g. C major <-> A minor)
                    kernel[k, j] = 0.3
                elif same_root and (not same_mode):
                    # Parallel key (e.g. C major <-> C minor)
                    kernel[k, j] = 0.2
                # else: 0.0

            # Normalise row so the non-self weights sum to 1
            row_sum = kernel[k].sum()
            if row_sum > 0:
                kernel[k] /= row_sum

        return kernel

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """Compute smoothed loss.

        Args:
            logits: (N, 24) raw logits.
            targets: (N,) integer class labels.
        """
        mask = targets != self.ignore_index
        if mask.sum() == 0:
            return logits.sum() * 0.0

        safe_targets = targets.clone()
        safe_targets[~mask] = 0

        # Build smoothed target distribution: (N, 24)
        one_hot = torch.zeros_like(logits).scatter_(
            -1, safe_targets.unsqueeze(-1), 1.0,
        )
        # kernel[safe_targets] gathers the smoothing row for each sample
        smooth_dist = self.kernel[safe_targets]  # (N, 24)
        q = (1.0 - self.epsilon) * one_hot + self.epsilon * smooth_dist

        # KL divergence: sum_j q_j * (log q_j - log p_j)
        log_probs = nn.functional.log_softmax(logits, dim=-1)

        # Per-sample loss (sum over classes)
        per_sample = -(q * log_probs).sum(dim=-1)  # (N,)

        # Focal modulation (optional)
        if self.focal_gamma > 0:
            pt = torch.exp(
                log_probs.gather(-1, safe_targets.unsqueeze(-1)).squeeze(-1)
            )
            focal_weight = (1.0 - pt) ** self.focal_gamma
            per_sample = focal_weight * per_sample

        # Class-weight scaling (optional)
        if self.weight is not None:
            w = self.weight[safe_targets]
            per_sample = w * per_sample

        return per_sample[mask].mean()


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
    """Load records from a single label directory (backward compatibility)."""
    records = []
    for composition_id in sorted(composition_ids):
        filename = f'{composition_id:04d}.json'
        path = os.path.join(label_dir, filename)
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8') as handle:
            records.append(json.load(handle))
    return records


def load_records_from_manifest(
    manifest_path: str,
    label_dirs: List[str],
    split_name: str,
    include_synthetic: bool = False,
) -> Tuple[List[Dict[str, object]], Dict[str, int], Dict[str, int]]:
    """
    Load records from a unified manifest, searching across multiple label directories.

    Filters out Strategy B synthetic files by default (they have all notes at pitch=60
    with varying key labels, which teaches the model to ignore pitch information).
    Only loads files where:
      - converter_strategy is "A" (real score parsing), OR
      - converter_strategy is absent (ATEPP files with real note data), OR
      - include_synthetic=True (for ablation studies)

    Args:
        manifest_path: Path to unified_training_manifest.json
        label_dirs: List of directories to search for label files
        split_name: Which split to load ('train', 'val', 'test')
        include_synthetic: If True, include Strategy B files (default: False)

    Returns:
        (records, class_counts, data_composition) where:
        - records: List of loaded record dictionaries
        - class_counts: Dict mapping key class (0-23) to label count
        - data_composition: Dict with stats on ATEPP, Strategy A, and Strategy B counts
    """
    with open(manifest_path, 'r', encoding='utf-8') as handle:
        manifest = json.load(handle)

    records = []
    class_counts = {i: 0 for i in range(24)}

    # Track data composition
    composition_stats = {
        'atepp_files': 0,
        'strategy_a_files': 0,
        'strategy_b_files_skipped': 0,
        'atepp_notes': 0,
        'strategy_a_notes': 0,
        'strategy_b_notes_skipped': 0,
    }

    for entry in manifest.get('entries', []):
        # Skip entries not in the requested split
        if entry.get('split') != split_name:
            continue

        # Try to find the label file across all directories
        relative_path = entry.get('file_path', '')

        # First, try the path as-is (absolute or relative to manifest)
        candidate_paths = [relative_path]

        # Also try just the filename across all label directories (flat search)
        filename = os.path.basename(relative_path)
        for label_dir in label_dirs:
            candidate_paths.append(os.path.join(label_dir, filename))
            # Recursive search: check subdirectories (handles DCML corpus structure)
            for subdir in os.listdir(label_dir) if os.path.isdir(label_dir) else []:
                subpath = os.path.join(label_dir, subdir, filename)
                if os.path.isdir(os.path.join(label_dir, subdir)):
                    candidate_paths.append(subpath)

        for candidate in candidate_paths:
            if not os.path.exists(candidate):
                continue

            with open(candidate, 'r', encoding='utf-8') as handle:
                data = json.load(handle)

            # Only load if the file has a 'notes' array (ATEPP format)
            if 'notes' not in data:
                continue  # File found but no notes, try next directory

            # Check converter_strategy from the LOADED FILE (not the manifest)
            # Strategy B files have all notes at pitch=60 — synthetic garbage
            file_strategy = data.get('converter_strategy')

            if file_strategy == 'B' and not include_synthetic:
                notes_count = len(data.get('notes', []))
                composition_stats['strategy_b_files_skipped'] += 1
                composition_stats['strategy_b_notes_skipped'] += notes_count
                break  # Found the file, it's Strategy B, skip it

            records.append(data)

            # Track which type of file this is
            notes_count = len(data.get('notes', []))
            if file_strategy == 'A':
                composition_stats['strategy_a_files'] += 1
                composition_stats['strategy_a_notes'] += notes_count
            else:  # No converter_strategy = ATEPP files with real notes
                composition_stats['atepp_files'] += 1
                composition_stats['atepp_notes'] += notes_count

            # Count class distribution from labels
            for note in data.get('notes', []):
                if 'key' in note:
                    key_idx = key_to_index(str(note['key']))
                    if 0 <= key_idx < 24:
                        class_counts[key_idx] += 1
            break

    return records, class_counts, composition_stats


def compute_class_weights(
    records: List[Dict[str, object]],
    mode: str = 'sqrt',
    ens_beta: float = 0.999,
) -> Tuple[Dict[int, float], Dict[int, int]]:
    """
    Compute class weights based on label distribution in training data.

    Args:
        records: Training records with 'notes' arrays.
        mode: Weighting strategy:
            'inverse' — raw inverse-frequency (can produce 20-25× ratio, risks collapse)
            'sqrt'    — sqrt of inverse-frequency (~5× ratio, recommended default)
            'none'    — uniform weights (all 1.0)
            'ens'     — effective number of samples (Cui et al., CVPR 2019)
        ens_beta: Beta parameter for ENS mode (default 0.999). Controls smoothing:
            closer to 1.0 = more aggressive reweighting for rare classes.

    Returns:
        (weights_dict, class_counts) where:
        - weights_dict: class_id -> weight for use in CrossEntropyLoss
        - class_counts: class_id -> count of that class in training data
    """
    class_counts = {i: 0 for i in range(24)}

    # Count all labels in the training data
    for record in records:
        notes = record.get('notes', [])
        for note in notes:
            key = str(note.get('key', ''))
            try:
                key_idx = key_to_index(key)
                if 0 <= key_idx < 24:
                    class_counts[key_idx] += 1
            except (ValueError, KeyError):
                continue

    weights_dict = {}
    total_count = sum(class_counts.values())

    if mode == 'none' or total_count == 0:
        weights_dict = {i: 1.0 for i in range(24)}
    else:
        for class_id in range(24):
            count = max(class_counts[class_id], 1)  # Avoid division by zero
            if mode == 'sqrt':
                weights_dict[class_id] = 1.0 / math.sqrt(float(count))
            elif mode == 'ens':
                # Effective Number of Samples (Cui et al., CVPR 2019)
                # w_c = (1 - beta) / (1 - beta^n_c)
                effective_n = (1.0 - ens_beta ** count) / (1.0 - ens_beta)
                weights_dict[class_id] = 1.0 / effective_n
            else:  # 'inverse'
                weights_dict[class_id] = 1.0 / float(count)

        # Normalize weights: scale so they sum to 24 (num_classes)
        weight_sum = sum(weights_dict.values())
        if weight_sum > 0:
            scaling_factor = 24.0 / weight_sum
            weights_dict = {k: v * scaling_factor for k, v in weights_dict.items()}

    return weights_dict, class_counts


def masked_accuracy(logits: torch.Tensor, labels: torch.Tensor) -> float:
    predictions = logits.argmax(dim=-1)
    mask = labels != -100
    correct = (predictions[mask] == labels[mask]).sum().item()
    total = mask.sum().item()
    return 0.0 if total == 0 else correct / total


# Phase A: MIREX scoring for val-MIREX checkpoint selection. Mirrors the canonical
# version in evaluate_harmonic_context_model.py:74–104; imports are blocked by a
# reverse dependency. Key indices: 0–11 = C..B major, 12–23 = Cm..Bm minor.
def _mirex_score_int(pred_idx: int, true_idx: int) -> float:
    if pred_idx == true_idx:
        return 1.0
    pred_pc = pred_idx % 12
    true_pc = true_idx % 12
    pred_minor = pred_idx >= 12
    true_minor = true_idx >= 12
    pc_diff = (pred_pc - true_pc) % 12
    if pred_pc == true_pc and pred_minor != true_minor:
        return 0.2
    if pred_minor == true_minor and pc_diff in (5, 7):
        return 0.5
    if pred_minor != true_minor and pc_diff in (3, 9):
        return 0.3
    return 0.0


_MIREX_LUT: torch.Tensor | None = None


def _mirex_lookup_table(device: torch.device) -> torch.Tensor:
    """24x24 lookup table of MIREX scores; computed once and cached per device."""
    global _MIREX_LUT
    if _MIREX_LUT is None or _MIREX_LUT.device != device:
        table = torch.tensor(
            [[_mirex_score_int(p, t) for t in range(24)] for p in range(24)],
            dtype=torch.float32, device=device,
        )
        _MIREX_LUT = table
    return _MIREX_LUT


def masked_mirex(logits: torch.Tensor, labels: torch.Tensor) -> Tuple[float, int]:
    """Compute mean MIREX weighted score over non-masked positions.

    Returns (sum_score, count). Sum (not mean) so aggregation across batches
    is a simple total_sum / total_count — identical to what `run_evaluation`
    does for accuracy.
    """
    predictions = logits.argmax(dim=-1)
    mask = labels != -100
    if mask.sum().item() == 0:
        return 0.0, 0
    lut = _mirex_lookup_table(logits.device)
    flat_pred = predictions[mask]
    flat_true = labels[mask]
    scores = lut[flat_pred, flat_true]
    return float(scores.sum().item()), int(flat_true.numel())


def _get_key_logits(output: object) -> torch.Tensor:
    """Get key logits from model output (GRU returns tensor, Transformer returns dict)."""
    if isinstance(output, dict):
        return output['key_logits']
    return output


def run_evaluation(
    model: nn.Module, loader: DataLoader, loss_fn: nn.Module, device: str,
    use_amp: bool = False,
) -> Dict[str, float]:
    model.eval()
    total_loss = 0.0
    total_accuracy = 0.0
    mirex_sum = 0.0
    mirex_count = 0
    batches = 0

    with torch.no_grad():
        for batch in loader:
            batch = {key: value.to(device) if torch.is_tensor(value) else value for key, value in batch.items()}
            with torch.amp.autocast('cuda', enabled=use_amp):
                logits = _get_key_logits(model(batch))
                loss = loss_fn(logits.view(-1, logits.shape[-1]), batch['labels'].view(-1))
            total_loss += loss.item()
            total_accuracy += masked_accuracy(logits, batch['labels'])
            bs_sum, bs_count = masked_mirex(logits, batch['labels'])
            mirex_sum += bs_sum
            mirex_count += bs_count
            batches += 1

    if batches == 0:
        return {'loss': math.nan, 'accuracy': math.nan, 'mirex_weighted_score': math.nan}

    return {
        'loss': total_loss / batches,
        'accuracy': total_accuracy / batches,
        'mirex_weighted_score': mirex_sum / mirex_count if mirex_count > 0 else math.nan,
        'mirex_n_frames': mirex_count,
    }


def train_epoch(
    model: nn.Module, loader: DataLoader, optimizer, loss_fn, device: str,
    clip_grad: float = 0.0,
    use_amp: bool = False,
    scaler: object = None,
) -> Dict[str, float]:
    model.train()
    total_loss = 0.0
    total_accuracy = 0.0
    batches = 0

    for batch in loader:
        batch = {key: value.to(device) if torch.is_tensor(value) else value for key, value in batch.items()}
        optimizer.zero_grad()
        with torch.amp.autocast('cuda', enabled=use_amp):
            logits = _get_key_logits(model(batch))
            loss = loss_fn(logits.view(-1, logits.shape[-1]), batch['labels'].view(-1))
        if scaler is not None:
            scaler.scale(loss).backward()
            if clip_grad > 0:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=clip_grad)
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            if clip_grad > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=clip_grad)
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

    # --- Causal-only guardrail (Phase A rigor restoration) ---
    # Bidirectional GRUs see future notes and therefore violate the real-time
    # <20ms no-lookahead tuning constraint. Permit bidirectional training only
    # when the user explicitly opts in as an offline oracle run.
    if args.require_causal and args.bidirectional and not args.allow_oracle:
        raise SystemExit(
            '[--require-causal] Refusing to train with --bidirectional.\n'
            '  Bidirectional GRUs are not deployable in the real-time tuning path.\n'
            '  To produce an offline oracle bound, pass --allow-oracle; the checkpoint\n'
            '  will be tagged as an oracle result in its metadata.'
        )
    if args.bidirectional and args.require_causal and args.allow_oracle:
        print('[--require-causal --allow-oracle] Bidirectional training permitted '
              'as ORACLE run — not a deployable result.')

    seed = args.seed if args.seed is not None else SEED
    set_seed(seed, deterministic=args.deterministic)
    print(f'Random seed: {seed}'
          f'{" (deterministic CUDA)" if args.deterministic else ""}')

    # Load records using either manifest mode or legacy mode
    if args.manifest:
        # Manifest mode: load from unified_training_manifest.json
        label_dirs = [args.label_dir]  # Always include default
        if args.label_dirs:
            label_dirs.extend(args.label_dirs.split(','))
        label_dirs = [d.strip() for d in label_dirs if d.strip()]

        print(f'Loading from manifest: {args.manifest}')
        print(f'Searching label directories: {label_dirs}')
        if args.include_synthetic:
            print('NOTE: Including Strategy B synthetic data (--include-synthetic flag set)')
        else:
            print('NOTE: Skipping Strategy B synthetic files (use --include-synthetic to include)')

        train_records, train_class_counts, train_composition = load_records_from_manifest(
            args.manifest, label_dirs, 'train', include_synthetic=args.include_synthetic
        )
        validation_records, val_class_counts, val_composition = load_records_from_manifest(
            args.manifest, label_dirs, 'val', include_synthetic=args.include_synthetic
        )

        print(f'\nTraining set data composition:')
        print(f'  ATEPP files (real notes):        {train_composition["atepp_files"]:6d} files, {train_composition["atepp_notes"]:8d} notes')
        print(f'  Strategy A files (real scores):  {train_composition["strategy_a_files"]:6d} files, {train_composition["strategy_a_notes"]:8d} notes')
        print(f'  Strategy B files SKIPPED:        {train_composition["strategy_b_files_skipped"]:6d} files, {train_composition["strategy_b_notes_skipped"]:8d} notes')
        total_real_notes = train_composition['atepp_notes'] + train_composition['strategy_a_notes']
        print(f'  TOTAL REAL NOTES LOADED:         {total_real_notes:30d}')

        print(f'\nValidation set data composition:')
        print(f'  ATEPP files (real notes):        {val_composition["atepp_files"]:6d} files, {val_composition["atepp_notes"]:8d} notes')
        print(f'  Strategy A files (real scores):  {val_composition["strategy_a_files"]:6d} files, {val_composition["strategy_a_notes"]:8d} notes')
        print(f'  Strategy B files SKIPPED:        {val_composition["strategy_b_files_skipped"]:6d} files, {val_composition["strategy_b_notes_skipped"]:8d} notes')
        total_val_notes = val_composition['atepp_notes'] + val_composition['strategy_a_notes']
        print(f'  TOTAL REAL NOTES LOADED:         {total_val_notes:30d}')

        print(f'\nLoaded {len(train_records)} training records from manifest')
        print(f'Loaded {len(validation_records)} validation records from manifest')
        print(f'\nTraining set class distribution:')
        for class_id in range(24):
            count = train_class_counts[class_id]
            if count > 0:
                print(f'  Class {class_id:2d}: {count:6d} labels')

    else:
        # Legacy mode: load from composition_splits.json
        split_ids = load_split_ids(args.splits)
        train_records = load_records(args.label_dir, split_ids['train'])
        validation_records = load_records(args.label_dir, split_ids['validation'])
        print(f'Loaded {len(train_records)} training records from {args.label_dir}')
        print(f'Loaded {len(validation_records)} validation records from {args.label_dir}')

    use_augment = not args.no_augment
    train_dataset = HarmonicLabelDataset(
        train_records,
        augment=use_augment,
        window_size=args.window_size,
        window_hop=args.window_hop,
    )
    print(f'Augmentation: {"enabled" if use_augment else "DISABLED"}')
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
        model = HarmonicContextGRU(
            hidden_size=args.hidden_size,
            bidirectional=args.bidirectional,
            use_pcp=args.gru_pcp,
        ).to(device)
        print(f'GRU mode: hidden_size={args.hidden_size}')
        if args.bidirectional:
            print(f'GRU mode: bidirectional (output dim = {args.hidden_size * 2})')
        if args.gru_pcp:
            print(f'GRU mode: PCP feature enabled (input dim = {args.hidden_size})')

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay,
    )

    # --- Learning-rate schedule: linear warmup + cosine decay (epoch-level) ---
    def lr_lambda(current_epoch: int) -> float:
        """Epoch-indexed (0-based): linear warmup then cosine decay."""
        if current_epoch < args.warmup_epochs and args.warmup_epochs > 0:
            return float(current_epoch + 1) / float(args.warmup_epochs)
        # Cosine decay after warmup
        decay_epochs = max(1, args.epochs - args.warmup_epochs)
        progress = float(current_epoch - args.warmup_epochs) / float(decay_epochs)
        return max(0.0, 0.5 * (1.0 + math.cos(math.pi * progress)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)
    print(f'LR schedule: {args.warmup_epochs}-epoch linear warmup -> cosine decay over {args.epochs} epochs')

    # Compute class weights from training data
    weights_dict, class_counts = compute_class_weights(
        train_records, mode=args.weight_mode, ens_beta=args.ens_beta,
    )
    class_weights = torch.tensor(
        [weights_dict.get(i, 1.0) for i in range(24)],
        dtype=torch.float32,
        device=device
    )
    if args.label_smoothing > 0:
        loss_fn = MusicTheoreticLabelSmoothing(
            epsilon=args.label_smoothing,
            weight=class_weights,
            focal_gamma=args.focal_gamma if args.focal_loss else 0.0,
            ignore_index=-100,
        )
        parts = [f'Circle-of-fifths label smoothing (epsilon={args.label_smoothing})']
        if args.focal_loss:
            parts.append(f'+ focal (gamma={args.focal_gamma})')
        print(f'Loss: {" ".join(parts)}')
    elif args.focal_loss:
        loss_fn = FocalLoss(
            weight=class_weights, gamma=args.focal_gamma, ignore_index=-100,
        )
        print(f'Loss: Focal loss (gamma={args.focal_gamma})')
    else:
        loss_fn = nn.CrossEntropyLoss(weight=class_weights, ignore_index=-100)

    weight_values = [class_weights[i].item() for i in range(24)]
    weight_ratio = max(weight_values) / max(min(weight_values), 1e-6)
    print(f'\nClass weights (mode={args.weight_mode}, max/min ratio={weight_ratio:.1f}×):')
    for class_id in range(24):
        weight = class_weights[class_id].item()
        count = class_counts.get(class_id, 0)
        print(f'  Class {class_id:2d}: weight={weight:.4f} (count={count})')

    # --- Mixed-precision training (Micikevicius et al., ICLR 2018) ---
    use_amp = args.amp and device.type == 'cuda'
    scaler = torch.amp.GradScaler('cuda', enabled=use_amp) if use_amp else None
    if args.amp and not use_amp:
        print('AMP: requested but device is not CUDA — disabled')
    elif use_amp:
        print('AMP: mixed-precision training enabled (float16)')

    # --- Gradient clipping (Pascanu et al., ICML 2013) ---
    clip_grad = args.clip_grad
    if clip_grad > 0:
        print(f'Gradient clipping: max_norm={clip_grad}')
    else:
        print('Gradient clipping: disabled')

    print(f'Weight decay: {args.weight_decay}')

    # Phase A selection-metric handling (rigor restoration).
    # Higher-is-better for val_mirex / val_accuracy; lower-is-better for val_loss.
    if args.selection_metric == 'val_loss':
        best_score = float('inf')
        def _is_better(new_score: float, best: float) -> bool:
            return new_score < best
        def _metric_of(m: Dict[str, float]) -> float:
            return float(m.get('loss', float('inf')))
    elif args.selection_metric == 'val_accuracy':
        best_score = float('-inf')
        def _is_better(new_score: float, best: float) -> bool:
            return new_score > best
        def _metric_of(m: Dict[str, float]) -> float:
            return float(m.get('accuracy', float('-inf')))
    else:  # val_mirex — default
        best_score = float('-inf')
        def _is_better(new_score: float, best: float) -> bool:
            return new_score > best
        def _metric_of(m: Dict[str, float]) -> float:
            return float(m.get('mirex_weighted_score', float('-inf')))
    best_validation = best_score  # kept name for backwards-compatible checkpoint field
    print(f'Checkpoint selection metric: {args.selection_metric}')

    best_epoch = 0
    epochs_without_improvement = 0
    per_epoch_log: List[Dict[str, float]] = []
    os.makedirs(os.path.dirname(args.checkpoint), exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        train_metrics = train_epoch(
            model, train_loader, optimizer, loss_fn, str(device),
            clip_grad=clip_grad, use_amp=use_amp, scaler=scaler,
        )
        # Step scheduler once per epoch (epoch-level is standard for warmup+cosine)
        scheduler.step()
        validation_metrics = run_evaluation(
            model, validation_loader, loss_fn, str(device), use_amp=use_amp,
        )

        current_lr = optimizer.param_groups[0]['lr']
        print(
            f"epoch={epoch} "
            f"train_loss={train_metrics['loss']:.4f} "
            f"train_acc={train_metrics['accuracy']:.4f} "
            f"val_loss={validation_metrics['loss']:.4f} "
            f"val_acc={validation_metrics['accuracy']:.4f} "
            f"val_mirex={validation_metrics.get('mirex_weighted_score', float('nan')):.4f} "
            f"lr={current_lr:.2e}"
        )

        per_epoch_log.append({
            'epoch': epoch,
            'train_loss': float(train_metrics['loss']),
            'train_accuracy': float(train_metrics['accuracy']),
            'val_loss': float(validation_metrics['loss']),
            'val_accuracy': float(validation_metrics['accuracy']),
            'val_mirex_weighted_score': float(validation_metrics.get('mirex_weighted_score', float('nan'))),
            'learning_rate': float(current_lr),
        })

        current_score = _metric_of(validation_metrics)
        if _is_better(current_score, best_validation):
            best_validation = current_score
            best_epoch = epoch
            epochs_without_improvement = 0
            torch.save(
                {
                    'model_state_dict': model.state_dict(),
                    'validation_loss': validation_metrics['loss'],
                    'validation_accuracy': validation_metrics['accuracy'],
                    'validation_mirex_weighted_score': validation_metrics.get('mirex_weighted_score'),
                    'selection_metric': args.selection_metric,
                    'selection_metric_value': float(current_score),
                    'seed': seed,  # actual runtime seed — bug fix 2026-04-14, was SEED constant
                    'epoch': epoch,
                    'weight_mode': args.weight_mode,
                    'ens_beta': args.ens_beta if args.weight_mode == 'ens' else None,
                    'augment': use_augment,
                    'model_type': args.model_type,
                    'learning_rate': args.learning_rate,
                    'batch_size': args.batch_size,
                    'window_size': args.window_size,
                    'warmup_epochs': args.warmup_epochs,
                    'patience': args.patience,
                    'bidirectional': args.bidirectional,
                    'is_oracle_result': bool(args.bidirectional),
                    'require_causal_flag': bool(args.require_causal),
                    'allow_oracle_flag': bool(args.allow_oracle),
                    'gru_pcp': args.gru_pcp,
                    'hidden_size': args.hidden_size,
                    'focal_loss': args.focal_loss,
                    'focal_gamma': args.focal_gamma if args.focal_loss else None,
                    'clip_grad': args.clip_grad,
                    'weight_decay': args.weight_decay,
                    'label_smoothing': args.label_smoothing,
                    'amp': use_amp,
                },
                args.checkpoint,
            )
        else:
            epochs_without_improvement += 1
            if args.patience > 0 and epochs_without_improvement >= args.patience:
                print(f'Early stopping: no improvement for {args.patience} epochs')
                break

    # Persist the per-epoch training log alongside the checkpoint for Phase A provenance.
    log_path = os.path.splitext(args.checkpoint)[0] + '_training_log.json'
    try:
        with open(log_path, 'w', encoding='utf-8') as fh:
            json.dump({
                'selection_metric': args.selection_metric,
                'best_epoch': best_epoch,
                'best_selection_metric_value': float(best_validation),
                'seed': seed,  # actual runtime seed — bug fix 2026-04-14, was SEED constant
                'weight_mode': args.weight_mode,
                'bidirectional': args.bidirectional,
                'per_epoch': per_epoch_log,
            }, fh, indent=2)
        print(f'Saved training log to {log_path}')
    except OSError as exc:
        print(f'WARNING: could not persist training log to {log_path}: {exc}')

    print(f'Saved best checkpoint to {args.checkpoint} (best epoch={best_epoch}, '
          f'selection={args.selection_metric}={best_validation:.4f})')


if __name__ == '__main__':
    main()
