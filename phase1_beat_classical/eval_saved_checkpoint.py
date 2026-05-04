#!/usr/bin/env python3
"""Evaluate a saved Phase I checkpoint on the ATEPP-41 test set.

Used to recover test MIREX when train_phase1.py's end-of-training
evaluation pass didn't run (e.g. crashed after saving the checkpoint).

Usage:
    python phase1_beat_classical/eval_saved_checkpoint.py \
        --checkpoint phase1_beat_classical/runs/T6_T1_T2_seed20260412.pt \
        --manifest research_data/unified_training_manifest_phase1_clean.json \
        --output phase1_beat_classical/runs/T6_T1_T2_seed20260412_eval.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluate_harmonic_context_model import mirex_weighted_score  # noqa: E402
from train_harmonic_context_model import load_records_from_manifest  # noqa: E402
from phase1_beat_classical.phase1_variants import (  # noqa: E402
    HarmonicContextGRUPhase1,
)
from phase1_beat_classical.phase1_dataset import (  # noqa: E402
    Phase1Dataset, collate_phase1_batch,
)

ATEPP_TEST_IDS = {7, 60, 77, 120, 122, 215, 515, 541, 546, 547, 550, 602,
                  610, 650, 670, 672, 728, 876, 907, 910, 1076, 1128,
                  1132, 1144, 1147, 1164, 1190, 1200, 1212, 1215, 1227,
                  1240, 1248, 1256, 1257, 1259, 1263, 1495, 1512, 1518, 1542}


def _cid(r):
    try:
        return int(r.get('composition_id', r.get('piece_id', -1)))
    except (ValueError, TypeError):
        return -1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--checkpoint', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--label-dirs', default=','.join([
        str(ROOT / 'research_data' / 'score_key_labels'),
        str(ROOT / 'research_data' / 'wir_key_labels'),
        str(ROOT / 'research_data' / 'dcml_key_labels'),
        str(ROOT / 'research_data' / 'dcml_score_key_labels'),
    ]))
    p.add_argument('--device', default='cpu')
    args = p.parse_args()

    ckpt = torch.load(args.checkpoint, map_location=args.device, weights_only=False)
    variant_cfg = ckpt['variant_cfg']
    print(f'Checkpoint: {args.checkpoint}')
    print(f'  Variant: {ckpt["args"]["variant"]}, seed {ckpt["args"]["seed"]}')
    print(f'  Best epoch: {ckpt["epoch"]}')
    print(f'  Config: {variant_cfg}')

    # Load test records (ATEPP-41 only)
    label_dirs = args.label_dirs.split(',')
    test_all, _, _ = load_records_from_manifest(args.manifest, label_dirs,
                                                  'test', include_synthetic=False)
    test_records = [r for r in test_all if _cid(r) in ATEPP_TEST_IDS]
    print(f'Test records: {len(test_records)} (filtered from {len(test_all)} to ATEPP-41)')

    # Build dataset with matching variant config
    ds = Phase1Dataset(
        test_records,
        use_global_pcp=variant_cfg['use_global_pcp'],
        use_chord_labels=False,  # test doesn't need chord labels
        n_transpositions=1,
    )
    loader = DataLoader(ds, batch_size=1, shuffle=False, collate_fn=collate_phase1_batch)

    # Build model
    model = HarmonicContextGRUPhase1(
        hidden_size=96,
        use_global_pcp=variant_cfg['use_global_pcp'],
        use_chord_heads=variant_cfg['use_chord_heads'],
    ).to(args.device)
    model.load_state_dict(ckpt['model_state_dict'])
    model.eval()

    # Evaluate per-composition
    per_comp = []
    total_mirex = 0.0
    total_frames = 0
    total_correct = 0
    with torch.no_grad():
        for i, batch in enumerate(loader):
            batch = {k: v.to(args.device) if isinstance(v, torch.Tensor) else v
                     for k, v in batch.items()}
            out = model(batch)
            logits = out['key_logits']
            labels = batch['labels']
            preds = logits.argmax(dim=-1)
            mask = labels != -100
            correct = 0
            piece_mirex = 0.0
            n = 0
            for p_, t_ in zip(preds[mask].cpu().tolist(),
                              labels[mask].cpu().tolist()):
                piece_mirex += mirex_weighted_score(p_, t_)
                if p_ == t_:
                    correct += 1
                n += 1
            cid = _cid(test_records[i])
            per_comp.append({
                'composition_id': cid,
                'mirex': piece_mirex / max(1, n),
                'accuracy': correct / max(1, n),
                'n_predictions': n,
            })
            total_mirex += piece_mirex
            total_frames += n
            total_correct += correct

    test_fw = total_mirex / max(1, total_frames)
    test_acc = total_correct / max(1, total_frames)
    test_ce = float(np.mean([r['mirex'] for r in per_comp]))
    print()
    print(f'Test FW MIREX: {test_fw:.4f}')
    print(f'Test CE MIREX: {test_ce:.4f}')
    print(f'Test accuracy: {test_acc:.4f}')
    print(f'Total frames:  {total_frames:,}')

    eval_out = {
        'checkpoint': args.checkpoint,
        'manifest': args.manifest,
        'variant': ckpt['args']['variant'],
        'variant_cfg': variant_cfg,
        'seed': ckpt['args']['seed'],
        'best_epoch': ckpt['epoch'],
        'test_mirex_weighted_score': test_fw,
        'test_mirex_CE': test_ce,
        'test_accuracy': test_acc,
        'test_total_predictions': total_frames,
        'per_composition': per_comp,
        'n_test_compositions': len(per_comp),
    }
    with open(args.output, 'w') as f:
        json.dump(eval_out, f, indent=2)
    print(f'Eval JSON: {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
