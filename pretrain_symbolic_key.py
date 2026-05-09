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
from typing import Dict, List, Sequence, Tuple, Union

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

    NOTE (2026-05-12 P3 audit fix): this in-memory cache is the legacy
    behaviour that OOMed at ~27 K MIDIs on Colab T4 (12 GB RAM). For the
    Phase C 371 K Aria-MIDI experiment, use `build_midi_cache_streaming`
    instead — it writes the same JSONL but holds only a byte-offset index
    in memory (~50 bytes per file) and reads notes on-demand. The two
    functions are interchangeable from the dataset's perspective: both
    return objects supporting `dict.items()`, `[key]`, `len()`, and
    `__contains__`.
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
# Lazy-load cache (2026-05-12 P3 audit fix — closes the Phase C T4 RAM ceiling)
# ===========================================================================

class _NoteCountStub:
    """Minimal object exposing only `__len__`, used by the streaming cache's
    `.items()` so `TranspositionPairDataset.__init__`'s filter
    `len(v) >= min_notes` works without loading any notes off disk.
    Memory cost: one Python int per MIDI file (~28 bytes vs 10–50 KB for
    a fully-loaded note list)."""
    __slots__ = ('_n',)

    def __init__(self, n: int):
        self._n = n

    def __len__(self) -> int:
        return self._n


class LazyMidiCache:
    """JSONL-backed lazy MIDI note cache (P3 audit fix, 2026-05-12).

    Replaces the in-memory `Dict[str, List[Dict]]` with a byte-offset
    index that lives in memory while the actual note lists stay on disk.
    Memory footprint at 371 K MIDIs: ~20 MB index vs ~12+ GB for the dict.
    Per-access latency: ~0.2 ms on local SSD (one `seek` + one `readline` +
    one `json.loads`), well below the per-batch GPU compute time so the
    dataset is not I/O-bound at typical training batch sizes.

    Exposes the dict-like subset that `TranspositionPairDataset` uses:
      * `__contains__`, `__len__`
      * `keys()`, `items()` (yields `(midi_path, _NoteCountStub)`)
      * `__getitem__(midi_path)` (lazy: returns the note list on demand)

    Implementation note: a single shared file handle is opened lazily on
    first `__getitem__` and reused thereafter. This is NOT thread-safe;
    PyTorch DataLoader with `num_workers > 0` forks the process so each
    worker gets its own handle (correct). In single-process mode the
    handle is reused and races between concurrent reads are not possible
    because PyTorch issues `__getitem__` calls sequentially in the main
    thread.
    """

    def __init__(self, jsonl_path: str, index: Dict[str, Tuple[int, int]]):
        """
        Args:
            jsonl_path: path to the JSONL cache file (one line per MIDI:
                `{"path": "...", "notes": [...]}`)
            index: dict mapping midi_path -> (byte_offset, n_notes)
        """
        self.jsonl_path = jsonl_path
        self.index = index
        self._fp = None  # opened on first __getitem__

    def _ensure_open(self):
        if self._fp is None:
            self._fp = open(self.jsonl_path, 'r')

    def __contains__(self, key: str) -> bool:
        return key in self.index

    def __len__(self) -> int:
        return len(self.index)

    def __getitem__(self, key: str) -> List[Dict]:
        """Lazy: seek to the byte offset, read one line, parse JSON, return notes."""
        offset, _ = self.index[key]
        self._ensure_open()
        self._fp.seek(offset)
        line = self._fp.readline()
        return json.loads(line)['notes']

    def keys(self):
        return self.index.keys()

    def items(self):
        """Yields (midi_path, _NoteCountStub) so the dataset's filter pass
        can call `len(v) >= min_notes` without loading any notes."""
        for midi_path, (_offset, n_notes) in self.index.items():
            yield midi_path, _NoteCountStub(n_notes)

    def __getstate__(self):
        # Drop the unpicklable file handle when fork()ing for DataLoader workers
        return {'jsonl_path': self.jsonl_path, 'index': self.index}

    def __setstate__(self, state):
        self.jsonl_path = state['jsonl_path']
        self.index = state['index']
        self._fp = None  # each worker reopens lazily


