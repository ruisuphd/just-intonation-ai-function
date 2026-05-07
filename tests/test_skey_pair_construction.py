"""Regression tests for the 2026-05-12 P3 audit fix: S-KEY pair construction.

Closes audit CLAIM 2: the original `TranspositionPairDataset` sampled two
non-overlapping windows from the same MIDI file and transposed only one of
them (with original-key padding when transposition pushed notes out of
range). The 2026-05-05 read-only audit identified this as a divergence
from the canonical S-KEY pair construction (Kong, Meseguer-Brocal,
Lostanlen, Lagrange, & Hennequin, 2025), which uses two pitch-shifted
views of the SAME audio frame.

These tests verify the corrected `pair_mode='canonical'` (default) AND
preserve the pre-fix `pair_mode='legacy'` for reproducibility.

Tests in this file:
1. Default pair_mode is 'canonical'
2. Canonical mode: A and B come from the SAME source notes (modulo range-filtering)
3. Canonical mode: c = c_B - c_A is consistent with c_A and c_B internal state
4. Canonical mode: c_A != c_B is enforced (Δc = 0 carries no equivariance signal)
5. Canonical mode: no notes leak into the transposed view that weren't transposed
   (i.e., no original-key padding)
6. Canonical mode: out-of-range transpositions trigger rejection and resampling
7. Legacy mode: pre-fix behaviour preserved
8. CLI: --pair-mode and --min-retained-frac flags are exposed
"""
from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pretrain_symbolic_key import (  # noqa: E402
    TranspositionPairDataset,
    transpose_notes,
)


def _make_synthetic_notes(n: int = 300, base_pitch: int = 60) -> list[dict]:
    """Build a synthetic note list around middle C — safe for ±11 transpositions."""
    return [
        {
            'pitch': base_pitch + (i % 12),  # cycle through 12 pitch classes
            'start': i * 0.5,
            'end':   i * 0.5 + 0.5,
            'velocity': 64,
        }
        for i in range(n)
    ]


