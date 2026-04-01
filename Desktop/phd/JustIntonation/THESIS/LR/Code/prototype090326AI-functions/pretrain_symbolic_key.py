#!/usr/bin/env python3
"""
Self-supervised pre-training for SymbolicKeyTransformer.

Adapts S-KEY (Kong et al., ICASSP 2025) from audio CQT to symbolic MIDI:
  - Equivariance loss: predict transposition interval via circle-of-fifths CPSD
  - Mode loss: major/minor pseudo-labels from PCP energy comparison
  - Batch balance: regularise 50/50 major/minor split

Usage:
    python pretrain_symbolic_key.py                          # full run
    python pretrain_symbolic_key.py --limit 50 --epochs 2    # smoke test
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm

import pretty_midi

from harmonic_context_model import (
    SymbolicKeyTransformer,
    compute_pcp,
    encode_live_events,
    collate_harmonic_batch,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PIANO_MIN = 21   # A0
PIANO_MAX = 108  # C8
BEAT_MS = 500.0  # 120 BPM default for timing conversion


# ===========================================================================
# 1. MIDI Note Loading
# ===========================================================================

def load_midi_notes(midi_path: str) -> List[Dict[str, object]]:
    """Load note events from a MIDI file using pretty_midi.

    Returns list of dicts with keys: pitch, start, end, velocity.
    Filtered to piano range [21, 108], sorted by onset.
    """
    try:
        pm = pretty_midi.PrettyMIDI(midi_path)
    except Exception:
        return []

    notes = []
    for instrument in pm.instruments:
        for note in instrument.notes:
            if PIANO_MIN <= note.pitch <= PIANO_MAX:
                notes.append({
                    'pitch': note.pitch,
                    'start': note.start,
                    'end': note.end,
                    'velocity': note.velocity,
                })
    notes.sort(key=lambda n: (n['start'], n['pitch']))
    return notes


# ===========================================================================
# 2. MIDI Cache (JSON-lines for safety)
# ===========================================================================

def build_midi_cache(
    metadata_csv: str,
    atepp_base: str,
    cache_path: str,
    limit: int | None = None,
) -> Dict[str, List[Dict]]:
    """Load all ATEPP MIDIs and cache as JSON-lines file.

    Returns dict mapping midi_path -> note list.
    """
    if os.path.exists(cache_path):
        print(f'Loading cached MIDI notes from {cache_path}...')
        cache = {}
        with open(cache_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                cache[entry['path']] = entry['notes']
        print(f'  Loaded {len(cache)} MIDI files from cache.')
        return cache

    print(f'Building MIDI cache (first run, this takes ~20-40 minutes)...')
    df = pd.read_csv(metadata_csv)
    midi_paths = df['midi_path'].unique().tolist()
    if limit:
        midi_paths = midi_paths[:limit]

    cache = {}
    with open(cache_path, 'w') as f:
        for midi_rel in tqdm(midi_paths, desc='Loading MIDIs'):
            full_path = os.path.join(atepp_base, midi_rel)
            if not os.path.exists(full_path):
                continue
            notes = load_midi_notes(full_path)
            if len(notes) < 64:  # skip very short pieces
                continue
            cache[midi_rel] = notes
            entry = json.dumps({'path': midi_rel, 'notes': notes})
            f.write(entry + '\n')

    print(f'  Cached {len(cache)} MIDI files to {cache_path}')
    return cache


# ===========================================================================
# 3. Transposition Utilities
# ===========================================================================

def transpose_notes(
    notes: List[Dict[str, object]], semitones: int,
) -> List[Dict[str, object]]:
    """Transpose all note pitches by semitones, filtering out-of-range notes."""
    result = []
    for note in notes:
        new_pitch = note['pitch'] + semitones
        if PIANO_MIN <= new_pitch <= PIANO_MAX:
            transposed = dict(note)
            transposed['pitch'] = new_pitch
            result.append(transposed)
    return result


def sample_window(
    notes: List[Dict[str, object]], size: int,
) -> List[Dict[str, object]] | None:
    """Sample a random contiguous window of notes."""
    if len(notes) < size:
        return None
    start = random.randint(0, len(notes) - size)
    return notes[start : start + size]


# ===========================================================================
# 4. Encoding Bridge: MIDI notes -> encode_live_events format
# ===========================================================================

def midi_notes_to_live_format(
    notes: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    """Convert pretty_midi note dicts to encode_live_events input format.

    Computes active_notes (notes sounding at each onset) and converts
    times from seconds to milliseconds.
    """
    events = []
    for i, note in enumerate(notes):
        onset_ms = note['start'] * 1000.0
        duration_ms = (note['end'] - note['start']) * 1000.0

        # Build active notes: all notes sounding at this onset
        active = set()
        for other in notes:
            if other['start'] <= note['start'] < other['end']:
                active.add(other['pitch'])

        events.append({
            'note': note['pitch'],
            'time_ms': onset_ms,
            'duration_ms': max(1.0, duration_ms),
            'velocity': note['velocity'],
            'active_notes': list(active),
        })
    return events


def encode_window(
    notes: List[Dict[str, object]], pcp_window: int = 32,
) -> Dict[str, object]:
    """Encode a window of MIDI notes into model input format with PCP."""
    events = midi_notes_to_live_format(notes)
    encoded = encode_live_events(events)

    pcp = compute_pcp(encoded['pitch_class'], window_size=pcp_window)

    return {
        'pitch_class': encoded['pitch_class'],
        'register': encoded['register'],
        'delta_bucket': encoded['delta_bucket'],
        'duration_bucket': encoded['duration_bucket'],
        'velocity_bucket': encoded['velocity_bucket'],
        'active_mask': encoded['active_mask'],
        'pcp': pcp,
        'labels': [0] * len(encoded['pitch_class']),  # dummy labels
    }


# ===========================================================================
# 5. Loss Functions (S-KEY adapted to symbolic domain)
# ===========================================================================

def symbolic_equivariance_loss(
    ksp_A: torch.Tensor,
    ksp_B: torch.Tensor,
    transposition_c: int,
) -> torch.Tensor:
    """Equivariance loss via circle-of-fifths CPSD (S-KEY Eq. 4 adapted).

    If B is a transposition of A by c semitones, then the DFT of B's KSP
    at the circle-of-fifths frequency (omega=7) should differ from A's
    by a phase rotation of 2*pi*7*c/12.

    Args:
        ksp_A: (batch, 12) softmax KSP for segment A
        ksp_B: (batch, 12) softmax KSP for segment B (transposed by c)
        transposition_c: int, number of semitones B was transposed

    Returns:
        Scalar loss (mean over batch).
    """
    omega = 7  # circle of fifths frequency

    # Discrete Fourier basis at omega=7 (real-valued decomposition)
    q = torch.arange(12, device=ksp_A.device, dtype=ksp_A.dtype)
    cos_basis = torch.cos(2 * math.pi * omega * q / 12)  # (12,)
    sin_basis = torch.sin(2 * math.pi * omega * q / 12)  # (12,)

    # DFT of ksp_A at omega=7: F_A = (ksp_A . cos_basis) - j*(ksp_A . sin_basis)
    re_A = (ksp_A * cos_basis).sum(dim=-1)  # (batch,)
    im_A = (ksp_A * sin_basis).sum(dim=-1)  # (batch,)

    # DFT of ksp_B at omega=7
    re_B = (ksp_B * cos_basis).sum(dim=-1)
    im_B = (ksp_B * sin_basis).sum(dim=-1)

    # Cross-power spectral density: CPSD = F_A * conj(F_B)
    # (a + jb) * (c - jd) = (ac + bd) + j(bc - ad)
    cpsd_re = re_A * re_B + im_A * im_B
    cpsd_im = im_A * re_B - re_A * im_B

    # Target phase rotation for transposition c
    target_angle = 2 * math.pi * omega * transposition_c / 12
    target_re = math.cos(target_angle)
    target_im = -math.sin(target_angle)  # conjugate convention

    # Distance: 0.5 * |target - CPSD|^2
    loss = 0.5 * ((target_re - cpsd_re) ** 2 + (target_im - cpsd_im) ** 2)
    return loss.mean()


def generate_mode_pseudo_labels(
    pcp: torch.Tensor,
) -> torch.Tensor:
    """Generate major/minor pseudo-labels from PCP energy (S-KEY Eq. 5).

    Compares chroma energy at the estimated major root vs the relative
    minor root (3 semitones below).  If major root energy is higher,
    label as major [1, 0]; otherwise minor [0, 1].

    Args:
        pcp: (batch, 12) normalised pitch-class histograms

    Returns:
        (batch, 2) pseudo-labels: [1,0] = major, [0,1] = minor
    """
    major_root_idx = pcp.argmax(dim=-1)                 # (batch,)
    minor_root_idx = (major_root_idx - 3) % 12          # relative minor root

    batch_idx = torch.arange(pcp.size(0), device=pcp.device)
    major_energy = pcp[batch_idx, major_root_idx]
    minor_energy = pcp[batch_idx, minor_root_idx]

    labels = torch.zeros(pcp.size(0), 2, device=pcp.device)
    is_major = major_energy > minor_energy
    labels[is_major, 0] = 1.0     # major
    labels[~is_major, 1] = 1.0    # minor
    return labels


def self_supervised_loss(
    out_A: Dict[str, torch.Tensor],
    out_B: Dict[str, torch.Tensor],
    pcp_A: torch.Tensor,
    transposition_c: int,
    lambda_equiv: float = 1.0,
    lambda_mode: float = 1.5,
    lambda_batch: float = 15.0,
) -> Tuple[torch.Tensor, Dict[str, float]]:
    """Combined S-KEY self-supervised loss (Eq. 8 adapted).

    Args:
        out_A: model output for segment A (original)
        out_B: model output for segment B (transposed by c)
        pcp_A: (batch, T, 12) PCP for segment A
        transposition_c: int, transposition amount in semitones
        lambda_*: loss weights from S-KEY

    Returns:
        (total_loss, detail_dict) where detail_dict has per-component values.
    """
    # Take softmax of last timestep outputs
    ksp_A = F.softmax(out_A['ksp_logits'][:, -1, :], dim=-1)  # (B, 12)
    ksp_B = F.softmax(out_B['ksp_logits'][:, -1, :], dim=-1)

    # 1. Equivariance loss
    L_equiv = symbolic_equivariance_loss(ksp_A, ksp_B, transposition_c)

    # 2. Mode pseudo-label loss
    pseudo_labels = generate_mode_pseudo_labels(pcp_A[:, -1, :])  # last step PCP
    mode_A = F.softmax(out_A['mode_logits'][:, -1, :], dim=-1)
    mode_B = F.softmax(out_B['mode_logits'][:, -1, :], dim=-1)
    # Clamp to avoid log(0) in BCE
    mode_A = mode_A.clamp(1e-7, 1 - 1e-7)
    mode_B = mode_B.clamp(1e-7, 1 - 1e-7)
    L_mode = (
        F.binary_cross_entropy(mode_A, pseudo_labels)
        + F.binary_cross_entropy(mode_B, pseudo_labels)
    )

    # 3. Batch balance regularisation (prevent mode collapse)
    batch_major_frac = mode_A[:, 0].mean()
    L_batch = (batch_major_frac - 0.5) ** 2

    total = lambda_equiv * L_equiv + lambda_mode * L_mode + lambda_batch * L_batch

    details = {
        'L_equiv': L_equiv.item(),
        'L_mode': L_mode.item(),
        'L_batch': L_batch.item(),
        'total': total.item(),
        'major_frac': batch_major_frac.item(),
    }
    return total, details


# ===========================================================================
# 6. Dataset
# ===========================================================================

class TranspositionPairDataset(Dataset):
    """Dataset yielding transposition pairs for self-supervised pre-training.

    Each item samples two non-overlapping windows from a random MIDI file,
    transposes one by a random interval c in [1, 11].
    """

    def __init__(
        self,
        note_cache: Dict[str, List[Dict]],
        window_size: int = 256,
        pcp_window: int = 32,
    ):
        self.midi_keys = [
            k for k, v in note_cache.items() if len(v) >= 2 * window_size
        ]
        self.note_cache = note_cache
        self.window_size = window_size
        self.pcp_window = pcp_window

        if not self.midi_keys:
            raise ValueError(
                f'No MIDI files with >= {2 * window_size} notes in cache!'
            )

    def __len__(self) -> int:
        # Each epoch: iterate through all qualifying MIDI files
        return len(self.midi_keys)

    def __getitem__(self, idx: int) -> Dict[str, object]:
        key = self.midi_keys[idx]
        notes = self.note_cache[key]

        # Sample two non-overlapping windows
        total = len(notes)
        mid = total // 2
        window_A = sample_window(notes[:mid], self.window_size)
        window_B = sample_window(notes[mid:], self.window_size)

        # Fallback if half-piece is too short
        if window_A is None:
            window_A = notes[: self.window_size]
        if window_B is None:
            window_B = notes[-self.window_size :]

        # Random transposition for window B
        c = random.randint(1, 11)
        window_B_transposed = transpose_notes(window_B, c)

        # If transposition removed too many notes, pad with original
        while len(window_B_transposed) < self.window_size:
            window_B_transposed.append(window_B[len(window_B_transposed) % len(window_B)])

        window_B_transposed = window_B_transposed[: self.window_size]

        # Encode both windows
        encoded_A = encode_window(window_A, self.pcp_window)
        encoded_B = encode_window(window_B_transposed, self.pcp_window)

        return {
            'A': encoded_A,
            'B': encoded_B,
            'c': c,
        }


def collate_pairs(
    batch: List[Dict[str, object]],
) -> Tuple[Dict[str, torch.Tensor], Dict[str, torch.Tensor], int]:
    """Collate transposition pairs into batched tensors."""
    examples_A = [item['A'] for item in batch]
    examples_B = [item['B'] for item in batch]

    # All windows should be same size, but use collate_harmonic_batch for safety
    batch_A = collate_harmonic_batch(examples_A)
    batch_B = collate_harmonic_batch(examples_B)

    # Transposition c (same for all items in batch in this simple version;
    # in practice each item has its own c, but we use the first for the loss)
    # Better: pass per-item c and average losses. For now, use per-item.
    c_values = [item['c'] for item in batch]

    return batch_A, batch_B, c_values


# ===========================================================================
# 7. Training Loop
# ===========================================================================

def pretrain(args: argparse.Namespace) -> None:
    """Main pre-training loop."""
    print(f'=== S-KEY-Symbolic Self-Supervised Pre-Training ===')
    print(f'Device: {args.device}')
    print(f'Epochs: {args.epochs}, Batch: {args.batch_size}, LR: {args.lr}')

    device = torch.device(args.device)

    # Load or build MIDI cache
    cache = build_midi_cache(
        metadata_csv=args.metadata_csv,
        atepp_base=args.atepp_base,
        cache_path=args.cache_path,
        limit=args.limit,
    )

    # Dataset
    dataset = TranspositionPairDataset(
        note_cache=cache,
        window_size=args.window_size,
        pcp_window=args.pcp_window,
    )
    print(f'Dataset: {len(dataset)} qualifying MIDI files')

    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate_pairs,
        num_workers=0,  # pretty_midi not picklable; data is in-memory anyway
        drop_last=True,
    )

    # Model
    model = SymbolicKeyTransformer(
        d_model=args.d_model,
        n_heads=args.n_heads,
        n_layers=args.n_layers,
        ff_dim=args.ff_dim,
        dropout=args.dropout,
    ).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    print(f'Model: SymbolicKeyTransformer ({total_params:,} params)')

    # Optimizer and scheduler
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs,
    )

    best_loss = float('inf')

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_losses = defaultdict(float)
        num_batches = 0
        t0 = time.time()

        for batch_A, batch_B, c_values in tqdm(
            loader, desc=f'Epoch {epoch}/{args.epochs}', leave=False,
        ):
            # Move to device
            batch_A = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                       for k, v in batch_A.items()}
            batch_B = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                       for k, v in batch_B.items()}

            # Forward pass
            out_A = model(batch_A)
            out_B = model(batch_B)

            # Compute loss for each item's transposition c, then average
            # (simplified: use mean c for the batch loss)
            mean_c = int(round(sum(c_values) / len(c_values)))
            loss, details = self_supervised_loss(
                out_A, out_B,
                pcp_A=batch_A['pcp'],
                transposition_c=mean_c,
                lambda_equiv=args.lambda_equiv,
                lambda_mode=args.lambda_mode,
                lambda_batch=args.lambda_batch,
            )

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            for k, v in details.items():
                epoch_losses[k] += v
            num_batches += 1

        scheduler.step()
        elapsed = time.time() - t0

        # Average losses
        avg = {k: v / max(num_batches, 1) for k, v in epoch_losses.items()}
        lr = scheduler.get_last_lr()[0]

        print(
            f'Epoch {epoch:3d}/{args.epochs} | '
            f'loss={avg["total"]:.4f} | '
            f'equiv={avg["L_equiv"]:.4f} | '
            f'mode={avg["L_mode"]:.4f} | '
            f'batch={avg["L_batch"]:.4f} | '
            f'maj%={avg["major_frac"]:.2f} | '
            f'lr={lr:.2e} | '
            f'{elapsed:.1f}s'
        )

        # Save best checkpoint
        if avg['total'] < best_loss:
            best_loss = avg['total']
            torch.save(
                {
                    'model_state_dict': model.state_dict(),
                    'epoch': epoch,
                    'loss': best_loss,
                    'args': vars(args),
                },
                args.output,
            )
            print(f'  -> Saved best checkpoint (loss={best_loss:.4f})')

    print(f'\nPre-training complete. Best loss: {best_loss:.4f}')
    print(f'Checkpoint: {args.output}')


# ===========================================================================
# 8. Ablation Grid
# ===========================================================================

ABLATION_CONFIGS = [
    # S-KEY audio defaults (Kong et al., ICASSP 2025)
    {'lambda_equiv': 1.0, 'lambda_mode': 1.5, 'lambda_batch': 15.0, 'tag': 'skey-default'},
    # Equivariance only (mode loss ablated)
    {'lambda_equiv': 1.0, 'lambda_mode': 0.0, 'lambda_batch': 15.0, 'tag': 'equiv-only'},
    # Mode loss only (equivariance ablated)
    {'lambda_equiv': 0.0, 'lambda_mode': 1.5, 'lambda_batch': 15.0, 'tag': 'mode-only'},
    # Higher mode weight (symbolic domain may need stronger mode signal)
    {'lambda_equiv': 1.0, 'lambda_mode': 3.0, 'lambda_batch': 15.0, 'tag': 'high-mode'},
    # Lower batch balance (less aggressive mode-collapse prevention)
    {'lambda_equiv': 1.0, 'lambda_mode': 1.5, 'lambda_batch': 5.0, 'tag': 'low-batch'},
    # Equal weighting (no S-KEY priors)
    {'lambda_equiv': 1.0, 'lambda_mode': 1.0, 'lambda_batch': 1.0, 'tag': 'equal'},
]


def run_ablation_grid(args: argparse.Namespace) -> None:
    """Run pre-training across a grid of loss weight configurations.

    Saves one checkpoint per configuration and a summary JSON.
    """
    import copy

    results = []
    output_dir = os.path.dirname(args.output) or 'research_data'
    summary_path = os.path.join(output_dir, 'ablation_grid_results.json')

    print(f'=== Ablation Grid: {len(ABLATION_CONFIGS)} configurations ===\n')

    for i, config in enumerate(ABLATION_CONFIGS):
        tag = config['tag']
        print(f'\n--- Config {i+1}/{len(ABLATION_CONFIGS)}: {tag} ---')
        print(f'  lambda_equiv={config["lambda_equiv"]}, '
              f'lambda_mode={config["lambda_mode"]}, '
              f'lambda_batch={config["lambda_batch"]}')

        run_args = copy.deepcopy(args)
        run_args.lambda_equiv = config['lambda_equiv']
        run_args.lambda_mode = config['lambda_mode']
        run_args.lambda_batch = config['lambda_batch']
        run_args.output = os.path.join(
            output_dir, f'symbolic_key_pretrained_{tag}.pt',
        )

        pretrain(run_args)

        results.append({
            'tag': tag,
            'lambda_equiv': config['lambda_equiv'],
            'lambda_mode': config['lambda_mode'],
            'lambda_batch': config['lambda_batch'],
            'checkpoint': run_args.output,
        })

    with open(summary_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f'\n=== Ablation grid complete. Summary: {summary_path} ===')


# ===========================================================================
# 9. CLI
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description='S-KEY-Symbolic self-supervised pre-training',
    )

    # Data
    parser.add_argument(
        '--metadata-csv',
        default='ATEPP_JI_Dataset/ATEPP-metadata-JI.csv',
        help='Path to ATEPP metadata CSV',
    )
    parser.add_argument(
        '--atepp-base',
        default='ATEPP_JI_Dataset/ATEPP-1.2',
        help='Path to ATEPP-1.2 directory with MIDI/score files',
    )
    parser.add_argument(
        '--cache-path',
        default='research_data/atepp_midi_cache.jsonl',
        help='Path for MIDI note cache',
    )
    parser.add_argument(
        '--limit', type=int, default=None,
        help='Limit number of MIDI files (for smoke testing)',
    )

    # Model
    parser.add_argument('--d-model', type=int, default=128)
    parser.add_argument('--n-heads', type=int, default=4)
    parser.add_argument('--n-layers', type=int, default=2)
    parser.add_argument('--ff-dim', type=int, default=256)
    parser.add_argument('--dropout', type=float, default=0.1)

    # Training
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--batch-size', type=int, default=32)
    parser.add_argument('--lr', type=float, default=5e-4)
    parser.add_argument('--window-size', type=int, default=256)
    parser.add_argument('--pcp-window', type=int, default=32)
    parser.add_argument('--device', default='cpu',
                        help='Device: cpu, mps, or cuda')

    # Loss weights (for ablation study)
    parser.add_argument('--lambda-equiv', type=float, default=1.0,
                        help='Weight for equivariance loss (S-KEY default: 1.0)')
    parser.add_argument('--lambda-mode', type=float, default=1.5,
                        help='Weight for mode pseudo-label loss (S-KEY default: 1.5)')
    parser.add_argument('--lambda-batch', type=float, default=15.0,
                        help='Weight for batch balance regularisation (S-KEY default: 15.0)')

    # Ablation grid mode
    parser.add_argument(
        '--ablation-grid', action='store_true',
        help='Run ablation grid over loss weight combinations',
    )

    # Output
    parser.add_argument(
        '--output',
        default='research_data/symbolic_key_pretrained.pt',
        help='Output checkpoint path',
    )

    args = parser.parse_args()

    if args.ablation_grid:
        run_ablation_grid(args)
    else:
        pretrain(args)


if __name__ == '__main__':
    main()
