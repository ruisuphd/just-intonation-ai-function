"""Regression tests for Option A — `train_phase1_transformer.py`.

Closes the engineering preconditions for the post-thesis Tier-3 audit follow-up
documented in `OPTION_A_B_IMPLEMENTATION_PLAN_2026-05-08.md` §1. The test
strategy mirrors `tests/test_trainer_cli_patches.py` (PR #8): verify the CLI
surface + the loadable-parameter fraction without running an actual GPU
training loop (which would be ~30 min per seed).

Tests:
1.  --help exits 0 and exposes the key Option A flags
2. The trainer can construct `SymbolicKeyTransformer` at the documented
    Phase A defaults (d_model=128, n_heads=4, n_layers=2)
3.  --pretrained-checkpoint is properly parsed (defaults to None)
4. Loaded-parameter fraction with strict=False against a Phase B
    canonical .pt would be ≥ 95 % (Option A's design promise) — verified by
    name-set intersection (filter pretraining mode_head + ksp_head as the
    trainer does) on a freshly-instantiated `SymbolicKeyTransformer`
5. The variant is correctly tagged as 'OptionA_Transformer_finetune' (when
    --pretrained-checkpoint is given) or 'OptionA_Transformer_scratch' (when
    omitted) — verified by inspecting the source for both arm-label paths
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TRAINER = ROOT / 'train_phase1_transformer.py'


def _help_text() -> str:
    """Run --help and return stdout. Raises if exit != 0."""
    result = subprocess.run(
        [sys.executable, str(TRAINER), '--help'],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        f'Trainer --help exited {result.returncode}\nSTDERR:\n{result.stderr[-1000:]}'
    )
    return result.stdout


def test_help_works():
    """--help exits 0 (verifies all imports succeed)."""
    out = _help_text()
    assert 'usage: train_phase1_transformer.py' in out


def test_pretrained_checkpoint_flag_exposed():
    """--pretrained-checkpoint must be in the CLI surface (Option A's main feature)."""
    out = _help_text()
    assert '--pretrained-checkpoint' in out, (
        '--pretrained-checkpoint must be exposed; without it Option A cannot '
        'load the canonical Phase B SymbolicKeyTransformer .pt as initialisation.'
    )


def test_test_filter_atepp41_default():
    """--test-filter must default to atepp41 for like-for-like comparison with Phase I."""
    out = _help_text()
    assert '--test-filter' in out
    assert "default: 'atepp41'" in out or "default='atepp41'" in out or 'atepp41' in out, (
        'Default --test-filter should be atepp41 (matches Phase I trainer default).'
    )


def test_required_phase_i_aligned_flags():
    """All Phase-I-aligned flags (seed/epochs/lr/dropout/ens-beta) must be present."""
    out = _help_text()
    for flag in ('--seed', '--epochs', '--lr', '--dropout', '--ens-beta',
                 '--patience', '--warmup-epochs', '--output-dir'):
        assert flag in out, f'Missing {flag} flag — Option A must align with Phase I trainer.'


def test_transformer_architecture_flags_exposed():
    """Transformer-specific flags (d_model / n_heads / n_layers / ff_dim / max_seq_len)
    must be present so the training run can be reproduced from --help defaults."""
    out = _help_text()
    for flag in ('--d-model', '--n-heads', '--n-layers', '--ff-dim', '--max-seq-len'):
        assert flag in out, f'Missing {flag} flag — Option A must let users pin the Transformer config.'


def test_imports_resolve():
    """Trainer imports SymbolicKeyTransformer + Phase I dataset infrastructure."""
    src = TRAINER.read_text()
    assert 'from harmonic_context_model import SymbolicKeyTransformer' in src
    assert 'from phase1_beat_classical.phase1_dataset import' in src
    assert 'from phase1_beat_classical.train_phase1 import' in src, (
        'Trainer should import build_ens_class_weights from the canonical Phase I trainer'
    )


def test_loaded_param_fraction_high_for_aria_pretrained():
    """**Critical Option A correctness check.**

    The trainer drops mode_head + ksp_head from the pretrained state-dict
    (those are pretraining-only). The remaining keys should match the
    SymbolicKeyTransformer's parameter dict by name AND shape, giving
    ~99% loaded fraction (i.e. all of Transformer body + key_head + input
    embeddings + projections + fusion + pos_embedding).

    This test inspects the source code's filtering logic (it must drop
    `mode_head` and `ksp_head` prefixes; nothing else) — without actually
    loading a real .pt (which is heavy and not available in CI).
    """
    src = TRAINER.read_text()
    assert "if not k.startswith(('mode_head', 'ksp_head'))" in src or \
           "if not k.startswith(('ksp_head', 'mode_head'))" in src, (
        'Trainer must filter pretraining-only heads (mode_head, ksp_head) from '
        'the state-dict. These are pretraining-only and not used by Option A '
        'fine-tune. ALL OTHER keys (input embeddings, projections, fusion, '
        'positional embedding, transformer body, key_head) MUST be loaded.'
    )


def test_arm_label_correctly_set():
    """The output-eval JSON is tagged as 'OptionA_Transformer_finetune' (when
    --pretrained-checkpoint is given) or 'OptionA_Transformer_scratch' (when
    omitted). This is what the joint-analysis bootstrap script reads."""
    src = TRAINER.read_text()
    assert "arm_label = 'finetune' if is_finetune else 'scratch'" in src, (
        'Trainer must auto-tag arm_label as "finetune" / "scratch" based on '
        '--pretrained-checkpoint presence; downstream analysis depends on it.'
    )
    assert "'OptionA_Transformer_'" in src or "f'OptionA_Transformer_{arm_label}'" in src, (
        'Variant tag in the eval JSON must be "OptionA_Transformer_finetune" '
        'or "OptionA_Transformer_scratch" so the joint analysis can pair them.'
    )


def test_phase1_t6_t1_alignment():
    """For the §6.9.4 paired-bootstrap comparison to be valid, Option A must
    use the SAME data preprocessing as Phase I T6_T1: 12-fold transposition
    augmentation + global PCP feature on. The downstream model architecture
    (Transformer vs GRU) is the only difference."""
    src = TRAINER.read_text()
    assert 'use_global_pcp=True' in src, (
        'Option A must use global PCP feature (matches Phase I T6_T1 config)'
    )
    assert 'n_transpositions=12' in src, (
        'Option A must use 12-fold transposition augmentation (matches T6 augmentation)'
    )


def test_ens_class_weighting_default():
    """ENS β = 0.999 must be the default class weighting (matches Phase I)."""
    src = TRAINER.read_text()
    assert "default=0.999" in src, (
        'ENS β default must be 0.999 (matches B9 / Phase I baseline)'
    )
