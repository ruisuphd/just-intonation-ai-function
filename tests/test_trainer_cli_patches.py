"""Regression test for trainer CLI patches landed in PR #8.

Validates that `phase1_beat_classical/train_phase1.py` exposes the four
2026-05 architecture-sweep + Aria-MIDI fine-tune CLI flags that were
previously applied as ephemeral Colab patches:

  --hidden-size            (default 96; matches B9 hardcoded value)
  --dropout                (default 0.1; matches B9 hardcoded value)
  --ens-beta               (default 0.999; matches B9 hardcoded value)
  --pretrained-checkpoint  (default None; no-op when omitted)

The defaults are chosen so that running with no extra flags is
bit-identical to the pre-2026-05-09 trainer (i.e. all Phase I cumulative
ablation results published before 2026-05-09 remain reproducible).

Closes the audit's CLAIM 1 ("trainer in zip lacks new CLI flags").
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRAINER = ROOT / "phase1_beat_classical" / "train_phase1.py"


def _help_text() -> str:
    """Run the trainer with --help and return stdout. Raises if exit != 0."""
    result = subprocess.run(
        [sys.executable, str(TRAINER), "--help"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        f"Trainer --help exited {result.returncode}\n"
        f"STDERR:\n{result.stderr[-1000:]}"
    )
    return result.stdout


def test_hidden_size_flag_exposed():
    """--hidden-size must be in the CLI surface (Tier 2.4 sensitivity sweep)."""
    out = _help_text()
    assert "--hidden-size" in out, (
        "Missing --hidden-size flag. The Tier 2.4 sensitivity sweep "
        "(sensitivity_sweep.py) cannot run without this."
    )


def test_dropout_flag_exposed():
    """--dropout must be in the CLI surface (Tier 2.4 sensitivity sweep)."""
    out = _help_text()
    assert "--dropout" in out, (
        "Missing --dropout flag. The Tier 2.4 sensitivity sweep cannot "
        "run without this."
    )


def test_ens_beta_flag_exposed():
    """--ens-beta must be in the CLI surface (Tier 2.4 sensitivity sweep)."""
    out = _help_text()
    assert "--ens-beta" in out, (
        "Missing --ens-beta flag. The Tier 2.4 sensitivity sweep cannot "
        "run without this."
    )


def test_pretrained_checkpoint_flag_exposed():
    """--pretrained-checkpoint must be in the CLI surface (Tier 3.2 Aria fine-tune)."""
    out = _help_text()
    assert "--pretrained-checkpoint" in out, (
        "Missing --pretrained-checkpoint flag. The Tier 3.2 Aria-MIDI "
        "fine-tune (Phase D / Phase E) cannot run without this."
    )


def test_defaults_match_b9_hardcoded():
    """The default values for the new flags must match the B9 hardcoded
    values that were used by every Phase I result before 2026-05-09."""
    src = TRAINER.read_text()
    # These exact substrings together prove the four defaults are unchanged.
    assert "'--hidden-size', type=int, default=96" in src, (
        "Default for --hidden-size must be 96 (the B9 hardcoded value); "
        "changing it would silently break reproducibility of all pre-2026-05-09 results."
    )
    assert "'--dropout', type=float, default=0.1" in src, (
        "Default for --dropout must be 0.1 (the B9 hardcoded value)."
    )
    assert "'--ens-beta', type=float, default=0.999" in src, (
        "Default for --ens-beta must be 0.999 (the B9 hardcoded value)."
    )
    assert "'--pretrained-checkpoint', default=None" in src, (
        "Default for --pretrained-checkpoint must be None (so the loader "
        "is a no-op when omitted)."
    )


def test_old_hardcoded_values_are_removed():
    """The model construction must NOT contain the old hardcoded values
    `hidden_size=96, num_layers=1, dropout=0.1`. If it does, the patched
    CLI args are not actually wired in and the sensitivity sweep is silent
    no-op. This test catches the regression where the patches are added
    to argparse but not propagated to model construction."""
    src = TRAINER.read_text()
    bad = "hidden_size=96, num_layers=1, dropout=0.1"
    assert bad not in src, (
        f"Trainer still contains the pre-patch hardcoded model construction "
        f"'{bad}'. This would silently override the --hidden-size and --dropout "
        f"CLI flags. The fix is to use args.hidden_size and args.dropout."
    )
    # Same for the ENS hardcoded value
    bad_ens = "build_ens_class_weights(train_records, beta=0.999)"
    assert bad_ens not in src, (
        f"Trainer still contains the pre-patch hardcoded ENS construction "
        f"'{bad_ens}'. The fix is to use args.ens_beta."
    )
