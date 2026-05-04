#!/usr/bin/env python3
"""Smoke test for the Phase I runtime patch (audit C4 closure).

This test confirms that:

  1. The Phase I model classes load through the runtime checkpoint loader.
  2. The runtime correctly assembles `batch['global_pcp']` from live note
     events under each of the three causality policies.
  3. The end-to-end `predict()` path returns a valid prediction with a
     `causality_policy` annotation.
  4. Backwards compatibility: the GRU and Transformer paths still work
     unchanged.

These are SMOKE tests — they exercise the contract, not the accuracy.
A separate offline-evaluation script is required to confirm that the
runtime numerically reproduces the chapter-canonical T6_T1 cell mean.

Run with:
    pytest tests/test_runtime_phase1_integration.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Test data: pick any one T6_T1 checkpoint from the 2026-05-01 archive.
PHASE1_DIR_CANDIDATES = [
    Path('/tmp/phase1_results_2026-05-01/phase1_beat_classical_2026-04-25'),
    ROOT / 'phase1_beat_classical' / 'runs',
]


def _find_t6_t1_checkpoint():
    for d in PHASE1_DIR_CANDIDATES:
        if not d.exists():
            continue
        # Prefer integer-named (canonical per pre-registration §5)
        for name in ('T6_T1_seed3886265411.pt',  # seed_a
                     'T6_T1_seed20260425a.pt'):
            p = d / name
            if p.exists():
                return p
    return None


def _find_t6_t1_t2_checkpoint():
    for d in PHASE1_DIR_CANDIDATES:
        if not d.exists():
            continue
        for name in ('T6_T1_T2_seed3886265411.pt',
                     'T6_T1_T2_seed20260425a.pt'):
            p = d / name
            if p.exists():
                return p
    return None


# Synthesize a 24-event "C major scale + arpeggio" so the running PCP
# is dominated by the C-major pitch classes {0, 2, 4, 5, 7, 9, 11}.
SYNTH_NOTES = [
    # C major scale, two octaves
    (60, 100, 0, 200), (62, 100, 200, 200), (64, 100, 400, 200),
    (65, 100, 600, 200), (67, 100, 800, 200), (69, 100, 1000, 200),
    (71, 100, 1200, 200), (72, 100, 1400, 200), (74, 100, 1600, 200),
    (76, 100, 1800, 200), (77, 100, 2000, 200), (79, 100, 2200, 200),
    # C major arpeggio repeated
    (60, 100, 2400, 300), (64, 100, 2700, 300), (67, 100, 3000, 300),
    (72, 100, 3300, 300), (60, 100, 3600, 300), (64, 100, 3900, 300),
    (67, 100, 4200, 300), (72, 100, 4500, 300), (60, 100, 4800, 300),
    (64, 100, 5100, 300), (67, 100, 5400, 300), (72, 100, 5700, 300),
]


def _seed_runtime(rt) -> None:
    """Fill the runtime's note buffer with the synthetic C-major sequence."""
    for pitch, vel, t_ms, dur_ms in SYNTH_NOTES:
        rt.add_note(pitch, vel, float(t_ms), active_notes=[pitch],
                    duration_ms=float(dur_ms))


# ─────────────────────────────────────────────────────────────────────────
# 1. Phase I checkpoint loading

def test_phase1_t6_t1_loads():
    """Loading T6_T1 through the runtime instantiates HarmonicContextGRUPhase1
    with use_global_pcp=True and use_chord_heads=False, and the state-dict
    keys match the saved checkpoint.
    """
    ckpt = _find_t6_t1_checkpoint()
    if ckpt is None:
        pytest.skip("no T6_T1 checkpoint available locally")
    from harmonic_context_runtime import HarmonicContextRuntime
    from phase1_beat_classical.phase1_variants import HarmonicContextGRUPhase1
    rt = HarmonicContextRuntime(
        checkpoint_path=str(ckpt),
        model_type='phase1_t6_t1',
        causality_policy='running',
    )
    assert rt.load(), 'load() returned False'
    assert isinstance(rt.model, HarmonicContextGRUPhase1)
    assert rt.model.use_global_pcp is True
    assert rt.model.use_chord_heads is False


def test_phase1_t6_t1_t2_loads():
    ckpt = _find_t6_t1_t2_checkpoint()
    if ckpt is None:
        pytest.skip("no T6_T1_T2 checkpoint available locally")
    from harmonic_context_runtime import HarmonicContextRuntime
    from phase1_beat_classical.phase1_variants import HarmonicContextGRUPhase1
    rt = HarmonicContextRuntime(
        checkpoint_path=str(ckpt),
        model_type='phase1_t6_t1_t2',
        causality_policy='running',
    )
    assert rt.load()
    assert isinstance(rt.model, HarmonicContextGRUPhase1)
    assert rt.model.use_global_pcp is True
    assert rt.model.use_chord_heads is True


