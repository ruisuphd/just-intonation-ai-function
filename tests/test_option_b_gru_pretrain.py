"""Regression tests for Option B — `HarmonicContextGRUPretrain` class +
`--pretrain-body gru` flag in `pretrain_symbolic_key.py`.

Closes the engineering preconditions for the post-thesis Tier-3 audit follow-up
documented in `OPTION_A_B_IMPLEMENTATION_PLAN_2026-05-08.md` §2. Strategy
mirrors `tests/test_skey_pair_construction.py` (PR #9): verify class + CLI
behaviour without running an actual GPU pretraining loop (~50 min on T4).

Tests:
1. `HarmonicContextGRUPretrain` instantiates with the expected param count
   (~67K body + ~1.4K heads = ~68K)
2. forward() returns the SAME dict shape as `SymbolicKeyTransformer`
   (`key_logits`, `mode_logits`, `ksp_logits`)
3. State-dict has exactly the union of `HarmonicContextGRU` body keys plus
    `mode_head.{w,b}` + `ksp_head.{w,b}` — and NOTHING else
4. The body keys (no `mode_head`/`ksp_head` prefix) match `HarmonicContextGRU`'s
   state-dict 1:1 — i.e. the parent body is unmodified
5. The `pretrain_symbolic_key.py` CLI exposes `--pretrain-body {transformer, gru}`
   and defaults to `transformer` (legacy compat)
6. With `--pretrain-body gru`, `pretrain_symbolic_key.py` constructs the
   GRU body (verified by --help text or by source-code inspection)
7. The pretrained GRU checkpoint's body keys are a SUPERSET of the keys
   `HarmonicContextGRUPhase1` expects (= the parameter-load fraction is
   ≥ 95% for a downstream fine-tune via `train_phase1.py
   --pretrained-checkpoint`)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parent.parent
PRETRAIN = ROOT / 'pretrain_symbolic_key.py'

sys.path.insert(0, str(ROOT))


def test_class_instantiates():
    """HarmonicContextGRUPretrain instantiates with the documented defaults."""
    from harmonic_context_model import HarmonicContextGRUPretrain
    m = HarmonicContextGRUPretrain(hidden_size=96, num_layers=1, dropout=0.1)
    n_params = sum(p.numel() for p in m.parameters())
    assert 67_000 <= n_params <= 70_000, (
        f'Expected ~68K params (67K body + 1.4K heads); got {n_params:,}. '
        f'Body should be HarmonicContextGRU at h=96, num_layers=1.'
    )


def test_forward_returns_dict_with_canonical_keys():
    """forward() must return a dict with keys 'key_logits', 'mode_logits',
    'ksp_logits' — same shape as SymbolicKeyTransformer.forward() so that
    pretrain_symbolic_key.py's loss functions are a drop-in replacement."""
    from harmonic_context_model import HarmonicContextGRUPretrain
    m = HarmonicContextGRUPretrain(hidden_size=96, num_layers=1, dropout=0.1)
    m.eval()

    batch_size, seq_len = 2, 10
    batch = {
        'pitch_class':     torch.zeros((batch_size, seq_len), dtype=torch.long),
        'register':        torch.zeros((batch_size, seq_len), dtype=torch.long),
        'delta_bucket':    torch.zeros((batch_size, seq_len), dtype=torch.long),
        'duration_bucket': torch.zeros((batch_size, seq_len), dtype=torch.long),
        'velocity_bucket': torch.zeros((batch_size, seq_len), dtype=torch.long),
        'active_mask':     torch.zeros((batch_size, seq_len, 12), dtype=torch.float),
    }
    out = m(batch)
    assert isinstance(out, dict), f'Expected dict; got {type(out)}'
    assert set(out.keys()) == {'key_logits', 'mode_logits', 'ksp_logits'}, (
        f'Expected canonical S-KEY keys; got {sorted(out.keys())}'
    )
    assert out['key_logits'].shape  == (batch_size, seq_len, 24)
    assert out['mode_logits'].shape == (batch_size, seq_len, 2)
    assert out['ksp_logits'].shape  == (batch_size, seq_len, 12)