def _make_edge_notes(n: int = 300) -> list[dict]:
    """Notes near the upper end of the piano — large positive transpositions
    will push some notes out of range, triggering rejection sampling."""
    return [
        {
            'pitch': 100 + (i % 8),  # MIDI 100-107, near PIANO_MAX (108)
            'start': i * 0.5,
            'end':   i * 0.5 + 0.5,
            'velocity': 64,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_default_pair_mode_is_canonical():
    """Default `pair_mode` must be 'canonical' so post-2026-05-12 runs use the fix."""
    cache = {'piece_a': _make_synthetic_notes()}
    ds = TranspositionPairDataset(cache, window_size=64)
    assert ds.pair_mode == 'canonical', (
        f"Default pair_mode is {ds.pair_mode!r}; expected 'canonical' so the "
        f"2026-05-12 P3 audit fix is the default behaviour."
    )


def test_canonical_uses_same_source_notes():
    """In canonical mode, A and B must come from the SAME source window
    (just transposed differently). The critical property: B is NOT a
    different musical segment from A."""
    random.seed(20260512)
    cache = {'piece_a': _make_synthetic_notes(n=300)}
    ds = TranspositionPairDataset(cache, window_size=64, pair_mode='canonical')
    item = ds[0]
    # The number of notes in A and B should match (after range-filter
    # truncation to the shorter of the two), AND the relative pitch
    # structure (intervals between consecutive notes) must be identical
    # because both come from the same source. We check the latter: if A
    # and B are derived from the same source, their interval sequences
    # are the same modulo the constant shift Δc.
    pcs_A = item['A']['pitch_class']
    pcs_B = item['B']['pitch_class']
    assert len(pcs_A) == len(pcs_B), (
        f"A and B should have the same length after truncation; "
        f"got len(A)={len(pcs_A)} and len(B)={len(pcs_B)}"
    )
    # The diff between consecutive pitch-classes is the SAME for A and B
    # (modulo wraparound), since both are linear shifts of the same source.
    if len(pcs_A) > 1:
        diffs_A = [(pcs_A[i+1] - pcs_A[i]) % 12 for i in range(len(pcs_A)-1)]
        diffs_B = [(pcs_B[i+1] - pcs_B[i]) % 12 for i in range(len(pcs_B)-1)]
        assert diffs_A == diffs_B, (
            "Interval structure of A and B should be identical (both are "
            "linear shifts of the same source). Mismatch indicates A and B "
            "come from different segments."
        )


def test_canonical_relative_shift_consistent():
    """The returned `c` must equal c_B − c_A from the internal sampling."""
    random.seed(20260512)
    cache = {'piece_a': _make_synthetic_notes()}
    ds = TranspositionPairDataset(cache, window_size=64, pair_mode='canonical')
    item = ds[0]
    expected_c = item['c_B'] - item['c_A']
    assert item['c'] == expected_c, (
        f"Expected c = c_B - c_A = {item['c_B']} - {item['c_A']} = {expected_c}, "
        f"got c = {item['c']}"
    )


def test_canonical_rejects_zero_shift():
    """c_A != c_B must always hold (Δc = 0 has no equivariance signal).
    Sample 50 items and verify none of them has c_A == c_B."""
    random.seed(20260512)
    cache = {f'p{i}': _make_synthetic_notes(n=200, base_pitch=60+i)
             for i in range(50)}
    ds = TranspositionPairDataset(cache, window_size=64, pair_mode='canonical')
    for i in range(min(50, len(ds))):
        item = ds[i]
        assert item['c_A'] != item['c_B'], (
            f"item[{i}] returned c_A == c_B == {item['c_A']} — Δc = 0 has no "
            f"equivariance signal and must never be sampled."
        )
        assert item['c'] != 0, (
            f"item[{i}] returned c = 0 — should always be ±1 to ±11."
        )


def test_canonical_no_original_key_padding():
    """In canonical mode, no notes should appear in B that aren't a
    transposition of A's source notes. This is the property the legacy mode
    violated by padding with original-key notes when transposition pushed
    notes out of range. We verify by checking that B's pitch classes are
    consistent with shifting A's pitch classes by Δc (modulo any range-
    filtered drops which truncate but don't introduce new content)."""
    random.seed(20260512)
    cache = {'piece_a': _make_synthetic_notes()}
    ds = TranspositionPairDataset(cache, window_size=64, pair_mode='canonical')
    item = ds[0]
    pcs_A = item['A']['pitch_class']
    pcs_B = item['B']['pitch_class']
    delta_c = item['c'] % 12  # mod-12 because pitch_class is mod-12
    # Each B[i] should equal (A[i] + Δc) mod 12 for the FIRST min(len_A, len_B)
    # positions (the truncation is applied to both equally so positions align).
    n_check = min(len(pcs_A), len(pcs_B))
    for i in range(n_check):
        # In canonical mode, the source window is the same; A is transposed
        # by c_A semitones and B by c_B semitones. So B[i] - A[i] = c_B - c_A
        # = Δc (mod 12). If we instead see B[i] taking a value that doesn't
        # match this rule, it's evidence of contamination (e.g., padding).
        expected_B_pc = (pcs_A[i] + delta_c) % 12
        assert pcs_B[i] == expected_B_pc, (
            f"At position {i}: A[{i}]={pcs_A[i]}, B[{i}]={pcs_B[i]}, "
            f"Δc={delta_c}, expected B = (A + Δc) mod 12 = {expected_B_pc}. "
            f"B does not match the canonical-pair-construction rule, "
            f"indicating either a padding bug or A/B coming from different segments."
        )


def test_canonical_rejects_out_of_range_transpositions():
    """When notes are near the piano edge, rejection sampling should pick
    transposition values that keep most notes in range. Verify that for
    edge-case notes, the dataset still produces a valid item (using the
    fallback (c_A, c_B) = (0, 1) if all 5 retries fail)."""
    random.seed(20260512)
    cache = {'piece_edge': _make_edge_notes(n=200)}
    ds = TranspositionPairDataset(cache, window_size=64, pair_mode='canonical',
                                   min_retained_frac=0.9)
    item = ds[0]
    # Should produce a valid item (not raise)
    assert item['c'] != 0, "c must be non-zero even with edge-case notes"
    assert len(item['A']['pitch_class']) > 0
    assert len(item['B']['pitch_class']) > 0


def test_legacy_mode_preserves_old_behaviour():
    """Legacy mode should match the pre-2026-05-12 implementation: two
    non-overlapping windows with original-key padding."""
    random.seed(20260512)
    cache = {'piece_a': _make_synthetic_notes(n=300)}  # >= 2*128 for legacy
    ds = TranspositionPairDataset(cache, window_size=64, pair_mode='legacy')
    item = ds[0]
    assert item['pair_mode'] == 'legacy'
    # Legacy mode returns 'c' (positive in [1,11]), not 'c_A' / 'c_B'
    assert 1 <= item['c'] <= 11, (
        f"Legacy mode should sample c in [1, 11] (positive shift only); got {item['c']}"
    )
    # Legacy mode has NO 'c_A' / 'c_B' keys (those are canonical-only diagnostics)
    assert 'c_A' not in item or item.get('c_A') is None
    assert 'c_B' not in item or item.get('c_B') is None


def test_legacy_mode_requires_2x_window_notes():
    """Legacy mode requires 2 * window_size notes per MIDI (since it samples
    two non-overlapping windows). Canonical needs only window_size."""
    # 100-note pieces qualify for canonical@64, NOT for legacy@64 (needs 128)
    cache = {'short_piece': _make_synthetic_notes(n=100)}
    # Canonical: should accept the 100-note piece
    ds_canon = TranspositionPairDataset(cache, window_size=64, pair_mode='canonical')
    assert len(ds_canon) == 1
    # Legacy: should REJECT the 100-note piece (needs 128)
    with pytest.raises(ValueError, match='No MIDI files'):
        TranspositionPairDataset(cache, window_size=64, pair_mode='legacy')


def test_invalid_pair_mode_raises():
    """An unknown pair_mode must raise ValueError clearly."""
    cache = {'piece_a': _make_synthetic_notes()}
    with pytest.raises(ValueError, match='pair_mode'):
        TranspositionPairDataset(cache, window_size=64, pair_mode='nonsense')


def test_cli_exposes_pair_mode_flag():
    """The --pair-mode and --min-retained-frac flags must be in --help output."""
    out = subprocess.check_output(
        [sys.executable, str(ROOT / 'pretrain_symbolic_key.py'), '--help'],
        text=True, cwd=str(ROOT),
    )
    assert '--pair-mode' in out, (
        '--pair-mode must be exposed as a CLI flag (P3 audit fix). '
        'Without it, the canonical pair construction can\'t be selected from '
        'the wrapper script.'
    )
    assert '--min-retained-frac' in out, (
        '--min-retained-frac must be exposed (P3 audit fix).'
    )
    assert 'canonical' in out and 'legacy' in out, (
        '--pair-mode help text must list both choices: canonical (default, P3-corrected) '
        'and legacy (pre-2026-05-12 reproducibility).'
    )
