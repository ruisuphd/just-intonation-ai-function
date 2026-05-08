#!/usr/bin/env python3
"""Option A trainer — fine-tunes SymbolicKeyTransformer end-to-end on the
unified ATEPP+DCML labelled pool.

Mirrors `phase1_beat_classical/train_phase1.py` but instantiates
`SymbolicKeyTransformer` (Transformer body, ~381K params) instead of
`HarmonicContextGRUPhase1` (GRU body, ~67K params).

This is the Tier-3 audit-closure follow-up to Chapter 6 §6.9.2 — it tests
whether the Transformer pretraining body, when given full end-to-end fine-tune
access (NOT the strict=False 1.52%-partial-transfer channel of §6.9.2),
improves over random initialisation at matched seeds.

Pre-registered decision gate (`OPTION_A_B_IMPLEMENTATION_PLAN_2026-05-08.md`
§1.4):
  🟢 STRONG     Δ_FW ≥ +0.020 AND paired-t p < 0.0125 (Bonferroni α/4 over the 4-hypothesis A+B family)
  🟡 DIRECTIONAL Δ_FW ≥ +0.005 AND paired-t p < 0.05 (uncorrected)
  🔴 NULL        otherwise

Usage (Aria-init):
    python train_phase1_transformer.py \\
        --seed 20260509 \\
        --pretrained-checkpoint research_data/symbolic_key_pretrained_aria_phaseB_canonical.pt \\
        --output-dir phase1_beat_classical/runs_option_a

Usage (matched-seed from-scratch control):
    python train_phase1_transformer.py \\
        --seed 20260509 \\
        --output-dir phase1_beat_classical/runs_option_a_scratch

Loss: cross-entropy on `out['key_logits']` flattened across time, with the
same ENS β = 0.999 class weighting used by the canonical Phase I trainer.

Variant constraint: Option A produces a single Transformer cell — no T6 /
T6_T1 / T6_T1_T2 cumulative ablation (the Transformer doesn't have global-PCP
or chord-head modules). The natural comparator in §6.9.4 is the Phase I T6_T1
cell at the same seeds (FW = 0.6707 ± 0.0103, n = 5).

Author: Rui Su, 2026-05-08. Pre-registered Tier-3 audit follow-up.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
import torch
from torch import nn, optim
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from harmonic_context_model import SymbolicKeyTransformer, KEY_LABELS  # noqa: E402
from train_harmonic_context_model import (  # noqa: E402
    load_records_from_manifest, set_seed, masked_mirex,
)
from phase1_beat_classical.phase1_dataset import (  # noqa: E402
    Phase1Dataset, collate_phase1_batch,
)
from phase1_beat_classical.train_phase1 import (  # noqa: E402
    build_ens_class_weights,
)


# Pre-registered ATEPP-41 test split (matches the Phase I trainer's default
# --test-filter atepp41 behaviour for like-for-like comparison).
ATEPP_41 = {7, 60, 77, 120, 122, 215, 515, 541, 546, 547, 550, 602,
            610, 650, 670, 672, 728, 876, 907, 910, 1076, 1128,
            1132, 1144, 1147, 1164, 1190, 1200, 1212, 1215, 1227,
            1240, 1248, 1256, 1257, 1259, 1263, 1495, 1512, 1518, 1542}


def _cid_str(r):
    """Stringify composition_id (or piece_id fallback)."""
    v = r.get('composition_id', r.get('piece_id'))
    return str(v) if v is not None else None


def _filter_test_atepp41(test_records):
    """Match ATEPP-41 IDs by stringified composition_id (tolerating int↔str)."""
    test_filter_set = {str(c) for c in ATEPP_41}
    out = []
    for r in test_records:
        cid = _cid_str(r)
        if cid is None:
            continue
        if cid in test_filter_set:
            out.append(r)
        else:
            try:
                if str(int(cid)) in test_filter_set:
                    out.append(r)
            except (ValueError, TypeError):
                pass
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--manifest',
                   default=str(ROOT / 'research_data'
                               / 'unified_training_manifest_phase1_clean.json'))
    p.add_argument('--label-dirs', default=','.join([
        str(ROOT / 'research_data' / 'score_key_labels'),
        str(ROOT / 'research_data' / 'wir_key_labels'),
        str(ROOT / 'research_data' / 'dcml_key_labels'),
        str(ROOT / 'research_data' / 'dcml_score_key_labels'),
    ]))
    p.add_argument('--seed', type=int, default=20260509)
    p.add_argument('--epochs', type=int, default=30)
    p.add_argument('--batch-size', type=int, default=8)
    p.add_argument('--lr', type=float, default=1e-3)
    p.add_argument('--patience', type=int, default=10)
    p.add_argument('--warmup-epochs', type=int, default=3)
    p.add_argument('--ens-beta', type=float, default=0.999,
                   help='ENS class-weight β (default 0.999 = Phase I match)')
    p.add_argument('--dropout', type=float, default=0.1,
                   help='Transformer dropout (default 0.1 = Phase I match)')
    p.add_argument('--d-model', type=int, default=128,
                   help='SymbolicKeyTransformer d_model (default 128)')
    p.add_argument('--n-heads', type=int, default=4)
    p.add_argument('--n-layers', type=int, default=2)
    p.add_argument('--ff-dim', type=int, default=256)
    p.add_argument('--max-seq-len', type=int, default=512)
    p.add_argument('--pretrained-checkpoint', default=None,
                   help=('Path to canonical Phase B SymbolicKeyTransformer .pt '
                         '(if omitted, model is initialised from scratch — the '
                         'matched-seed paired control arm).'))
    p.add_argument('--output-dir',
                   default=str(ROOT / 'phase1_beat_classical' / 'runs_option_a'))
    p.add_argument('--device', default='auto')
    p.add_argument('--test-filter', default='atepp41', choices=['atepp41', 'none'])
    args = p.parse_args()

    set_seed(args.seed, deterministic=True)

    # Device
    if args.device == 'auto':
        if torch.cuda.is_available():
            device = 'cuda'
        elif torch.backends.mps.is_available():
            device = 'mps'
        else:
            device = 'cpu'
    else:
        device = args.device
    print(f'Device: {device}, seed={args.seed}, dropout={args.dropout}, '
          f'd_model={args.d_model}')

    # Load records
    print('Loading records from manifest...')
    label_dirs = args.label_dirs.split(',')
    train_records, _, _ = load_records_from_manifest(
        args.manifest, label_dirs, 'train', include_synthetic=False,
    )
    val_records, _, _ = load_records_from_manifest(
        args.manifest, label_dirs, 'val', include_synthetic=False,
    )
    test_records, _, _ = load_records_from_manifest(
        args.manifest, label_dirs, 'test', include_synthetic=False,
    )
    if args.test_filter == 'atepp41':
        test_records = _filter_test_atepp41(test_records)
    print(f'  train: {len(train_records)}, val: {len(val_records)}, '
          f'test: {len(test_records)} (filter={args.test_filter})')

    # is_modulating flag (Phase1Dataset reweighting)
    for rec_set in (train_records, val_records, test_records):
        for rec in rec_set:
            keys = {str(n.get('key')) for n in rec.get('notes', [])
                    if n.get('key') is not None}
            rec['is_modulating'] = len(keys) >= 2

    # Datasets — match the Phase I T6_T1 configuration (12-fold transposition aug,
    # global PCP enabled) for direct apples-to-apples comparison with T6_T1.
    train_ds = Phase1Dataset(
        train_records, use_global_pcp=True, use_chord_labels=False,
        n_transpositions=12,
    )
    val_ds = Phase1Dataset(
        val_records, use_global_pcp=True, use_chord_labels=False,
        n_transpositions=1,
    )
    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        collate_fn=collate_phase1_batch,
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch_size, shuffle=False,
        collate_fn=collate_phase1_batch,
    )
    print(f'Train: {len(train_ds)} (×12 T6 aug), Val: {len(val_ds)}')

    # Model — SymbolicKeyTransformer
    model = SymbolicKeyTransformer(
        d_model=args.d_model,
        n_heads=args.n_heads,
        n_layers=args.n_layers,
        ff_dim=args.ff_dim,
        dropout=args.dropout,
        max_seq_len=args.max_seq_len,
    ).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f'Model: SymbolicKeyTransformer ({n_params:,} parameters)')

    # Pretrained-checkpoint loader (Option A's main feature). Drops pretraining
    # mode/ksp heads (not used in fine-tune); keeps key_head as a warm
    # initialisation point.
    if args.pretrained_checkpoint:
        ckpt = torch.load(
            args.pretrained_checkpoint, map_location=device, weights_only=False,
        )
        sd = ckpt.get('model_state_dict', ckpt)
        sd_filtered = {
            k: v for k, v in sd.items()
            if not k.startswith(('mode_head', 'ksp_head'))
        }
        missing, unexpected = model.load_state_dict(sd_filtered, strict=False)
        # Compute the loaded-parameter fraction (= Option A's transfer strength).
        model_keys = set(dict(model.named_parameters()).keys()) | \
                     set(dict(model.named_buffers()).keys())
        loaded_keys = [k for k in sd_filtered if k in model_keys]
        loaded_param_count = sum(
            sd_filtered[k].numel() for k in loaded_keys
            if hasattr(sd_filtered[k], 'numel')
        )
        print(f'  ✓ Loaded pretrained checkpoint: {args.pretrained_checkpoint}')
        print(f'    Loaded params: {loaded_param_count:,} / {n_params:,} '
              f'({100 * loaded_param_count / n_params:.2f}% of model)')
        print(f'    missing keys: {len(missing)}, unexpected keys: {len(unexpected)}')
    else:
        print('  (no --pretrained-checkpoint; this is the from-scratch control arm)')

    # Loss + optimiser
    class_weights = build_ens_class_weights(
        train_records, beta=args.ens_beta,
    ).to(device)
    key_loss_fn = nn.CrossEntropyLoss(weight=class_weights, ignore_index=-100)
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs - args.warmup_epochs,
    )

    # Train
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    is_finetune = bool(args.pretrained_checkpoint)
    arm_label = 'finetune' if is_finetune else 'scratch'
    run_id = f'transformer_{arm_label}_seed{args.seed}'
    best_val_mirex = -1.0
    best_epoch = -1
    patience_ct = 0
    per_epoch_log = []
    t0 = time.time()

    for epoch in range(1, args.epochs + 1):
        if epoch <= args.warmup_epochs:
            for g in optimizer.param_groups:
                g['lr'] = args.lr * (epoch / args.warmup_epochs)

        model.train()
        epoch_loss, epoch_count = 0.0, 0
        for batch in train_loader:
            batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                     for k, v in batch.items()}
            optimizer.zero_grad()
            out = model(batch)
            logits = out['key_logits']
            # Align labels to the model's sliding-window output length
            # (SymbolicKeyTransformer.forward truncates to the most recent
            # max_seq_len notes when T_in > max_seq_len; the trainer must
            # apply the same truncation to labels before the CE loss).
            T_out = logits.shape[1]
            labels = batch['labels']
            if labels.shape[1] != T_out:
                labels = labels[:, -T_out:]
            loss = key_loss_fn(
                logits.reshape(-1, logits.shape[-1]),
                labels.reshape(-1),
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            epoch_loss += float(loss.item())
            epoch_count += 1
        if epoch > args.warmup_epochs:
            scheduler.step()

        # Val — vectorised MIREX via masked_mirex (24×24 LUT)
        model.eval()
        total_score, total_n = 0.0, 0
        with torch.no_grad():
            for batch in val_loader:
                batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                         for k, v in batch.items()}
                out = model(batch)
                # Same sliding-window alignment as in the train loop
                logits = out['key_logits']
                T_out = logits.shape[1]
                labels = batch['labels']
                if labels.shape[1] != T_out:
                    labels = labels[:, -T_out:]
                ss, n = masked_mirex(logits, labels)
                total_score += ss
                total_n += n
        val_mirex = total_score / max(1, total_n)
        wall = time.time() - t0
        print(f'  epoch {epoch:>2}: train_loss={epoch_loss/max(1,epoch_count):.4f}  '
              f'val_MIREX={val_mirex:.4f}  '
              f'lr={optimizer.param_groups[0]["lr"]:.1e}  ({wall:.0f}s)')
        per_epoch_log.append({
            'epoch': epoch,
            'train_loss': epoch_loss / max(1, epoch_count),
            'val_mirex_weighted_score': val_mirex,
            'learning_rate': optimizer.param_groups[0]['lr'],
        })
        if val_mirex > best_val_mirex:
            best_val_mirex = val_mirex
            best_epoch = epoch
            patience_ct = 0
            torch.save({
                'model_state_dict': model.state_dict(),
                'args': vars(args),
                'epoch': epoch,
                'arm_label': arm_label,
            }, out_dir / f'{run_id}.pt')
        else:
            patience_ct += 1
            if patience_ct >= args.patience:
                print(f'  early-stop at epoch {epoch} '
                      f'(no val_mirex improvement for {args.patience} epochs)')
                break

    print(f'\nBest val_MIREX: {best_val_mirex:.4f} at epoch {best_epoch}')
    print(f'Checkpoint: {out_dir / f"{run_id}.pt"}')

    # Test eval — per-piece, vectorised MIREX
    ckpt = torch.load(
        str(out_dir / f'{run_id}.pt'), map_location=device, weights_only=False,
    )
    model.load_state_dict(ckpt['model_state_dict'])
    model.eval()

    test_results = []
    with torch.no_grad():
        for rec in test_records:
            comp_id = rec.get('composition_id', rec.get('piece_id', 'unknown'))
            single_ds = Phase1Dataset(
                [rec], use_global_pcp=True, use_chord_labels=False,
                n_transpositions=1,
            )
            if len(single_ds) == 0:
                continue
            loader = DataLoader(
                single_ds, batch_size=16, shuffle=False,
                collate_fn=collate_phase1_batch,
            )
            piece_score, piece_correct, piece_n = 0.0, 0, 0
            for batch in loader:
                batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                         for k, v in batch.items()}
                logits = model(batch)['key_logits']
                labels = batch['labels']
                # Same sliding-window alignment as train/val loops
                T_out = logits.shape[1]
                if labels.shape[1] != T_out:
                    labels = labels[:, -T_out:]
                mask = labels != -100
                ss, n = masked_mirex(logits, labels)
                piece_score += ss
                piece_n += n
                piece_correct += int(((logits.argmax(-1) == labels) & mask).sum().item())
            if piece_n == 0:
                continue
            test_results.append({
                'composition_id': comp_id,
                'mirex': piece_score / piece_n,
                'accuracy': piece_correct / piece_n,
                'n_predictions': piece_n,
            })

    total_mirex = sum(r['mirex'] * r['n_predictions'] for r in test_results)
    total_n = sum(r['n_predictions'] for r in test_results)
    fw = total_mirex / max(1, total_n)

    eval_out = {
        'variant': f'OptionA_Transformer_{arm_label}',
        'seed': args.seed,
        'best_epoch': best_epoch,
        'best_val_mirex_FW': best_val_mirex,
        'test_mirex_weighted_score': fw,
        'test_total_predictions': total_n,
        'per_composition': test_results,
        'per_epoch': per_epoch_log,
        'n_params': n_params,
        'pretrained_checkpoint': args.pretrained_checkpoint,
        'arm_label': arm_label,
        'wall_clock_seconds': time.time() - t0,
        'd_model': args.d_model, 'n_heads': args.n_heads,
        'n_layers': args.n_layers, 'ff_dim': args.ff_dim,
        'max_seq_len': args.max_seq_len, 'dropout': args.dropout,
        'ens_beta': args.ens_beta,
    }
    with open(out_dir / f'{run_id}_eval.json', 'w') as f:
        json.dump(eval_out, f, indent=2, default=str)
    print(f'Test FW MIREX: {fw:.4f}')
    print(f'Eval JSON: {out_dir / f"{run_id}_eval.json"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