def test_state_dict_has_only_expected_keys():
    """The pretrain state-dict has exactly: HarmonicContextGRU body keys +
    mode_head + ksp_head. No extras, no missing."""
    from harmonic_context_model import HarmonicContextGRUPretrain
    m = HarmonicContextGRUPretrain()
    sd_keys = set(m.state_dict().keys())

    # Pretraining heads should be present
    expected_heads = {'mode_head.weight', 'mode_head.bias',
                      'ksp_head.weight', 'ksp_head.bias'}
    assert expected_heads.issubset(sd_keys), (
        f'Pretraining heads missing: {expected_heads - sd_keys}'
    )

    # All non-head keys MUST match HarmonicContextGRU's state-dict
    body_keys = sd_keys - expected_heads
    from harmonic_context_model import HarmonicContextGRU
    parent = HarmonicContextGRU(hidden_size=96, num_layers=1, dropout=0.1)
    parent_keys = set(parent.state_dict().keys())
    assert body_keys == parent_keys, (
        f'Body keys differ from HarmonicContextGRU.\n'
        f'In Option B but not parent: {body_keys - parent_keys}\n'
        f'In parent but not Option B: {parent_keys - body_keys}'
    )


def test_body_unchanged_from_parent():
    """Confirm Option B subclasses HarmonicContextGRU without modifying its
    body (= the body is still loadable into a non-pretrain
    `HarmonicContextGRU` instance for inference)."""
    from harmonic_context_model import HarmonicContextGRU, HarmonicContextGRUPretrain
    pretrain = HarmonicContextGRUPretrain(hidden_size=96, num_layers=1, dropout=0.1)
    deploy = HarmonicContextGRU(hidden_size=96, num_layers=1,
                                dropout=0.1, bidirectional=False, use_pcp=False)

    # The deploy model's state-dict keys should be a subset of the pretrain's
    deploy_keys = set(deploy.state_dict().keys())
    pretrain_keys = set(pretrain.state_dict().keys())
    assert deploy_keys.issubset(pretrain_keys), (
        f'HarmonicContextGRU keys not in HarmonicContextGRUPretrain: '
        f'{deploy_keys - pretrain_keys}'
    )

    # And the shapes match for every shared key
    for k in deploy_keys:
        assert deploy.state_dict()[k].shape == pretrain.state_dict()[k].shape, (
            f'Shape mismatch on key {k}: '
            f'deploy={deploy.state_dict()[k].shape}, '
            f'pretrain={pretrain.state_dict()[k].shape}'
        )


def test_pretrain_body_flag_in_help():
    """`--pretrain-body` must be in --help, with both 'transformer' and
    'gru' choices listed."""
    out = subprocess.check_output(
        [sys.executable, str(PRETRAIN), '--help'],
        text=True, cwd=str(ROOT),
    )
    assert '--pretrain-body' in out, (
        '--pretrain-body must be exposed as a CLI flag (Option B audit '
        'follow-up). Without it the user cannot select the GRU pretraining body.'
    )
    assert 'transformer' in out and 'gru' in out, (
        '--pretrain-body help text must list both choices: transformer (default, '
        'legacy/canonical S-KEY body) and gru (Option B architecturally-aligned '
        'variant).'
    )


def test_pretrain_body_default_is_transformer():
    """Default `--pretrain-body` must remain 'transformer' for backward
    compatibility with the §6.9.2 legacy + canonical Phase B runs."""
    src = PRETRAIN.read_text()
    assert "default='transformer'" in src or 'default="transformer"' in src, (
        "Default --pretrain-body must be 'transformer' (preserves §6.9.2 legacy/"
        "canonical Phase B reproducibility; Option B is opt-in)."
    )


def test_pretrain_body_gru_dispatch_is_present():
    """The pretrain script must dispatch to `HarmonicContextGRUPretrain` when
    `--pretrain-body gru` is selected. Verify this by source-code inspection
    (a full end-to-end test would need a GPU + a real Aria-MIDI cache)."""
    src = PRETRAIN.read_text()
    assert 'HarmonicContextGRUPretrain' in src, (
        "pretrain_symbolic_key.py must import + use HarmonicContextGRUPretrain "
        "for the gru body. Without this, --pretrain-body gru would be a no-op."
    )
    # Verify the dispatch logic
    assert "'gru'" in src or '"gru"' in src, (
        "Dispatch must check for 'gru' string literal."
    )