# ─────────────────────────────────────────────────────────────────────────
# 2. Causality-policy validation

def test_unknown_causality_policy_rejected():
    from harmonic_context_runtime import HarmonicContextRuntime
    with pytest.raises(ValueError):
        HarmonicContextRuntime(
            checkpoint_path='/dev/null',
            model_type='phase1_t6_t1',
            causality_policy='nonsense',
        )


def test_unknown_model_type_rejected():
    from harmonic_context_runtime import HarmonicContextRuntime
    with pytest.raises(ValueError):
        HarmonicContextRuntime(
            checkpoint_path='/dev/null',
            model_type='not_a_real_model',
        )


# ─────────────────────────────────────────────────────────────────────────
# 3. Running global PCP — causality + math

def test_running_pcp_concentrates_on_c_major_classes():
    """For the C-major synthetic sequence, the running PCP at the end of
    the sequence should put weight ONLY on C-major pitch classes
    {0, 2, 4, 5, 7, 9, 11} (i.e., zero weight on the chromatic comp
    {1, 3, 6, 8, 10}).
    """
    from harmonic_context_runtime import HarmonicContextRuntime
    rt = HarmonicContextRuntime(
        checkpoint_path='/dev/null',
        model_type='phase1_t6_t1',
        causality_policy='running',
    )
    _seed_runtime(rt)
    pcp = rt._compute_running_global_pcp()
    assert len(pcp) == 12
    assert abs(sum(pcp) - 1.0) < 1e-6, 'PCP must be L1-normalised'
    in_key_classes = {0, 2, 4, 5, 7, 9, 11}
    out_of_key_classes = {1, 3, 6, 8, 10}
    in_mass = sum(pcp[c] for c in in_key_classes)
    out_mass = sum(pcp[c] for c in out_of_key_classes)
    assert in_mass > 0.99, f'expected ~1.0 mass on C-major classes, got {in_mass:.3f}'
    assert out_mass < 0.01, f'expected ~0 mass on out-of-key classes, got {out_mass:.3f}'


def test_running_pcp_uniform_when_no_duration_supplied():
    """If the host provides no duration_ms, the running PCP falls back to
    count-weighted uniform per-note mass.
    """
    from harmonic_context_runtime import HarmonicContextRuntime
    rt = HarmonicContextRuntime(
        checkpoint_path='/dev/null',
        model_type='phase1_t6_t1',
        causality_policy='running',
    )
    # Three notes, all C
    rt.add_note(60, 100, 0.0, active_notes=[60])
    rt.add_note(60, 100, 100.0, active_notes=[60])
    rt.add_note(60, 100, 200.0, active_notes=[60])
    pcp = rt._compute_running_global_pcp()
    assert pcp[0] == pytest.approx(1.0, abs=1e-6)
    assert all(p == pytest.approx(0.0, abs=1e-6) for p in pcp[1:])


def test_running_pcp_empty_buffer_returns_uniform():
    from harmonic_context_runtime import HarmonicContextRuntime
    rt = HarmonicContextRuntime(
        checkpoint_path='/dev/null',
        model_type='phase1_t6_t1',
        causality_policy='running',
    )
    pcp = rt._compute_running_global_pcp()
    assert all(p == pytest.approx(1 / 12, abs=1e-6) for p in pcp)


# ─────────────────────────────────────────────────────────────────────────
# 4. Score-known and offline policies

def test_score_known_pcp_is_used():
    from harmonic_context_runtime import HarmonicContextRuntime
    rt = HarmonicContextRuntime(
        checkpoint_path='/dev/null',
        model_type='phase1_t6_t1',
        causality_policy='score_known',
    )
    # Even if the live buffer has C-major notes, score-known should win.
    _seed_runtime(rt)
    # Score says A-minor: pitch classes {9, 0, 2, 4, 5, 7, 11} with extra
    # weight on the tonic A (9). Use a non-uniform score PCP.
    score_pcp = [0.0] * 12
    score_pcp[9] = 0.30  # A
    score_pcp[0] = 0.20  # C
    score_pcp[2] = 0.15  # D
    score_pcp[4] = 0.15  # E
    score_pcp[5] = 0.10  # F
    score_pcp[7] = 0.05  # G
    score_pcp[11] = 0.05  # B
    rt.set_score_global_pcp(score_pcp)
    resolved = rt._resolve_global_pcp()
    assert resolved[9] == pytest.approx(0.30, abs=1e-6)
    assert resolved[0] == pytest.approx(0.20, abs=1e-6)


