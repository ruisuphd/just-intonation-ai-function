#!/usr/bin/env python3
"""DEPRECATED — use phase1_beat_classical/train_phase1.py instead.

This root-level script is a duplicate / alternate trainer that was
reconstructed 2026-04-25 after a directory cleanup. The 2026-04-30
project audit (`phd_project_audit_report_2026-04-30.md`, finding M3)
identified a bug in this file's `run_evaluation` MIREX aggregation:

    mirex, n = masked_mirex(logits, labels)
    mirex_sum += mirex * n   # WRONG — masked_mirex returns the SUM
    mirex_n += n

`masked_mirex` returns `(sum_score, count)` per its docstring in
`train_harmonic_context_model.py:925`, so the correct aggregation is
`mirex_sum += mirex` (no multiplication by `n`). The bug inflated
the MIREX score by a factor of (mean batch size). This script's
results are therefore **not comparable** to the canonical Phase I
results produced by `phase1_beat_classical/train_phase1.py`.

**The canonical Phase I trainer is `phase1_beat_classical/train_phase1.py`.**
That script is the one driven by `colab_phase1_beat_classical.py` for
the 2026-04-25 → 2026-05-01 sweeps reported in the thesis chapters.

The bug below has been fixed in this file as a documentation
correction (see line 141 onwards), but no Phase I results were
produced from this file post-fix; if you need to reproduce Phase I
numbers, use the canonical script.

──────────────────────────────────────────────────────────────────

Original purpose of this file:

Trains a Phase1Dataset / HarmonicContextGRUPhase1 stack with one of:

  - T0  : B9 baseline (no T1, no T2, single transposition)
  - T1  : + global pitch-class profile feature
  - T2  : + multi-task chord (root + quality) heads
  - T6  : + ×12 deterministic transposition augmentation
  - T6+T1+T2 : full stack (default)

Inherits the deployable B9 hyperparameters: hidden = 96, ENS β = 0.999,
single-layer causal GRU, val-MIREX checkpoint selection, 30 epochs by
default. Uses the Phase I clean manifest by default; pass the leaky one
(unified_training_manifest_phase1.json) explicitly to reproduce the
2026-04-24 contaminated run.

Test set is forcibly restricted to the 41-composition ATEPP manifest
test split — DCML-expert and WiR-expert entries that share a `split:
test` flag are dropped from evaluation here, otherwise the Phase B
back-compat numbers don't replicate.

Reconstructed 2026-04-25 after a directory cleanup removed the original.
Bug fixed + deprecated 2026-05-01.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from train_harmonic_context_model import (  # noqa: E402
    load_records_from_manifest,
    compute_class_weights,
    masked_accuracy,
    masked_mirex,
)
from harmonic_context_model import KEY_LABELS  # noqa: E402
from phase1_beat_classical.phase1_variants import HarmonicContextGRUPhase1  # noqa: E402
from phase1_beat_classical.phase1_dataset import (  # noqa: E402
    Phase1Dataset, collate_phase1_batch,
)


DEFAULT_MANIFEST = ROOT / "research_data" / "unified_training_manifest_phase1_clean.json"
DEFAULT_LABEL_DIRS = [
    ROOT / "research_data" / "score_key_labels",
    ROOT / "research_data" / "wir_key_labels",
    ROOT / "research_data" / "dcml_key_labels",
    ROOT / "research_data" / "dcml_score_key_labels",
]

# Frozen 41-composition ATEPP test split (composition_id integer, formatted as
# zero-padded piece_id string in the score_key_labels filenames).
ATEPP_TEST_IDS = {
    7, 60, 77, 120, 122, 215, 515, 541, 546, 547, 550, 602, 610, 650, 670,
    672, 728, 876, 907, 910, 1076, 1128, 1132, 1144, 1147, 1164, 1190, 1200,
    1212, 1215, 1227, 1240, 1248, 1256, 1257, 1259, 1263, 1495, 1512, 1518,
    1542,
}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--label-dirs", default=",".join(str(p) for p in DEFAULT_LABEL_DIRS))
    ap.add_argument("--variant", default="T6_T1_T2",
                    choices=["T0", "T1", "T2", "T6", "T6_T1", "T6_T2", "T6_T1_T2"])
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--learning-rate", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=20260412)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--checkpoint", default=None,
                    help="path to save best checkpoint (default: phase1_<variant>_<seed>.pt)")
    ap.add_argument("--results", default=None,
                    help="path to save results JSON (default: phase1_<variant>_<seed>_results.json)")
    return ap.parse_args()


def pick_device(arg: str) -> torch.device:
    if arg == "cpu":
        return torch.device("cpu")
    if arg == "cuda":
        return torch.device("cuda")
    if arg == "mps":
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    # NB: for B9-scale (67 k params) MPS is dramatically slower on Apple
    # silicon (≈ 7× CPU); use CPU unless explicitly forced.
    return torch.device("cpu")


def filter_atepp_test(records: List[Dict]) -> List[Dict]:
    """Drop test records whose piece_id is not in ATEPP_TEST_IDS."""
    out = []
    for rec in records:
        piece_id = rec.get("piece_id") or rec.get("composition_id")
        try:
            pid = int(str(piece_id).lstrip("0") or "0")
        except (ValueError, TypeError):
            continue
        if pid in ATEPP_TEST_IDS:
            out.append(rec)
    return out


def variant_flags(variant: str) -> Dict[str, object]:
    return {
        "use_global_pcp": "T1" in variant,
        "use_chord_heads": "T2" in variant,
        "n_transpositions": 12 if "T6" in variant else 1,
    }


def evaluate(model, loader, device) -> Dict[str, float]:
    model.eval()
    correct = total = 0
    mirex_sum = 0.0
    mirex_n = 0
    with torch.no_grad():
        for batch in loader:
            batch = {k: v.to(device) if torch.is_tensor(v) else v for k, v in batch.items()}
            out = model(batch)
            logits = out["key_logits"]
            labels = batch["labels"]
            acc_correct = masked_accuracy(logits, labels)
            mirex_sum_batch, n = masked_mirex(logits, labels)
            n_valid = (labels != -100).sum().item()
            correct += acc_correct * n_valid
            total += n_valid
            # Bug fix 2026-05-01 (audit M3): masked_mirex returns (sum_score, count),
            # not (mean_score, count). Previously this line was
            #     mirex_sum += mirex * n
            # which double-multiplied by the batch count and inflated the result.
            # The correct aggregation is the running sum of per-batch sums
            # divided by the running count of valid positions.
            mirex_sum += mirex_sum_batch
            mirex_n += n
    acc = correct / max(total, 1)
    mirex = mirex_sum / max(mirex_n, 1)
    return {"accuracy": float(acc), "mirex": float(mirex)}


def main() -> int:
    args = parse_args()

    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)

    label_dirs = [d for d in args.label_dirs.split(",") if d]
    print(f"Manifest: {args.manifest}")
    print(f"Label dirs: {label_dirs}")
    print(f"Variant: {args.variant}")

    train_records, train_class_counts, _ = load_records_from_manifest(
        args.manifest, label_dirs, "train", include_synthetic=False,
    )
    val_records, _, _ = load_records_from_manifest(
        args.manifest, label_dirs, "val", include_synthetic=False,
    )
    test_records, _, _ = load_records_from_manifest(
        args.manifest, label_dirs, "test", include_synthetic=False,
    )
    test_records = filter_atepp_test(test_records)
    print(f"Loaded train={len(train_records)} val={len(val_records)} test={len(test_records)} (ATEPP-41)")

    flags = variant_flags(args.variant)
    train_ds = Phase1Dataset(train_records, **flags)
    flags_eval = dict(flags); flags_eval["n_transpositions"] = 1  # eval no-aug
    val_ds = Phase1Dataset(val_records, **flags_eval)
    test_ds = Phase1Dataset(test_records, **flags_eval)
    print(f"Dataset items: train={len(train_ds)} val={len(val_ds)} test={len(test_ds)}")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              collate_fn=collate_phase1_batch, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                            collate_fn=collate_phase1_batch, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False,
                             collate_fn=collate_phase1_batch, num_workers=0)

    device = pick_device(args.device)
    print(f"Device: {device}")

    weights, _ = compute_class_weights(train_records, mode="ens", ens_beta=0.999)
    weight_tensor = torch.tensor(
        [weights.get(i, 1.0) for i in range(24)],
        dtype=torch.float32, device=device,
    )

    model = HarmonicContextGRUPhase1(
        hidden_size=96,
        use_global_pcp=flags["use_global_pcp"],
        use_chord_heads=flags["use_chord_heads"],
    ).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Model params: {n_params:,}")

    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    ce = nn.CrossEntropyLoss(weight=weight_tensor, ignore_index=-100)
    chord_root_loss = nn.CrossEntropyLoss(ignore_index=-100)
    chord_qual_loss = nn.CrossEntropyLoss(ignore_index=-100)

    ckpt_path = args.checkpoint or f"phase1_{args.variant}_seed{args.seed}.pt"
    results_path = args.results or f"phase1_{args.variant}_seed{args.seed}_results.json"

    best_val_mirex = -1.0
    best_epoch = -1
    history = []

    for epoch in range(1, args.epochs + 1):
        model.train()
        t0 = time.time()
        epoch_loss = 0.0
        for batch in train_loader:
            batch = {k: v.to(device) if torch.is_tensor(v) else v for k, v in batch.items()}
            out = model(batch)
            logits = out["key_logits"]
            labels = batch["labels"]
            loss = ce(logits.reshape(-1, logits.shape[-1]), labels.reshape(-1))
            if flags["use_chord_heads"] and "chord_root_logits" in out:
                root_logits = out["chord_root_logits"]
                qual_logits = out["chord_quality_logits"]
                root_lab = batch["chord_root_labels"]
                qual_lab = batch["chord_quality_labels"]
                loss_root = chord_root_loss(root_logits.reshape(-1, root_logits.shape[-1]),
                                            root_lab.reshape(-1))
                loss_qual = chord_qual_loss(qual_logits.reshape(-1, qual_logits.shape[-1]),
                                            qual_lab.reshape(-1))
                loss = loss + 0.5 * loss_root + 0.5 * loss_qual
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            epoch_loss += float(loss.item())
        val_metrics = evaluate(model, val_loader, device)
        elapsed = time.time() - t0
        print(f"Epoch {epoch:02d} | loss={epoch_loss/max(len(train_loader),1):.4f} "
              f"| val acc={val_metrics['accuracy']:.4f} mirex={val_metrics['mirex']:.4f} "
              f"| {elapsed:.0f}s")
        history.append({
            "epoch": epoch, "train_loss": epoch_loss / max(len(train_loader), 1),
            "val_accuracy": val_metrics["accuracy"], "val_mirex": val_metrics["mirex"],
            "elapsed_s": elapsed,
        })
        if val_metrics["mirex"] > best_val_mirex:
            best_val_mirex = val_metrics["mirex"]
            best_epoch = epoch
            torch.save({
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "val_mirex": val_metrics["mirex"],
                "variant": args.variant,
                "seed": args.seed,
                "flags": flags,
            }, ckpt_path)

    print(f"\nBest epoch: {best_epoch} (val mirex {best_val_mirex:.4f})")

    # Load best checkpoint and evaluate on test
    state = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(state["model_state_dict"])
    test_metrics = evaluate(model, test_loader, device)
    print(f"Test (ATEPP-41) | acc={test_metrics['accuracy']:.4f} mirex={test_metrics['mirex']:.4f}")

    results = {
        "variant": args.variant, "seed": args.seed,
        "manifest": args.manifest,
        "best_epoch": best_epoch, "best_val_mirex": best_val_mirex,
        "test_accuracy": test_metrics["accuracy"],
        "test_mirex": test_metrics["mirex"],
        "history": history, "flags": flags,
    }
    with open(results_path, "w") as fh:
        json.dump(results, fh, indent=2)
    print(f"Wrote {results_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