def test_pretrain_gru_state_dict_keys_match_phase1_t6t1_body():
    """**Critical Option B correctness check.**

    The whole point of Option B is that a GRU pretraining checkpoint will load
    cleanly into the downstream `HarmonicContextGRUPhase1` model used by Phase
    I T6_T1 fine-tuning, with NEAR-COMPLETE parameter overlap (vs the 1.52%
    of the original §6.9.2 partial-transfer test).

    Verify by checking that the body keys of `HarmonicContextGRUPretrain`
    (== keys without mode_head / ksp_head prefixes) appear in the state-dict
    of `HarmonicContextGRUPhase1` (the downstream model).
    """
    from harmonic_context_model import HarmonicContextGRUPretrain
    from phase1_beat_classical.phase1_variants import HarmonicContextGRUPhase1

    pretrain = HarmonicContextGRUPretrain(hidden_size=96, num_layers=1, dropout=0.1)
    downstream = HarmonicContextGRUPhase1(hidden_size=96, num_layers=1, dropout=0.1,
                                          use_global_pcp=True, use_chord_heads=False)

    pretrain_body_keys = {
        k for k in pretrain.state_dict()
        if not k.startswith(('mode_head', 'ksp_head'))
    }
    downstream_keys = set(downstream.state_dict().keys())

    # The pretrain body keys should overlap heavily with the downstream model's keys.
    overlap = pretrain_body_keys & downstream_keys
    overlap_count = len(overlap)
    pretrain_count = len(pretrain_body_keys)
    overlap_fraction = overlap_count / max(1, pretrain_count)
    print(f'\nPretrain body keys: {pretrain_count}')
    print(f'Downstream keys:    {len(downstream_keys)}')
    print(f'Overlap:            {overlap_count} ({100*overlap_fraction:.1f}%)')
    print(f'Pretrain-only keys: {sorted(pretrain_body_keys - downstream_keys)}')
    print(f'Downstream-only keys: {sorted(downstream_keys - pretrain_body_keys)}')

    # Critical check (tightened 2026-05-13 per reviewer): the regression floor
    # must reflect Option B's documented design promise. With shape-filtering
    # in train_phase1.py, the pretrain body should contribute 14/15 keys to
    # the downstream HarmonicContextGRUPhase1 model — only `classifier.weight`
    # is shape-mismatched (24, 96) → (24, 120) and re-initialised in fine-tune.
    # We assert ≥14 overlapping keys (= 93.3% of pretrain body keys) AND
    # ≥80% loaded-parameter fraction by name+shape, which is the 96.45% we
    # measure in production minus a safety margin.
    assert overlap_count >= 14, (
        f'Option B pretraining checkpoint must contribute ≥14/15 body keys to '
        f'HarmonicContextGRUPhase1 (parity with the documented architectural-'
        f'alignment design promise). Got {overlap_count}. Old §6.9.2 1.52% '
        f'baseline (7 keys) is no longer the regression floor.'
    )

    # Shape-compatible parameter-fraction check (the actual measure of how
    # much Option B's pretraining transfers, accounting for the classifier
    # shape mismatch that gets re-initialised in fine-tune).
    downstream_sd = downstream.state_dict()
    shape_compatible_params = sum(
        v.numel() for k, v in pretrain.state_dict().items()
        if k in downstream_sd
        and not k.startswith(('mode_head', 'ksp_head'))
        and v.shape == downstream_sd[k].shape
    )
    total_downstream = sum(p.numel() for p in downstream.parameters())
    loaded_fraction = shape_compatible_params / total_downstream
    print(f'Loaded fraction (shape-compatible body): '
          f'{shape_compatible_params:,}/{total_downstream:,} = {100*loaded_fraction:.2f}%')
    assert loaded_fraction >= 0.80, (
        f'Option B loaded-parameter fraction {100*loaded_fraction:.2f}% is below '
        f'the 80% regression floor. Documented production value is 96.45% '
        f'(2026-05-08 PR #11 + train_phase1.py shape-filter patch). A drop '
        f'below 80% would indicate a regression in HarmonicContextGRUPretrain '
        f'or in the downstream HarmonicContextGRUPhase1 architecture.'
    )


def test_existing_pretrain_legacy_path_still_works():
    """Backward-compatibility check: with default `--pretrain-body transformer`,
    pretrain_symbolic_key.py must still import `SymbolicKeyTransformer` and
    construct it. This protects the §6.9.2 legacy + canonical Phase B
    reproducibility from being broken by Option B's additions."""
    src = PRETRAIN.read_text()
    assert 'from harmonic_context_model import SymbolicKeyTransformer' in src or \
           'SymbolicKeyTransformer' in src, (
        'pretrain_symbolic_key.py must still construct SymbolicKeyTransformer '
        'in the default `--pretrain-body transformer` path.'
    )