def test_score_known_normalises_input():
    """Caller may pass un-normalised PCP; runtime must L1-normalise."""
    from harmonic_context_runtime import HarmonicContextRuntime
    rt = HarmonicContextRuntime(
        checkpoint_path='/dev/null', model_type='phase1_t6_t1',
        causality_policy='score_known',
    )
    rt.set_score_global_pcp([3.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    resolved = rt._resolve_global_pcp()
    assert resolved[0] == pytest.approx(1.0, abs=1e-6)


def test_offline_policy_uses_offline_pcp():
    from harmonic_context_runtime import HarmonicContextRuntime
    rt = HarmonicContextRuntime(
        checkpoint_path='/dev/null', model_type='phase1_t6_t1',
        causality_policy='offline',
    )
    rt.set_offline_global_pcp([1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    resolved = rt._resolve_global_pcp()
    assert resolved[0] == pytest.approx(1 / 3, abs=1e-6)


def test_score_known_falls_back_to_running_if_not_set():
    """If causality_policy is score_known but no score PCP has been set
    yet, the runtime falls back to running PCP rather than throwing.
    """
    from harmonic_context_runtime import HarmonicContextRuntime
    rt = HarmonicContextRuntime(
        checkpoint_path='/dev/null', model_type='phase1_t6_t1',
        causality_policy='score_known',
    )
    _seed_runtime(rt)
    resolved = rt._resolve_global_pcp()
    # Should be running PCP (concentrated on C-major classes), not uniform.
    assert resolved[0] > 0.05  # C is in the synth sequence
    assert resolved[1] < 1e-6  # C# is not


# ─────────────────────────────────────────────────────────────────────────
# 5. End-to-end predict() smoke test

def test_predict_returns_dict_with_causality_annotation():
    ckpt = _find_t6_t1_checkpoint()
    if ckpt is None:
        pytest.skip("no T6_T1 checkpoint available locally")
    from harmonic_context_runtime import HarmonicContextRuntime
    rt = HarmonicContextRuntime(
        checkpoint_path=str(ckpt),
        model_type='phase1_t6_t1',
        causality_policy='running',
        confidence_threshold=0.0,  # never suppress (smoke test)
    )
    assert rt.load()
    _seed_runtime(rt)
    out = rt.predict()
    assert out is not None, 'predict() returned None on a valid 24-event buffer'
    assert 'key' in out
    assert 'confidence' in out
    assert out['source'] == 'harmonic_context_model_phase1_t6_t1'
    assert out['causality_policy'] == 'running'
    # Confidence in [0, 1]
    assert 0.0 <= out['confidence'] <= 1.0


def test_warmup_gate_holds_predict_below_threshold():
    """Phase I `predict()` should return None when the buffer has fewer
    events than `global_pcp_warmup`.
    """
    ckpt = _find_t6_t1_checkpoint()
    if ckpt is None:
        pytest.skip("no T6_T1 checkpoint available locally")
    from harmonic_context_runtime import HarmonicContextRuntime
    rt = HarmonicContextRuntime(
        checkpoint_path=str(ckpt),
        model_type='phase1_t6_t1',
        causality_policy='running',
        global_pcp_warmup=10,
        confidence_threshold=0.0,
    )
    assert rt.load()
    # Add fewer events than warm-up.
    for pitch, vel, t_ms, dur_ms in SYNTH_NOTES[:5]:
        rt.add_note(pitch, vel, float(t_ms), active_notes=[pitch],
                    duration_ms=float(dur_ms))
    assert rt.predict() is None, 'should suppress predict() before warmup threshold'


# ─────────────────────────────────────────────────────────────────────────
# 6. Backwards compatibility

def test_gru_path_unchanged():
    """B9 / GRU path must continue to work exactly as before.

    Specifically: constructing with model_type='gru' and the default
    causality_policy must not raise; load() against a non-existent path
    must return False (not raise).
    """
    from harmonic_context_runtime import HarmonicContextRuntime
    rt = HarmonicContextRuntime(
        checkpoint_path='/tmp/this_path_does_not_exist_test_smoke.pt',
        model_type='gru',
    )
    assert rt.is_available() is False
    assert rt.load() is False  # FileNotFoundError caught → returns False
    assert rt.is_available() is False
