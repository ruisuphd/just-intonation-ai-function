#!/usr/bin/env python3
"""Eval-bottleneck patch verification (audit W2 / Su 2026n §7.2).

This test confirms two properties of the 2026-05-02 patch to
`phase1_beat_classical/train_phase1.py`:

  1. **Numerical equivalence.** The vectorised
     `masked_mirex(logits, labels)` path produces FW MIREX values
     bit-identical (up to float-precision rounding) to the previous
     Python per-frame `mirex_weighted_score(p, t)` path. This is the
     evidence that the patch preserves the canonical eval-JSON schema's
     numerical contract — chapter-headline numbers do not move.

  2. **Speedup.** On a representative-size logits tensor (≈ 100k frames
     × 24 classes), the vectorised path is materially faster than the
     Python loop. The exact ratio depends on hardware; we assert
     ≥ 5× as a conservative floor.

Run with:
    pytest tests/test_eval_bottleneck_patch.py -v
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _legacy_mirex_loop(logits, labels):
    """Reproduce the pre-patch Python per-frame loop for comparison."""
    from evaluate_harmonic_context_model import mirex_weighted_score
    preds = logits.argmax(dim=-1)
    mask = labels != -100
    total_mirex = 0.0
    total = 0
    for p, t in zip(preds[mask].cpu().tolist(),
                    labels[mask].cpu().tolist()):
        total_mirex += mirex_weighted_score(p, t)
        total += 1
    return total_mirex, total


def test_vectorised_matches_legacy_python_loop():
    """The vectorised `masked_mirex` path must produce the same FW MIREX
    as the legacy Python per-frame loop, to within 1e-6.
    """
    import torch
    from train_harmonic_context_model import masked_mirex

    torch.manual_seed(20260502)
    n_frames = 5000
    n_classes = 24
    logits = torch.randn(2, n_frames // 2, n_classes)
    labels = torch.randint(0, n_classes, (2, n_frames // 2))
    # Insert some padding (-100) at random positions to exercise mask
    pad_idx = torch.randint(0, n_frames // 2, (200,))
    labels[0, pad_idx] = -100

    # Vectorised
    sum_v, n_v = masked_mirex(logits, labels)
    fw_v = sum_v / max(1, n_v)

    # Legacy
    sum_l, n_l = _legacy_mirex_loop(logits, labels)
    fw_l = sum_l / max(1, n_l)

    assert n_v == n_l, f"count mismatch: vectorised={n_v}, legacy={n_l}"
    assert abs(fw_v - fw_l) < 1e-6, (
        f"FW MIREX differs by more than 1e-6: vectorised={fw_v:.10f}, "
        f"legacy={fw_l:.10f}, Δ={fw_v - fw_l:.3e}"
    )


def test_vectorised_speedup_over_legacy():
    """Confirm the vectorised path is materially faster than the legacy
    Python per-frame loop. We assert ≥ 5× speedup on a representative
    logits tensor (~100k frames × 24 classes), which is the per-piece
    × n-pieces budget seen in test eval.
    """
    import torch
    from train_harmonic_context_model import masked_mirex

    torch.manual_seed(20260502)
    n_frames = 100_000
    n_classes = 24
    logits = torch.randn(1, n_frames, n_classes)
    labels = torch.randint(0, n_classes, (1, n_frames))

    # Warm up the LUT cache (so the first call doesn't pay LUT-build cost).
    _ = masked_mirex(logits, labels)

    t0 = time.perf_counter()
    sum_v, n_v = masked_mirex(logits, labels)
    t_vec = time.perf_counter() - t0

    t0 = time.perf_counter()
    sum_l, n_l = _legacy_mirex_loop(logits, labels)
    t_leg = time.perf_counter() - t0

    speedup = t_leg / max(1e-6, t_vec)
    print(f'\n  vectorised: {t_vec * 1000:.1f} ms')
    print(f'  legacy:     {t_leg * 1000:.1f} ms')
    print(f'  speedup:    {speedup:.1f}×')
    assert speedup >= 5.0, (
        f"vectorised path must be ≥ 5× faster on ~100k frames; got {speedup:.1f}×. "
        f"This may indicate a regression — the canonical 24×24 LUT path should be "
        f"O(N) tensor work, while the Python loop is O(N) interpreter overhead per frame."
    )


def test_eval_json_schema_unchanged():
    """The eval-JSON output schema produced by `phase1_beat_classical/train_phase1.py`
    must be unchanged after the patch. We don't actually run training here; we
    confirm the patched train_phase1.py still emits a per-composition list with
    the four canonical fields {composition_id, mirex, accuracy, n_predictions}
    and the canonical top-level fields by static inspection of the source.
    """
    src = (ROOT / 'phase1_beat_classical' / 'train_phase1.py').read_text()
    # Per-composition fields
    assert "'composition_id': comp_id" in src
    assert "'mirex': piece_mirex_sum / piece_n" in src
    assert "'accuracy': piece_correct / piece_n" in src
    assert "'n_predictions': piece_n" in src
    # Top-level fields
    for field in ('test_mirex_weighted_score', 'best_val_mirex_FW',
                  'per_composition', 'per_epoch', 'wall_clock_seconds',
                  'variant', 'seed'):
        assert f"'{field}'" in src, f"top-level field '{field}' missing from eval JSON output"
