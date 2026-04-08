#!/usr/bin/env python3
"""
Compact causal harmonic-state model utilities.

The first model target is local key plus confidence for the score-free path.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence

import torch
import torch.nn.functional as F
from torch import nn


NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
KEY_LABELS = NOTE_NAMES + [f'{name}m' for name in NOTE_NAMES]
KEY_TO_INDEX = {key: idx for idx, key in enumerate(KEY_LABELS)}

CANONICAL_KEY_MAP = {
    'Cb': 'B',
    'Db': 'C#',
    'Eb': 'D#',
    'Fb': 'E',
    'Gb': 'F#',
    'Ab': 'G#',
    'Bb': 'A#',
    'Bbm': 'A#m',
    'Cbm': 'Bm',
    'Dbm': 'C#m',
    'Ebm': 'D#m',
    'Fbm': 'Em',
    'Gbm': 'F#m',
    'Abm': 'G#m',
}

DELTA_BUCKETS_MS = (0, 40, 80, 120, 180, 260, 360, 500, 700, 1000, 1400, 2000, 3000)
DURATION_BUCKETS_MS = (0, 40, 80, 120, 180, 260, 360, 500, 700, 1000, 1400, 2000, 4000)
VELOCITY_BUCKETS = tuple(range(0, 128, 8))


def compute_pcp(
    pitch_classes: Sequence[int],
    velocities: Sequence[float] | None = None,
    window_size: int = 32,
) -> List[List[float]]:
    """Compute pitch-class profile (PCP) for each note position.

    For each position t, builds a 12-bin histogram of pitch classes in the
    window [max(0, t-W+1), t+1], optionally weighted by velocity.
    The histogram is L1-normalised so each row sums to ~1.0.

    Args:
        pitch_classes: list of ints in [0, 11], one per note event
        velocities: optional list of floats, same length as pitch_classes
        window_size: number of notes in the sliding window (default 32)

    Returns:
        List of 12-element lists (one per note), each summing to ~1.0.
        If a window is empty, returns a uniform distribution [1/12]*12.
    """
    n = len(pitch_classes)
    if n == 0:
        return []

    result: List[List[float]] = []
    for t in range(n):
        histogram = [0.0] * 12
        start = max(0, t - window_size + 1)
        for i in range(start, t + 1):
            weight = velocities[i] if velocities is not None else 1.0
            histogram[pitch_classes[i]] += weight
        total = sum(histogram)
        if total > 0:
            result.append([h / total for h in histogram])
        else:
            result.append([1.0 / 12] * 12)
    return result


def regularise_key_sequence(
    key_predictions: Sequence[int],
    min_segment_beats: float = 4.0,
    onset_beats: Sequence[float] | None = None,
    min_segment_notes: int = 8,
) -> List[int]:
    """Suppress short key segments (tonicizations) per Gedizlioglu & Erol (2024).

    Walks through the prediction sequence, identifies runs of consecutive
    identical keys, and absorbs segments shorter than min_segment_beats
    (or min_segment_notes if onset_beats is not available) into the
    preceding segment.

    Args:
        key_predictions: list of key indices (0-23), one per note
        min_segment_beats: minimum duration in beats for a key segment to survive
        onset_beats: beat position of each note (same length as key_predictions)
        min_segment_notes: fallback minimum when onset_beats is unavailable

    Returns:
        Regularised key prediction list (same length as input).
    """
    if len(key_predictions) <= 1:
        return list(key_predictions)

    use_beats = onset_beats is not None and len(onset_beats) == len(key_predictions)

    # Step 1: identify segments of consecutive identical keys
    segments = []  # (start_idx, end_idx, key, duration_or_count)
    seg_start = 0
    for i in range(1, len(key_predictions)):
        if key_predictions[i] != key_predictions[seg_start]:
            if use_beats:
                duration = onset_beats[i] - onset_beats[seg_start]
            else:
                duration = float(i - seg_start)
            segments.append((seg_start, i, key_predictions[seg_start], duration))
            seg_start = i

    # Final segment
    if use_beats:
        final_dur = onset_beats[-1] - onset_beats[seg_start] + 0.5
    else:
        final_dur = float(len(key_predictions) - seg_start)
    segments.append((seg_start, len(key_predictions), key_predictions[seg_start], final_dur))

    # Step 2: absorb short segments into neighbours
    threshold = min_segment_beats if use_beats else float(min_segment_notes)
    result = list(key_predictions)

    for start, end, key, duration in segments:
        if duration < threshold:
            # Use the preceding segment's key (conservative: maintain existing key)
            if start > 0:
                fill_key = result[start - 1]
            elif end < len(result):
                fill_key = key_predictions[end] if end < len(key_predictions) else key
            else:
                fill_key = key
            for j in range(start, end):
                result[j] = fill_key

    return result


def key_to_index(key_name: str) -> int:
    canonical = CANONICAL_KEY_MAP.get(key_name, key_name)
    return KEY_TO_INDEX[canonical]


def index_to_key(index: int) -> str:
    return KEY_LABELS[index]


def bucketize(value: float, boundaries: Sequence[float]) -> int:
    for idx, boundary in enumerate(boundaries):
        if value <= boundary:
            return idx
    return len(boundaries)


def register_bucket(midi_note: int) -> int:
    return max(0, min(10, (midi_note // 12) - 1))


def build_active_mask(active_notes: Iterable[int]) -> List[float]:
    mask = [0.0] * 12
    for note in active_notes:
        mask[int(note) % 12] = 1.0
    return mask


def encode_live_events(note_events: Sequence[Dict[str, object]]) -> Dict[str, List[object]]:
    pitch_classes: List[int] = []
    registers: List[int] = []
    delta_buckets: List[int] = []
    duration_buckets: List[int] = []
    velocity_buckets: List[int] = []
    active_masks: List[List[float]] = []

    previous_time = None
    for event in note_events:
        note = int(event['note'])
        event_time = float(event.get('time_ms', 0.0))
        delta_ms = 0.0 if previous_time is None else max(0.0, event_time - previous_time)
        previous_time = event_time

        duration_ms = float(event.get('duration_ms', 0.0))
        velocity = int(event.get('velocity', 96))
        active_notes = event.get('active_notes', [])

        pitch_classes.append(note % 12)
        registers.append(register_bucket(note))
        delta_buckets.append(bucketize(delta_ms, DELTA_BUCKETS_MS))
        duration_buckets.append(bucketize(duration_ms, DURATION_BUCKETS_MS))
        velocity_buckets.append(bucketize(velocity, VELOCITY_BUCKETS))
        active_masks.append(build_active_mask(active_notes))

    return {
        'pitch_class': pitch_classes,
        'register': registers,
        'delta_bucket': delta_buckets,
        'duration_bucket': duration_buckets,
        'velocity_bucket': velocity_buckets,
        'active_mask': active_masks,
    }


def pad_sequence(values: Sequence[int], target_length: int, pad_value: int = 0) -> List[int]:
    return list(values) + [pad_value] * max(0, target_length - len(values))


def pad_mask(values: Sequence[Sequence[float]], target_length: int) -> List[List[float]]:
    values = [list(row) for row in values]
    return values + ([[0.0] * 12] * max(0, target_length - len(values)))


def collate_harmonic_batch(examples: Sequence[Dict[str, object]]) -> Dict[str, torch.Tensor]:
    lengths = [len(example['pitch_class']) for example in examples]
    max_length = max(lengths)

    has_pcp = 'pcp' in examples[0]

    batch: Dict[str, object] = {
        'pitch_class': [],
        'register': [],
        'delta_bucket': [],
        'duration_bucket': [],
        'velocity_bucket': [],
        'active_mask': [],
        'labels': [],
        'lengths': torch.tensor(lengths, dtype=torch.long),
    }
    if has_pcp:
        batch['pcp'] = []

    for example in examples:
        batch['pitch_class'].append(pad_sequence(example['pitch_class'], max_length, 0))
        batch['register'].append(pad_sequence(example['register'], max_length, 0))
        batch['delta_bucket'].append(pad_sequence(example['delta_bucket'], max_length, 0))
        batch['duration_bucket'].append(pad_sequence(example['duration_bucket'], max_length, 0))
        batch['velocity_bucket'].append(pad_sequence(example['velocity_bucket'], max_length, 0))
        batch['active_mask'].append(pad_mask(example['active_mask'], max_length))
        batch['labels'].append(pad_sequence(example['labels'], max_length, -100))
        if has_pcp:
            batch['pcp'].append(pad_mask(example['pcp'], max_length))

    result = {
        'pitch_class': torch.tensor(batch['pitch_class'], dtype=torch.long),
        'register': torch.tensor(batch['register'], dtype=torch.long),
        'delta_bucket': torch.tensor(batch['delta_bucket'], dtype=torch.long),
        'duration_bucket': torch.tensor(batch['duration_bucket'], dtype=torch.long),
        'velocity_bucket': torch.tensor(batch['velocity_bucket'], dtype=torch.long),
        'active_mask': torch.tensor(batch['active_mask'], dtype=torch.float32),
        'labels': torch.tensor(batch['labels'], dtype=torch.long),
        'lengths': batch['lengths'],
    }
    if has_pcp:
        result['pcp'] = torch.tensor(batch['pcp'], dtype=torch.float32)
    return result


class HarmonicContextGRU(nn.Module):
    def __init__(
        self,
        hidden_size: int = 96,
        num_layers: int = 1,
        dropout: float = 0.1,
        bidirectional: bool = False,
        use_pcp: bool = False,
    ):
        super().__init__()
        self.bidirectional = bidirectional
        self.use_pcp = use_pcp

        self.pitch_embedding = nn.Embedding(12, 32)
        self.register_embedding = nn.Embedding(11, 8)
        self.delta_embedding = nn.Embedding(len(DELTA_BUCKETS_MS) + 1, 8)
        self.duration_embedding = nn.Embedding(len(DURATION_BUCKETS_MS) + 1, 8)
        self.velocity_embedding = nn.Embedding(len(VELOCITY_BUCKETS) + 1, 8)
        self.active_projection = nn.Linear(12, 16)

        feature_size = 32 + 8 + 8 + 8 + 8 + 16  # = 80
        if use_pcp:
            # Add PCP projection (12-dim histogram -> 16-dim embedding)
            self.pcp_projection = nn.Linear(12, 16)
            feature_size += 16  # = 96

        self.input_projection = nn.Linear(feature_size, hidden_size)
        self.encoder = nn.GRU(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
            bidirectional=bidirectional,
        )
        self.dropout = nn.Dropout(dropout)
        # Bidirectional doubles the output dimension
        classifier_input = hidden_size * 2 if bidirectional else hidden_size
        self.classifier = nn.Linear(classifier_input, len(KEY_LABELS))

    def forward(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        feature_parts = [
            self.pitch_embedding(batch['pitch_class']),
            self.register_embedding(batch['register']),
            self.delta_embedding(batch['delta_bucket']),
            self.duration_embedding(batch['duration_bucket']),
            self.velocity_embedding(batch['velocity_bucket']),
            self.active_projection(batch['active_mask']),
        ]
        if self.use_pcp:
            feature_parts.append(self.pcp_projection(batch['pcp']))

        features = torch.cat(feature_parts, dim=-1)
        projected = self.input_projection(features)
        encoded, _ = self.encoder(projected)
        return self.classifier(self.dropout(encoded))

    @torch.no_grad()
    def predict_last_step(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        logits = self.forward(batch)
        lengths = batch['lengths']
        batch_indices = torch.arange(logits.shape[0], device=logits.device)
        last_indices = torch.clamp(lengths - 1, min=0)
        return logits[batch_indices, last_indices]


class SymbolicKeyTransformer(nn.Module):
    """Two-branch causal Transformer for local key estimation.

    Adapts S-KEY (Kong et al., ICASSP 2025) from audio to symbolic MIDI
    using the OctaveNet two-branch design (Ding & Weiss, EUSIPCO 2024).

    Branch 1 (PCP): octave-folded pitch-class histogram -> d_model
    Branch 2 (Raw): per-note features with octave info  -> d_model
    Fusion:  concat + project -> causal Transformer -> output heads

    Positional encoding: learnable embeddings up to max_seq_len, with a
    sliding-window inference policy for sequences exceeding this limit.
    At inference time, only the most recent max_seq_len notes are used,
    which is acceptable because key detection is a local property —
    harmonic context beyond ~500 notes contributes negligible information.

    Note on RoPE: Rotary Position Embedding (Su et al., arXiv:2104.09864)
    would be the ideal choice for unbounded sequences, but requires custom
    attention layers (RoPE rotates Q and K inside attention, not the input).
    Since nn.TransformerEncoderLayer does not expose Q/K hooks, and the
    overhead of a custom attention implementation is not justified for a
    2-layer model with a naturally local task, we use learnable embeddings
    with the sliding-window policy described above.

    Output heads:
      key_logits  (B, T, 24) — 12 major + 12 minor key classes
      mode_logits (B, T, 2)  — major vs minor (self-supervised pre-training)
      ksp_logits  (B, T, 12) — key signature profile (equivariance loss)
    """

    def __init__(
        self,
        d_model: int = 128,
        n_heads: int = 4,
        n_layers: int = 2,
        ff_dim: int = 256,
        dropout: float = 0.1,
        max_seq_len: int = 512,
    ):
        super().__init__()
        self.d_model = d_model
        self.max_seq_len = max_seq_len

        # --- Branch 1: Pitch-Class Profile (octave-folded) ---
        self.pcp_projection = nn.Linear(12, d_model)

        # --- Branch 2: Raw pitch features (reuses GRU embedding sizes) ---
        self.pitch_embedding = nn.Embedding(12, 32)
        self.register_embedding = nn.Embedding(11, 8)
        self.delta_embedding = nn.Embedding(len(DELTA_BUCKETS_MS) + 1, 8)
        self.duration_embedding = nn.Embedding(len(DURATION_BUCKETS_MS) + 1, 8)
        self.velocity_embedding = nn.Embedding(len(VELOCITY_BUCKETS) + 1, 8)
        self.active_projection = nn.Linear(12, 16)
        raw_feature_size = 32 + 8 + 8 + 8 + 8 + 16  # = 80
        self.raw_projection = nn.Linear(raw_feature_size, d_model)

        # --- Fusion ---
        self.fusion = nn.Linear(2 * d_model, d_model)

        # --- Positional encoding (learnable) ---
        self.pos_embedding = nn.Embedding(max_seq_len, d_model)

        # --- Causal Transformer encoder ---
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=ff_dim,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(
            encoder_layer, num_layers=n_layers,
        )
        self.dropout = nn.Dropout(dropout)

        # --- Output heads ---
        self.key_head = nn.Linear(d_model, len(KEY_LABELS))   # 24 keys
        self.mode_head = nn.Linear(d_model, 2)                 # major/minor
        self.ksp_head = nn.Linear(d_model, 12)                 # KSP for equivariance

    def forward(self, batch: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        """Forward pass through both branches, fusion, and Transformer.

        Args:
            batch: dict with keys 'pcp' (B,T,12), 'pitch_class' (B,T),
                   'register' (B,T), 'delta_bucket' (B,T),
                   'duration_bucket' (B,T), 'velocity_bucket' (B,T),
                   'active_mask' (B,T,12).

        Returns:
            dict with 'key_logits' (B,T,24), 'mode_logits' (B,T,2),
            'ksp_logits' (B,T,12).
        """
        B, T = batch['pitch_class'].shape

        # Sliding-window policy: if sequence exceeds max_seq_len, use only
        # the most recent max_seq_len notes. Key detection is local — context
        # beyond ~500 notes contributes negligible harmonic information.
        if T > self.max_seq_len:
            offset = T - self.max_seq_len
            batch = {
                k: v[:, offset:] if isinstance(v, torch.Tensor) and v.dim() >= 2
                else v
                for k, v in batch.items()
            }
            T = self.max_seq_len

        # Branch 1: PCP -> d_model
        branch1 = self.pcp_projection(batch['pcp'])  # (B, T, d_model)

        # Branch 2: concatenate raw feature embeddings -> d_model
        raw_features = torch.cat(
            [
                self.pitch_embedding(batch['pitch_class']),
                self.register_embedding(batch['register']),
                self.delta_embedding(batch['delta_bucket']),
                self.duration_embedding(batch['duration_bucket']),
                self.velocity_embedding(batch['velocity_bucket']),
                self.active_projection(batch['active_mask']),
            ],
            dim=-1,
        )  # (B, T, 80)
        branch2 = self.raw_projection(raw_features)  # (B, T, d_model)

        # Fuse the two branches
        fused = self.fusion(torch.cat([branch1, branch2], dim=-1))  # (B, T, d_model)

        # Add learnable positional encoding
        positions = torch.arange(T, device=fused.device).unsqueeze(0)  # (1, T)
        fused = fused + self.pos_embedding(positions)

        # Causal mask: prevent attending to future positions
        causal_mask = torch.triu(
            torch.ones(T, T, device=fused.device), diagonal=1,
        ).bool()  # True = "mask out this position"

        # Transformer encoder
        encoded = self.transformer(
            self.dropout(fused), mask=causal_mask, is_causal=True,
        )  # (B, T, d_model)

        return {
            'key_logits': self.key_head(encoded),    # (B, T, 24)
            'mode_logits': self.mode_head(encoded),   # (B, T, 2)
            'ksp_logits': self.ksp_head(encoded),     # (B, T, 12)
        }

    @torch.no_grad()
    def predict_last_step(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        """Return key logits at the last valid position (for runtime inference)."""
        outputs = self.forward(batch)
        logits = outputs['key_logits']
        lengths = batch['lengths']
        batch_indices = torch.arange(logits.shape[0], device=logits.device)
        last_indices = torch.clamp(lengths - 1, min=0)
        return logits[batch_indices, last_indices]
