#!/usr/bin/env python3
"""Phase I training driver — runs B9 + {T6, T1, T2} combinations.

Mirrors the B9 training hyperparameter profile (GRU h=96, ENS β=0.999,
val_mirex selection, 30 epochs, causal) with the Phase I extensions
gated behind CLI flags.

Usage (examples):

    # T6 only (deterministic ×12 transposition; control against B9 baseline)
    python phase1_beat_classical/train_phase1.py --variant T6 --seed 20260412

    # T6 + T1 (+ global PCP feature)
    python phase1_beat_classical/train_phase1.py --variant T6_T1 --seed 20260412

    # T6 + T1 + T2 (full Phase I; + multi-task chord head)
    python phase1_beat_classical/train_phase1.py --variant T6_T1_T2 --seed 20260412
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from harmonic_context_model import KEY_LABELS  # noqa: E402
from evaluate_harmonic_context_model import (  # noqa: E402
    evaluate_per_composition, mirex_weighted_score,
)
from train_harmonic_context_model import (  # noqa: E402
    load_records_from_manifest, set_seed,
)
from phase1_beat_classical.phase1_variants import (  # noqa: E402
    HarmonicContextGRUPhase1,
)
from phase1_beat_classical.phase1_dataset import (  # noqa: E402
    Phase1Dataset, collate_phase1_batch,
)


VARIANTS = {
    'BASELINE':   {'n_transpositions': 1,  'use_global_pcp': False, 'use_chord_heads': False},
    'T6':         {'n_transpositions': 12, 'use_global_pcp': False, 'use_chord_heads': False},
    'T6_T1':      {'n_transpositions': 12, 'use_global_pcp': True,  'use_chord_heads': False},
    'T6_T1_T2':   {'n_transpositions': 12, 'use_global_pcp': True,  'use_chord_heads': True},
    # Also individual cells for clean ablation:
    'T1':         {'n_transpositions': 1,  'use_global_pcp': True,  'use_chord_heads': False},
    'T2':         {'n_transpositions': 1,  'use_global_pcp': False, 'use_chord_heads': True},
}


def build_ens_class_weights(records, beta: float = 0.999) -> torch.Tensor:
    """Reproduce the B9 ENS class-weighting (Cui et al., 2019)."""
    counts = np.zeros(24, dtype=np.float64)
    for rec in records:
        for n in rec.get('notes', []):
            key = n.get('key')
            if key is None:
                continue
            # rely on key_to_index defined in harmonic_context_model
            from harmonic_context_model import key_to_index
            counts[key_to_index(str(key))] += 1
    # Effective number of samples
    eff = 1.0 - np.power(beta, counts)
    eff = np.where(eff == 0, 1.0, eff)
    weights = (1.0 - beta) / eff
    weights = weights * (24.0 / weights.sum())  # normalise to mean 1
    return torch.tensor(weights, dtype=torch.float32)


def compute_frame_mirex(model, loader, device) -> float:
    """Compute frame-weighted MIREX on a dataloader.

    Eval-bottleneck patch (2026-05-02, audit Tier-1 W2 / Su 2026n §7.2):
    the previous implementation looped in Python at each frame calling
    `mirex_weighted_score(p, t)`, which dominated per-epoch wall-clock
    on T4 (~2 h/seed) versus the pre-flight 5-min audit estimate. The
    vectorised path uses the GPU MIREX lookup table from
    `train_harmonic_context_model.masked_mirex` (24×24 LUT cached per
    device); per-frame Python overhead is eliminated and the per-batch
    cost drops to a single tensor index + sum.

    Output (frame-weighted MIREX = total_score_sum / total_count) is
    bit-identical to the previous implementation modulo float-precision
    rounding (verified: max abs Δ < 1e-6 on the BASELINE × 5 reference
    runs).
    """
    from train_harmonic_context_model import masked_mirex  # noqa: E402
    model.eval()
    total_mirex = 0.0
    total = 0
    with torch.no_grad():
        for batch in loader:
            batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                     for k, v in batch.items()}
            out = model(batch)
            logits = out['key_logits']
            labels = batch['labels']
            sum_score, n = masked_mirex(logits, labels)
            total_mirex += sum_score
            total += n
    return total_mirex / max(1, total)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--variant', choices=list(VARIANTS.keys()),
                   default='T6_T1_T2')
    p.add_argument('--manifest', default=str(ROOT / 'research_data'
                                             / 'unified_training_manifest.json'))
    p.add_argument('--label-dirs', default=','.join([
        str(ROOT / 'research_data' / 'score_key_labels'),
        str(ROOT / 'research_data' / 'wir_key_labels'),
        str(ROOT / 'research_data' / 'dcml_key_labels'),
        str(ROOT / 'research_data' / 'dcml_score_key_labels'),  # Block B.3 chord-labelled
    ]))
    p.add_argument('--seed', type=int, default=20260412)
    p.add_argument('--epochs', type=int, default=30)
    p.add_argument('--batch-size', type=int, default=8)
    p.add_argument('--lr', type=float, default=1e-3)
    # 2026-05 architecture-sweep + Aria-MIDI fine-tune CLI flags.
    # Defaults match the B9 hardcoded values used by every Phase I result
    # produced before 2026-05-09; running with all defaults is bit-identical
    # to the pre-patch trainer (verified by tests/test_trainer_cli_patches.py).
    p.add_argument('--hidden-size', type=int, default=96,
                   help=("GRU hidden size for the architecture sweep "
                         "(Tier 2.4; default 96 reproduces the B9 baseline)."))
    p.add_argument('--dropout', type=float, default=0.1,
                   help=("GRU dropout for the regularisation sweep "
                         "(Tier 2.4; default 0.1 reproduces the B9 baseline)."))
    p.add_argument('--ens-beta', type=float, default=0.999,
                   help=("ENS class-weight β (Cui et al., 2019) for the "
                         "class-imbalance sweep (Tier 2.4; default 0.999 "
                         "reproduces the B9 baseline)."))
    p.add_argument('--pretrained-checkpoint', default=None,
                   help=("Path to a .pt checkpoint to use as initial "
                         "weights for the GRU (Phase D Aria-MIDI fine-tune, "
                         "Tier 3.2). The state_dict is loaded with "
                         "strict=False so any module not present in the "
                         "pre-trained checkpoint (e.g. the chord head in "
                         "T2 / T6_T1_T2 variants) remains randomly "
                         "initialised and trainable. Default: no init."))
    p.add_argument('--patience', type=int, default=10)
    p.add_argument('--warmup-epochs', type=int, default=3)
    p.add_argument('--chord-loss-weight', type=float, default=0.3,
                   help='λ for chord-heads loss when T2 is active')
    p.add_argument('--output-dir', default=str(ROOT / 'phase1_beat_classical'
                                                / 'runs'))
    p.add_argument('--device', default='auto')
    p.add_argument('--test-filter', default='atepp41',
                   help=("Which test composition IDs to evaluate on. Options: "
                         "'atepp41' (default — legacy hardcoded 41-piece ATEPP "
                         "allowlist for back-compat with B9 chapter results); "
                         "'none' (use every record the manifest tagged as "
                         "split=test; for cross-corpus runs e.g. POP909, "
                         "BPS-FH, TAVERN); or a path to a JSON file containing "
                         "a top-level list of allowed composition IDs (mixed "
                         "int / string ok)."))
    args = p.parse_args()

    variant_cfg = VARIANTS[args.variant]
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
    print(f'Device: {device}')

    # Load records
    print('Loading records from manifest...')
    # The base loader takes a comma-separated label-dirs string; split if needed
    label_dirs_list = args.label_dirs.split(',') if ',' in args.label_dirs else [args.label_dirs]
    train_records, _, _ = load_records_from_manifest(
        args.manifest, label_dirs_list, 'train', include_synthetic=False,
    )
    val_records, _, _ = load_records_from_manifest(
        args.manifest, label_dirs_list, 'val', include_synthetic=False,
    )
    test_records, _, _ = load_records_from_manifest(
        args.manifest, label_dirs_list, 'test', include_synthetic=False,
    )
    # Test-set filter (Month 2 patch, 2026-05-08):
    # Originally a hardcoded ATEPP-41 allowlist (back-compat with B9 chapter
    # results). The hardcoded form silently dropped every cross-corpus test
    # record (POP909 string IDs failed `int()` and were treated as -1, which
    # broke the Tier-2.1 POP909 sweep). The filter is now CLI-controlled:
    #   --test-filter atepp41  → legacy 41-piece ATEPP allowlist (default)
    #   --test-filter none     → trust the manifest's split=test tagging
    #   --test-filter <path>   → JSON file with a top-level list of IDs
    ATEPP_41 = {7, 60, 77, 120, 122, 215, 515, 541, 546, 547, 550, 602,
                610, 650, 670, 672, 728, 876, 907, 910, 1076, 1128,
                1132, 1144, 1147, 1164, 1190, 1200, 1212, 1215, 1227,
                1240, 1248, 1256, 1257, 1259, 1263, 1495, 1512, 1518, 1542}

    def _cid_str(r):
        """Stringify composition_id (or piece_id fallback) without int-coercion.
        POP909 / BPS-FH use string IDs; ATEPP uses integer IDs."""
        v = r.get('composition_id', r.get('piece_id'))
        return str(v) if v is not None else None

    def _resolve_test_filter(spec):
        """Return (allow_set | None, label) where None means 'no filter'."""
        if spec == 'atepp41':
            return {str(c) for c in ATEPP_41}, 'atepp41 (back-compat)'
        if spec == 'none':
            return None, 'none (trust manifest split=test)'
        from pathlib import Path as _Path
        path = _Path(spec)
        if not path.exists():
            raise SystemExit(
                f'--test-filter: not a recognised mode and file not found: {spec}')
        ids = json.load(open(path))
        if not isinstance(ids, list):
            raise SystemExit(
                f'--test-filter: {path} must contain a JSON list of IDs')
        return {str(x) for x in ids}, f'custom ({path.name}, n={len(ids)})'

    test_filter_set, test_filter_label = _resolve_test_filter(args.test_filter)
    test_records_all = test_records
    if test_filter_set is None:
        # No filter — use every test record the manifest tagged
        pass
    else:
        # Match by stringified composition_id, tolerating ATEPP int↔str.
        test_records = []
        for r in test_records_all:
            cid = _cid_str(r)
            if cid is None:
                continue
            if cid in test_filter_set:
                test_records.append(r)
            else:
                # ATEPP-style: '7' as int may be stored as int in some sources
                try:
                    if str(int(cid)) in test_filter_set:
                        test_records.append(r)
                except (ValueError, TypeError):
                    pass
    print(f'  train: {len(train_records)}, val: {len(val_records)}, '
          f'test: {len(test_records)} (test-filter = {test_filter_label}; '
          f'before filter: {len(test_records_all)})')

    if len(test_records) == 0:
        print(f'  WARN: 0 test records survived the filter. '
              f'If using a cross-corpus manifest (POP909 / BPS-FH / TAVERN), '
              f'pass `--test-filter none` so manifest-tagged test records are '
              f'kept. The eval JSON will report test_mirex_weighted_score=0.0 '
              f'and per_composition=[] — this is a configuration issue, not a '
              f'training failure.')

    # Compute is_modulating flag (needed by Phase1Dataset / composition reweighting)
    for rec_set in (train_records, val_records, test_records):
        for rec in rec_set:
            keys_seen = set()
            for n in rec.get('notes', []):
                k = n.get('key')
                if k is not None:
                    keys_seen.add(str(k))
            rec['is_modulating'] = len(keys_seen) >= 2

    # Datasets
    train_ds = Phase1Dataset(
        train_records, use_global_pcp=variant_cfg['use_global_pcp'],
        use_chord_labels=variant_cfg['use_chord_heads'],
        n_transpositions=variant_cfg['n_transpositions'],
    )
    val_ds = Phase1Dataset(
        val_records, use_global_pcp=variant_cfg['use_global_pcp'],
        use_chord_labels=False,  # val doesn't need chord labels (no chord loss applied)
        n_transpositions=1,
    )
    train_loader = DataLoader(train_ds, batch_size=args.batch_size,
                               shuffle=True, collate_fn=collate_phase1_batch)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size,
                             shuffle=False, collate_fn=collate_phase1_batch)

    print(f'Train dataset: {len(train_ds)} (×{variant_cfg["n_transpositions"]} if T6 active)')
    print(f'Val dataset: {len(val_ds)}')

    # Model
    model = HarmonicContextGRUPhase1(
        hidden_size=args.hidden_size, num_layers=1, dropout=args.dropout,
        use_global_pcp=variant_cfg['use_global_pcp'],
        use_chord_heads=variant_cfg['use_chord_heads'],
    ).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f'Model: HarmonicContextGRUPhase1 variant {args.variant} '
          f'(h={args.hidden_size}, dropout={args.dropout}, '
          f'{n_params:,} parameters)')

    # Phase D Aria-MIDI fine-tune init (Tier 3.2). When --pretrained-checkpoint
    # is supplied, load its state_dict with strict=False so that any module
    # not present in the pre-trained body (e.g. the chord head in T2 /
    # T6_T1_T2 variants, or any module added since the checkpoint was saved)
    # remains randomly initialised and trainable. With --pretrained-checkpoint
    # left at its default of None this block is a no-op and the trainer
    # behaves identically to the pre-2026-05-09 version.
    if args.pretrained_checkpoint:
        ckpt = torch.load(
            args.pretrained_checkpoint, map_location=device, weights_only=False,
        )
        sd = ckpt.get('model_state_dict', ckpt)
        missing, unexpected = model.load_state_dict(sd, strict=False)
        print(f'  ✓ Loaded pretrained checkpoint: {args.pretrained_checkpoint}')
        print(f'    missing keys: {len(missing)}, unexpected: {len(unexpected)}')

    # Loss + optimiser (B9 config; ENS β is now CLI-controlled via --ens-beta,
    # default 0.999 reproduces the original B9 hardcoded value).
    class_weights = build_ens_class_weights(
        train_records, beta=args.ens_beta,
    ).to(device)
    key_loss_fn = nn.CrossEntropyLoss(weight=class_weights, ignore_index=-100)
    chord_loss_fn = nn.CrossEntropyLoss(ignore_index=-100, reduction='none')
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs - args.warmup_epochs,
    )

    # Train
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f'{args.variant}_seed{args.seed}'
    best_val_mirex = -1.0
    best_epoch = -1
    patience_ct = 0
    per_epoch_log = []
    t0 = time.time()
    for epoch in range(1, args.epochs + 1):
        # Warmup LR
        if epoch <= args.warmup_epochs:
            lr_factor = epoch / args.warmup_epochs
            for g in optimizer.param_groups:
                g['lr'] = args.lr * lr_factor
        model.train()
        train_loss_total, train_count = 0.0, 0
        for batch in train_loader:
            batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                     for k, v in batch.items()}
            optimizer.zero_grad()
            out = model(batch)
            logits = out['key_logits']
            loss = key_loss_fn(logits.view(-1, logits.shape[-1]),
                               batch['labels'].view(-1))
            # Chord loss (masked)
            if variant_cfg['use_chord_heads'] and 'chord_root_labels' in batch:
                root_l = out['chord_root_logits']
                qual_l = out['chord_quality_logits']
                mask = batch['chord_mask']
                per_note_root = chord_loss_fn(
                    root_l.reshape(-1, root_l.shape[-1]),
                    batch['chord_root_labels'].reshape(-1),
                )
                per_note_qual = chord_loss_fn(
                    qual_l.reshape(-1, qual_l.shape[-1]),
                    batch['chord_quality_labels'].reshape(-1),
                )
                mask_flat = mask.reshape(-1)
                cr = (per_note_root * mask_flat).sum() / max(mask_flat.sum(), 1)
                cq = (per_note_qual * mask_flat).sum() / max(mask_flat.sum(), 1)
                loss = loss + args.chord_loss_weight * (cr + cq) / 2
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss_total += float(loss.item())
            train_count += 1
        if epoch > args.warmup_epochs:
            scheduler.step()
        val_mirex = compute_frame_mirex(model, val_loader, device)
        wall = time.time() - t0
        print(f'  epoch {epoch:>2}: train_loss={train_loss_total / max(1, train_count):.4f}  '
              f'val_MIREX={val_mirex:.4f}  lr={optimizer.param_groups[0]["lr"]:.1e}  '
              f'({wall:.0f}s)')
        per_epoch_log.append({
            'epoch': epoch, 'train_loss': train_loss_total / max(1, train_count),
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
                'variant_cfg': variant_cfg,
                'epoch': epoch,
            }, out_dir / f'{run_id}.pt')
        else:
            patience_ct += 1
            if patience_ct >= args.patience:
                print(f'  early-stop at epoch {epoch} (no val_mirex improvement for {args.patience} epochs)')
                break

    print(f'\nBest val_MIREX: {best_val_mirex:.4f} at epoch {best_epoch}')
    print(f'Checkpoint: {out_dir / f"{run_id}.pt"}')

    # Final evaluation on the test set with the best checkpoint.
    # NOTE 2026-04-25: bypass evaluate_per_composition because the legacy
    # base-dataset path doesn't pass `global_pcp`/chord tensors through to
    # the Phase I model and crashes with KeyError when use_global_pcp=True.
    # We compute per-piece metrics directly using the Phase1Dataset.
    #
    # Eval-bottleneck patch (2026-05-02, audit W2 / Su 2026n §7.2): the
    # previous per-piece test-eval loop used a Python for-loop calling
    # `_mirex_score_int(p, t)` once per frame. With 41 pieces × thousands
    # of frames per piece, this dominated test-eval wall-clock on T4
    # (≈ 30–60 minutes per seed). The vectorised path below uses the
    # GPU 24×24 MIREX lookup table via `masked_mirex(logits, labels)`,
    # which returns (sum_score, count). Per-piece test-eval drops to a
    # constant per-batch tensor cost. Bit-identical output up to
    # float-precision rounding (verified: max abs Δ < 1e-6 on the
    # BASELINE × 5 reference runs).
    from train_harmonic_context_model import masked_mirex  # noqa: E402
    ckpt = torch.load(str(out_dir / f'{run_id}.pt'), map_location=device, weights_only=False)
    model.load_state_dict(ckpt['model_state_dict'])
    model.eval()

    test_results = []
    with torch.no_grad():
        for rec in test_records:
            comp_id = rec.get('composition_id', rec.get('piece_id', 'unknown'))
            single_ds = Phase1Dataset(
                [rec], use_global_pcp=variant_cfg['use_global_pcp'],
                use_chord_labels=False, n_transpositions=1,
            )
            if len(single_ds) == 0:
                continue
            loader = DataLoader(
                single_ds, batch_size=16, shuffle=False,
                collate_fn=collate_phase1_batch,
            )
            piece_mirex_sum = 0.0
            piece_correct = 0
            piece_n = 0
            for batch in loader:
                batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v
                         for k, v in batch.items()}
                logits = model(batch)['key_logits']
                labels = batch['labels']
                mask = labels != -100
                # Vectorised MIREX via the cached 24×24 LUT.
                sum_score, n = masked_mirex(logits, labels)
                piece_mirex_sum += sum_score
                piece_n += n
                # Accuracy: fully vectorised (no python per-frame loop).
                piece_correct += int(((logits.argmax(-1) == labels) & mask).sum().item())
            if piece_n == 0:
                continue
            test_results.append({
                'composition_id': comp_id,
                'mirex': piece_mirex_sum / piece_n,
                'accuracy': piece_correct / piece_n,
                'n_predictions': piece_n,
            })

    total_mirex = sum(r['mirex'] * r['n_predictions'] for r in test_results)
    total_frames = sum(r['n_predictions'] for r in test_results)
    per_comp = [
        {'composition_id': r['composition_id'], 'mirex': r['mirex'],
         'accuracy': r['accuracy'], 'n_predictions': r['n_predictions']}
        for r in test_results
    ]
    test_mirex_fw = total_mirex / max(1, total_frames)
    eval_out = {
        'variant': args.variant,
        'variant_cfg': variant_cfg,
        'seed': args.seed,
        'best_epoch': best_epoch,
        'best_val_mirex_FW': best_val_mirex,
        'test_mirex_weighted_score': test_mirex_fw,
        'test_total_predictions': total_frames,
        'per_composition': per_comp,
        'per_epoch': per_epoch_log,
        'n_params': n_params,
        'train_records_n': len(train_records),
        'val_records_n': len(val_records),
        'test_records_n': len(test_records),
        'test_filter': args.test_filter,
        'test_filter_label': test_filter_label,
        'test_records_before_filter': len(test_records_all),
        'wall_clock_seconds': time.time() - t0,
    }
    with open(out_dir / f'{run_id}_eval.json', 'w') as f:
        json.dump(eval_out, f, indent=2)
    print(f'Test FW MIREX: {test_mirex_fw:.4f}')
    print(f'Eval JSON:     {out_dir / f"{run_id}_eval.json"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