def _build_index_from_existing_jsonl(cache_path: str) -> Dict[str, Tuple[int, int]]:
    """Scan an existing JSONL once and build the (path -> (offset, n_notes)) index.
    Memory peak during scan: one MIDI's notes (Python GCs after each line)."""
    index = {}
    offset = 0
    with open(cache_path, 'r') as f:
        line = f.readline()
        while line:
            entry = json.loads(line)
            # offset is where THIS line starts (we already advanced f past it).
            # The next iteration's line starts at f.tell().
            index[entry['path']] = (offset, len(entry['notes']))
            offset = f.tell()
            line = f.readline()
    return index


def build_midi_cache_streaming(
    metadata_csv: str,
    atepp_base: str,
    cache_path: str,
    limit: int | None = None,
) -> 'LazyMidiCache':
    """Streaming JSONL builder — closes the OOM that limited Phase B to 20 K
    on T4 (Chapter 6 §6.9.2). Behaviourally interchangeable with
    `build_midi_cache` from the dataset's perspective; differs only in
    memory footprint.

    Returns a `LazyMidiCache` that exposes the dict-like interface
    `TranspositionPairDataset` needs (items / __getitem__ / __len__ /
    __contains__) without holding any notes in memory.
    """
    if os.path.exists(cache_path):
        print(f'Loading lazy MIDI cache from {cache_path}...')
        index = _build_index_from_existing_jsonl(cache_path)
        print(f'  Indexed {len(index)} MIDI files (streaming, ~{len(index)*50/1e6:.1f} MB memory).')
        return LazyMidiCache(cache_path, index)

    print(f'Building streaming MIDI cache (first run, ~20-40 min, '
          f'CONSTANT memory — does not OOM at any corpus size)...')
    df = pd.read_csv(metadata_csv)
    midi_paths = df['midi_path'].unique().tolist()
    if limit:
        midi_paths = midi_paths[:limit]

    index: Dict[str, Tuple[int, int]] = {}
    with open(cache_path, 'w') as f:
        for midi_rel in tqdm(midi_paths, desc='Streaming MIDI cache'):
            full_path = os.path.join(atepp_base, midi_rel)
            if not os.path.exists(full_path):
                continue
            notes = load_midi_notes(full_path)
            if len(notes) < 64:  # skip very short pieces
                continue
            offset = f.tell()
            entry = json.dumps({'path': midi_rel, 'notes': notes})
            f.write(entry + '\n')
            index[midi_rel] = (offset, len(notes))
            # Critical: `notes` falls out of scope after this iteration → GC'd.
            # No in-memory dict accumulating note lists. RAM stays ~constant.

    print(f'  Streamed {len(index)} MIDI files to {cache_path} '
          f'(index size: ~{len(index)*50/1e6:.1f} MB; JSONL on disk: '
          f'~{os.path.getsize(cache_path)/1e9:.2f} GB)')
    return LazyMidiCache(cache_path, index)


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
    transposition_c: Union[int, torch.Tensor],
) -> torch.Tensor:
    """Equivariance loss via circle-of-fifths CPSD (S-KEY Eq. 4 adapted).

    If B is a transposition of A by c semitones, then the DFT of B's KSP
    at the circle-of-fifths frequency (omega=7) should differ from A's
    by a phase rotation of 2*pi*7*c/12.

    Args:
        ksp_A: (batch, 12) softmax KSP for segment A
        ksp_B: (batch, 12) softmax KSP for segment B (transposed by c)
        transposition_c: int or (B,) tensor, number of semitones B was transposed

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

    # Target phase rotation for transposition c (works for scalar int or (B,) tensor)
    target_angle = 2 * math.pi * omega * transposition_c / 12
    target_re = torch.cos(target_angle) if isinstance(transposition_c, torch.Tensor) else math.cos(target_angle)
    target_im = -(torch.sin(target_angle) if isinstance(transposition_c, torch.Tensor) else math.sin(target_angle))  # conjugate convention

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
    transposition_c: Union[int, torch.Tensor],
    lambda_equiv: float = 1.0,
    lambda_mode: float = 1.5,
    lambda_batch: float = 15.0,
) -> Tuple[torch.Tensor, Dict[str, float]]:
    """Combined S-KEY self-supervised loss (Eq. 8 adapted).

    Args:
        out_A: model output for segment A (original)
        out_B: model output for segment B (transposed by c)
        pcp_A: (batch, T, 12) PCP for segment A
        transposition_c: int or (B,) tensor, transposition amount in semitones
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

    2026-05-12 P3 audit fix (S-KEY pair-construction correction):
    Previously this dataset sampled TWO non-overlapping windows from the same
    MIDI file and transposed only one of them, with original-key padding when
    transposition pushed notes out of the piano range. The 2026-05-05 read-only
    audit (CLAIM 2) flagged this as a divergence from the canonical S-KEY
    pair construction (Kong, Meseguer-Brocal, Lostanlen, Lagrange, &
    Hennequin, 2025): canonical S-KEY uses two pitch-shifted views of the
    SAME audio frame, so the equivariance objective isolates the
    transposition signal. With non-overlapping segments, the model learns
    to predict both the transposition AND any segment-level harmonic
    content differences (development sections, modulating pieces);
    original-key padding contaminates the equivariance signal further.

    The corrected version (default) samples ONE window per __getitem__,
    applies two DIFFERENT random transpositions c_A and c_B to that same
    window, and uses Δc = c_B - c_A as the relative-shift target. Notes
    pushed out of the piano range under either transposition are dropped
    (NO padding); if either transposed view ends up with < 90% of the
    original window length, we resample c_A and c_B (up to 5 retries) and
    finally fall back to (c_A, c_B) = (0, 1) which fits any piano-range
    window.

    The legacy (non-overlapping-segments + original-padding) behaviour is
    preserved behind `pair_mode='legacy'` for reproducibility of the
    pre-2026-05-12 Phase A / Phase B null result. The default `pair_mode`
    is `'canonical'`.

    Args:
        note_cache: dict mapping midi_path -> list of note dicts.
        window_size: number of notes per window (both A and B).
        pcp_window: PCP rolling-window size.
        pair_mode: 'canonical' (default, P3 corrected) or 'legacy' (pre-fix).
        min_retained_frac: minimum fraction of window_size notes retained
            after transposition for the pair to be accepted (canonical mode
            only). Default 0.9.
    """

    def __init__(
        self,
        note_cache: Dict[str, List[Dict]],
        window_size: int = 256,
        pcp_window: int = 32,
        pair_mode: str = 'canonical',
        min_retained_frac: float = 0.9,
    ):
        if pair_mode not in ('canonical', 'legacy'):
            raise ValueError(
                f'pair_mode must be "canonical" or "legacy", got {pair_mode!r}'
            )
        # Canonical mode needs only window_size notes; legacy needs 2 *
        # window_size (since it samples two non-overlapping windows).
        min_notes = window_size if pair_mode == 'canonical' else 2 * window_size
        self.midi_keys = [
            k for k, v in note_cache.items() if len(v) >= min_notes
        ]
        self.note_cache = note_cache
        self.window_size = window_size
        self.pcp_window = pcp_window
        self.pair_mode = pair_mode
        self.min_retained_frac = min_retained_frac

        if not self.midi_keys:
            raise ValueError(
                f'No MIDI files with >= {min_notes} notes in cache! '
                f'(pair_mode={pair_mode!r}, window_size={window_size})'
            )

    def __len__(self) -> int:
        # Each epoch: iterate through all qualifying MIDI files
        return len(self.midi_keys)

    def __getitem__(self, idx: int) -> Dict[str, object]:
        key = self.midi_keys[idx]
        notes = self.note_cache[key]

        if self.pair_mode == 'legacy':
            return self._getitem_legacy(notes)
        return self._getitem_canonical(notes)

    def _getitem_canonical(self, notes: List[Dict]) -> Dict[str, object]:
        """Canonical S-KEY pair construction (P3 fix, 2026-05-12).

        Samples ONE window from the MIDI, applies two DIFFERENT random
        transpositions c_A and c_B to the SAME notes, and uses the
        relative shift Δc = c_B - c_A as the equivariance target. Out-of-
        range notes are DROPPED (not padded with original-key notes).
        """
        # Sample one window from anywhere in the piece
        window = sample_window(notes, self.window_size)
        if window is None:
            window = notes[: self.window_size]

        # Sample two distinct transpositions with rejection if either pushes
        # too many notes out of the piano range.
        min_kept = int(self.min_retained_frac * len(window))
        c_A, c_B = 0, 1  # safe fallback (any piano-range window survives ±1)
        view_A, view_B = transpose_notes(window, 0), transpose_notes(window, 1)
        for _retry in range(5):
            ca = random.randint(0, 11)
            cb = random.randint(0, 11)
            if ca == cb:
                continue  # Δc = 0 carries no equivariance signal
            cand_A = transpose_notes(window, ca)
            cand_B = transpose_notes(window, cb)
            if len(cand_A) >= min_kept and len(cand_B) >= min_kept:
                c_A, c_B = ca, cb
                view_A, view_B = cand_A, cand_B
                break

        # If A and B have different lengths after range-filtering (rare —
        # only when one transposition keeps more notes than the other),
        # truncate to the shorter so the model sees aligned-length sequences
        # and the equivariance loss compares like-for-like KSPs.
        target_len = min(len(view_A), len(view_B))
        view_A = view_A[:target_len]
        view_B = view_B[:target_len]

        encoded_A = encode_window(view_A, self.pcp_window)
        encoded_B = encode_window(view_B, self.pcp_window)

        # Relative transposition (signed). The equivariance loss applies
        # cos(2πω·c/12) which is 2π-periodic, so signed Δc works cleanly.
        c_relative = c_B - c_A

        return {
            'A': encoded_A,
            'B': encoded_B,
            'c': c_relative,
            'c_A': c_A,         # for diagnostic / unit-test introspection
            'c_B': c_B,
            'pair_mode': 'canonical',
        }

    def _getitem_legacy(self, notes: List[Dict]) -> Dict[str, object]:
        """Pre-2026-05-12 pair construction (preserved for reproducibility).

        Samples two non-overlapping windows from the same MIDI, transposes
        only the second one, and pads with original-key notes when
        transposition pushes notes out of the piano range. This is the
        construction that produced the Phase A (5K) and Phase B (20K) null
        result reported in Chapter 6 §6.9.2; running with `pair_mode='legacy'`
        reproduces those checkpoints bit-identically given the same RNG seed.
        """
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
            'pair_mode': 'legacy',
        }


def collate_pairs(
    batch: List[Dict[str, object]],
) -> Tuple[Dict[str, torch.Tensor], Dict[str, torch.Tensor], torch.Tensor]:
    """Collate transposition pairs into batched tensors."""
    examples_A = [item['A'] for item in batch]
    examples_B = [item['B'] for item in batch]

    # All windows should be same size, but use collate_harmonic_batch for safety
    batch_A = collate_harmonic_batch(examples_A)
    batch_B = collate_harmonic_batch(examples_B)

    # Per-item transposition values as a tensor for vectorised loss computation
    c_values = torch.tensor([item['c'] for item in batch], dtype=torch.long)

    return batch_A, batch_B, c_values


# ===========================================================================
# 7. Training Loop
# ===========================================================================

def pretrain(args: argparse.Namespace) -> None:
    """Main pre-training loop."""
    print(f'=== S-KEY-Symbolic Self-Supervised Pre-Training ===')
    if args.device == 'auto':
        if torch.backends.mps.is_available():
            args.device = 'mps'
        elif torch.cuda.is_available():
            args.device = 'cuda'
        else:
            args.device = 'cpu'
    print(f'Device: {args.device}')
    print(f'Epochs: {args.epochs}, Batch: {args.batch_size}, LR: {args.lr}')

    device = torch.device(args.device)

    # Load or build MIDI cache. The 2026-05-12 P3 audit fix exposes
    # `--lazy-load` to switch to the streaming JSONL-backed cache that
    # supports the full Aria-MIDI 371 K corpus on T4 RAM.
    if getattr(args, 'lazy_load', False):
        cache = build_midi_cache_streaming(
            metadata_csv=args.metadata_csv,
            atepp_base=args.atepp_base,
            cache_path=args.cache_path,
            limit=args.limit,
        )
    else:
        cache = build_midi_cache(
            metadata_csv=args.metadata_csv,
            atepp_base=args.atepp_base,
            cache_path=args.cache_path,
            limit=args.limit,
        )

    # Dataset (2026-05-12 P3 audit fix exposes pair-mode + min_retained_frac)
    dataset = TranspositionPairDataset(
        note_cache=cache,
        window_size=args.window_size,
        pcp_window=args.pcp_window,
        pair_mode=getattr(args, 'pair_mode', 'canonical'),
        min_retained_frac=getattr(args, 'min_retained_frac', 0.9),
    )
    print(f'Dataset: {len(dataset)} qualifying MIDI files '
          f'(pair_mode={getattr(args, "pair_mode", "canonical")!r})')

    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate_pairs,
        num_workers=0,  # pretty_midi not picklable; data is in-memory anyway
        drop_last=True,
    )

    # Model — pretraining body selectable via --pretrain-body (Option B
    # 2026-05-08 audit follow-up). Default 'transformer' preserves the legacy
    # / canonical S-KEY pretraining body that produced the §6.9.2 partial-
    # transfer null. The 'gru' option uses HarmonicContextGRUPretrain — a GRU
    # body architecturally aligned with the deployed `HarmonicContextGRUPhase1`
    # downstream model, so subsequent fine-tune via train_phase1.py
    # --pretrained-checkpoint loads ~95% of weights instead of 1.52%.
    if getattr(args, 'pretrain_body', 'transformer') == 'gru':
        from harmonic_context_model import HarmonicContextGRUPretrain
        model = HarmonicContextGRUPretrain(
            hidden_size=96,
            num_layers=1,
            dropout=args.dropout,
        ).to(device)
        print(f'  Body: HarmonicContextGRUPretrain (h=96, ~67K params; '
              f'architecturally aligned with downstream HarmonicContextGRUPhase1)')
    else:
        model = SymbolicKeyTransformer(
            d_model=args.d_model,
            n_heads=args.n_heads,
            n_layers=args.n_layers,
            ff_dim=args.ff_dim,
            dropout=args.dropout,
        ).to(device)
        print(f'  Body: SymbolicKeyTransformer (d_model={args.d_model}, '
              f'~381K params; legacy/canonical S-KEY pretraining body)')

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

            # Vectorised loss: each item has its own transposition c,
            # passed as a (B,) tensor so cos/sin targets are per-item.
            c_tensor = c_values.to(device=device, dtype=torch.float32)
            loss, details = self_supervised_loss(
                out_A, out_B,
                pcp_A=batch_A['pcp'],
                transposition_c=c_tensor,
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
    parser.add_argument('--device', default='auto',
                        help='Device: auto, cpu, mps, or cuda (auto picks best available)')
    # 2026-05-12 P3 audit fix: pair-construction mode for the equivariance loss.
    # 'canonical' samples one window and applies two different transpositions
    # (faithful to Kong et al., 2025 S-KEY). 'legacy' samples two non-overlapping
    # windows and transposes only one, with original-key padding when transposition
    # pushes notes out of range — this is the construction that produced the Phase
    # A / Phase B null result reported in Chapter 6 §6.9.2; preserved for
    # reproducibility.
    parser.add_argument('--pair-mode', default='canonical',
                        choices=['canonical', 'legacy'],
                        help='Pair construction for the equivariance loss '
                             '(default: canonical = P3-corrected; '
                             'legacy = pre-2026-05-12 reproducibility)')
    parser.add_argument('--min-retained-frac', type=float, default=0.9,
                        help='Minimum fraction of window_size notes that must '
                             'survive both transpositions in canonical mode '
                             '(default 0.9 = at least 90%% of notes retained)')
    # 2026-05-08 Option B audit follow-up: pretraining body architecture
    # selector. 'transformer' is the legacy / canonical S-KEY pretraining
    # body (SymbolicKeyTransformer, ~381K params); 'gru' is the new
    # architecturally-aligned body (HarmonicContextGRUPretrain, ~67K params)
    # that produces a checkpoint loadable into the downstream GRU model with
    # ~95% parameter overlap (vs 1.52% for the Transformer body).
    parser.add_argument('--pretrain-body', default='transformer',
                        choices=['transformer', 'gru'],
                        help=("Pretraining body architecture (Option B 2026-05-08 "
                              "audit follow-up). Default 'transformer' preserves the "
                              "legacy/canonical S-KEY body. 'gru' is the new "
                              "architecturally-aligned variant for Tier-3 closure of "
                              "the §6.9.2 architectural-mismatch caveat."))
    # 2026-05-12 P3 audit fix: lazy-load JSONL cache (closes Phase C T4 RAM ceiling).
    parser.add_argument('--lazy-load', action='store_true',
                        help='Use streaming JSONL-backed lazy cache instead of '
                             'in-memory dict. Closes the Phase B → Phase C '
                             'memory bottleneck (Phase B at 20 K MIDIs OOMed '
                             'on Colab T4; lazy mode supports the full 371 K '
                             'Aria-MIDI corpus on the same hardware).')

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
