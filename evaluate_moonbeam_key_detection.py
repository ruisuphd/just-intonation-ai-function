#!/usr/bin/env python3
"""
Evaluate a Moonbeam per-note key-detection checkpoint.

Companion to finetune_moonbeam_key_detection.py (Phase C Path A, 2026-04-18).
Writes JSON output in the SAME schema as evaluate_harmonic_context_model.py,
so ensemble_key_detector.py and hmm_postprocessing.py consume Moonbeam
predictions unchanged.

Schema of _predictions.json (identical to the GRU evaluator):
    {
      'checkpoint', 'model_type': 'moonbeam',
      'split': 'test' | 'val',
      'has_softmax': True,
      'compositions': [
        {'composition_id', 'mirex', 'accuracy', 'n_predictions',
         'predictions': [int, ...], 'softmax': [[float]*24, ...]},
        ...
      ]
    }

Usage:
    python evaluate_moonbeam_key_detection.py \\
        --manifest research_data/unified_training_manifest.json \\
        --label-dirs "research_data/wir_key_labels,research_data/dcml_key_labels,research_data/score_key_labels" \\
        --checkpoint research_data/C1_seed20260309.pt \\
        --output    research_data/phase_c_evals/C1_seed20260309_eval.json \\
        --save-predictions     research_data/phase_c_evals/C1_seed20260309_predictions.json \\
        --save-val-predictions research_data/phase_c_evals/C1_seed20260309_val_predictions.json \\
        --bootstrap-n 10000 --device cuda
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

# Moonbeam source path
MOONBEAM_DIR = Path(__file__).parent / "Moonbeam-MIDI-Foundation-Model-main"
sys.path.insert(0, str(MOONBEAM_DIR / "src"))
sys.path.insert(0, str(MOONBEAM_DIR / "src" / "llama_recipes" / "transformers_minimal" / "src"))

from transformers import LlamaConfig, LlamaForCausalLM

# Share helper code with finetune script
from finetune_moonbeam_key_detection import (
    KEY_LABELS, key_to_index, mirex_weighted_score, build_mirex_table,
    notes_to_compound_tokens, MoonbeamPerNoteClassifier,
    load_records_from_manifest,
)


def evaluate_composition(
    model: MoonbeamPerNoteClassifier,
    notes: List[Dict],
    device: torch.device,
    max_seq_len: int,
    window_hop: int,
) -> Dict:
    """Run the model over one composition and return per-note predictions.

    For compositions longer than max_seq_len, windows overlap with hop=window_hop.
    For overlapping positions, we average softmax probabilities (robust to per-
    window prediction noise).

    Returns:
        {
          'composition_id': int,
          'n_notes': int,
          'n_predictions': int (notes with valid labels),
          'mirex': float,
          'accuracy': float,
          'predictions': List[int],       # length = n_notes (0-23 or -1 if no label)
          'softmax':     List[List[float]] # length = n_notes, each length 24
        }
    """
    compounds = notes_to_compound_tokens(notes)
    n_notes = len(compounds)
    if n_notes == 0:
        return {
            'composition_id': -1, 'n_notes': 0, 'n_predictions': 0,
            'mirex': 0.0, 'accuracy': 0.0, 'predictions': [], 'softmax': [],
        }

    # Ground-truth labels per note
    labels_np = np.array([key_to_index(str(n.get('key', ''))) for n in notes], dtype=np.int64)

    # Accumulate softmax across overlapping windows
    accum_softmax = np.zeros((n_notes, 24), dtype=np.float64)
    accum_count   = np.zeros(n_notes, dtype=np.int64)

    # Build window start indices
    if n_notes <= max_seq_len:
        starts = [0]
    else:
        starts = list(range(0, n_notes - max_seq_len + 1, window_hop))
        if (n_notes - max_seq_len) % window_hop != 0:
            starts.append(n_notes - max_seq_len)

    model.eval()
    with torch.no_grad():
        for start in starts:
            end = min(start + max_seq_len, n_notes)
            chunk = compounds[start:end]
            tensor_chunk = torch.tensor(chunk, dtype=torch.long).unsqueeze(0).to(device)  # (1, T, 6)
            attn = torch.ones(tensor_chunk.shape[:2], dtype=torch.bool, device=device)
            logits = model(tensor_chunk, attention_mask=attn)  # (1, T, 24)
            logits = logits.clamp(-50, 50)
            if torch.isnan(logits).any():
                logits = torch.nan_to_num(logits, nan=0.0)
            sm = F.softmax(logits.float(), dim=-1).cpu().numpy()[0]  # (T, 24)
            seq_len = sm.shape[0]
            accum_softmax[start:start + seq_len] += sm
            accum_count[start:start + seq_len] += 1

    # Average softmax per note
    softmax_avg = accum_softmax / np.clip(accum_count[:, None], 1, None)
    preds = softmax_avg.argmax(axis=-1)

    # Compute MIREX over notes with valid labels
    valid = labels_np >= 0
    n_predictions = int(valid.sum())
    if n_predictions == 0:
        mirex = 0.0; accuracy = 0.0
    else:
        correct = int(((preds == labels_np) & valid).sum())
        accuracy = correct / n_predictions
        mirex_total = 0.0
        for p, t in zip(preds[valid], labels_np[valid]):
            mirex_total += mirex_weighted_score(int(p), int(t))
        mirex = mirex_total / n_predictions

    return {
        'n_notes': n_notes,
        'n_predictions': n_predictions,
        'mirex': mirex,
        'accuracy': accuracy,
        'predictions': preds.tolist(),
        'softmax': softmax_avg.tolist(),
    }


def evaluate_all(
    model: MoonbeamPerNoteClassifier,
    records: List[Dict],
    device: torch.device,
    max_seq_len: int,
    window_hop: int,
) -> List[Dict]:
    """Evaluate every composition in `records`. Each record has a 'notes' array
    and a 'piece_id' (or '_piece_id' attached by load_records_from_manifest).
    """
    out = []
    for rec in records:
        piece_id = rec.get('_piece_id', rec.get('piece_id', rec.get('composition_id', -1)))
        try:
            piece_id_int = int(piece_id)
        except (ValueError, TypeError):
            piece_id_int = -1
        notes = rec.get('notes', [])
        if not notes:
            continue
        result = evaluate_composition(model, notes, device, max_seq_len, window_hop)
        result['composition_id'] = piece_id_int
        out.append(result)
    return out


def aggregate_metrics(per_comp_results: List[Dict]) -> Dict[str, float]:
    """Frame-weighted aggregate (canonical) MIREX and accuracy."""
    total_mirex = 0.0
    total_correct = 0
    total_notes = 0
    mirex_table = None
    for r in per_comp_results:
        n = r['n_predictions']
        if n == 0: continue
        total_mirex += r['mirex'] * n
        total_correct += r['accuracy'] * n
        total_notes += n
    if total_notes == 0:
        return {'mirex_weighted_score': 0.0, 'accuracy': 0.0, 'total_predictions': 0}
    return {
        'mirex_weighted_score': total_mirex / total_notes,
        'accuracy':             total_correct / total_notes,
        'total_predictions':    total_notes,
    }


def bootstrap_ci(per_comp_results: List[Dict], n_boot: int = 10000, seed: int = 20260418) -> Dict:
    """Composition-level bootstrap CI on frame-weighted MIREX."""
    if not per_comp_results or n_boot <= 0:
        return {'mirex_mean': 0.0, 'mirex_ci_lower': 0.0, 'mirex_ci_upper': 0.0,
                'mirex_std': 0.0, 'n_bootstrap': 0, 'n_compositions': 0}
    mirex_vec = np.array([r['mirex'] for r in per_comp_results], dtype=np.float64)
    n_vec = np.array([r['n_predictions'] for r in per_comp_results], dtype=np.int64)
    rng = np.random.default_rng(seed)
    n = len(mirex_vec)
    boot = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        w = n_vec[idx]
        m = mirex_vec[idx]
        denom = w.sum()
        boot[i] = (m * w).sum() / max(denom, 1)
    return {
        'mirex_mean':     float(boot.mean()),
        'mirex_ci_lower': float(np.percentile(boot, 2.5)),
        'mirex_ci_upper': float(np.percentile(boot, 97.5)),
        'mirex_std':      float(boot.std()),
        'n_bootstrap':    int(n_boot),
        'n_compositions': int(n),
    }


def load_classifier(checkpoint_path: str, device: torch.device) -> MoonbeamPerNoteClassifier:
    """Load a saved finetune checkpoint with base model + optional LoRA."""
    ckpt = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
    model_size = ckpt.get('model_size', '309M')
    config_path = ckpt.get('config_path',
        str(MOONBEAM_DIR / 'src' / 'llama_recipes' / 'configs' /
            ('model_config_309M.json' if model_size == '309M' else 'model_config.json')))

    llama_cfg = LlamaConfig.from_pretrained(config_path)
    llama_cfg.use_cache = False
    base_model = LlamaForCausalLM(llama_cfg)

    classifier = MoonbeamPerNoteClassifier(base_model, num_classes=24)

    # Re-wrap with LoRA if the checkpoint used LoRA (state_dict key names shifted)
    if ckpt.get('use_lora', True) and not ckpt.get('full_finetune', False):
        from peft import LoraConfig, get_peft_model
        lora_cfg = LoraConfig(
            r=ckpt.get('lora_r', 16), lora_alpha=ckpt.get('lora_alpha', 32),
            lora_dropout=0.05,
            target_modules=["q_proj", "v_proj"], bias="none",
            task_type="FEATURE_EXTRACTION",
        )
        classifier.encoder = get_peft_model(classifier.encoder, lora_cfg)

    state_dict = ckpt['model_state_dict']
    missing, unexpected = classifier.load_state_dict(state_dict, strict=False)
    if missing:
        print(f'  [load] missing keys (first 5): {missing[:5]}')
    if unexpected:
        print(f'  [load] unexpected keys (first 5): {unexpected[:5]}')

    classifier = classifier.to(device)
    classifier.eval()
    return classifier


def parse_args():
    p = argparse.ArgumentParser(description='Evaluate Moonbeam per-note key-detection checkpoint')
    p.add_argument('--manifest', required=True)
    p.add_argument('--label-dirs', required=True)
    p.add_argument('--checkpoint', required=True)
    p.add_argument('--output', required=True, help='Path for aggregate eval JSON')
    p.add_argument('--save-predictions', default=None)
    p.add_argument('--save-val-predictions', default=None)
    p.add_argument('--max-seq-len', type=int, default=512)
    p.add_argument('--window-hop', type=int, default=256)
    p.add_argument('--bootstrap-n', type=int, default=10000)
    p.add_argument('--device', default='auto')
    p.add_argument('--causal-only', action='store_true', default=False,
                   help='Refuse non-causal checkpoints. Moonbeam is always causal so this '
                        'passes unless someone manually flipped the `causal` flag in metadata.')
    return p.parse_args()


def main():
    args = parse_args()
    if args.device == 'auto':
        if torch.cuda.is_available(): device = torch.device('cuda')
        elif torch.backends.mps.is_available(): device = torch.device('mps')
        else: device = torch.device('cpu')
    else:
        device = torch.device(args.device)
    print(f'Device: {device}')

    # Load model
    print(f'Loading checkpoint: {args.checkpoint}')
    classifier = load_classifier(args.checkpoint, device)
    ckpt_meta = torch.load(args.checkpoint, map_location='cpu', weights_only=False)
    if args.causal_only and not ckpt_meta.get('causal', True):
        raise SystemExit(f'[--causal-only] Checkpoint {args.checkpoint} is not flagged causal.')

    # Load data
    label_dirs = [d.strip() for d in args.label_dirs.split(',')]
    test_records = load_records_from_manifest(args.manifest, label_dirs, 'test')
    val_records  = load_records_from_manifest(args.manifest, label_dirs, 'val')
    print(f'Records (note-level): {len(val_records)} val, {len(test_records)} test')

    # Run inference
    print('Evaluating validation set...')
    val_per_comp = evaluate_all(classifier, val_records, device, args.max_seq_len, args.window_hop)
    val_metrics = aggregate_metrics(val_per_comp)

    print('Evaluating test set...')
    test_per_comp = evaluate_all(classifier, test_records, device, args.max_seq_len, args.window_hop)
    test_metrics = aggregate_metrics(test_per_comp)

    print(f'\nValidation: n_comps={len(val_per_comp)}  MIREX={val_metrics["mirex_weighted_score"]:.4f}  accuracy={val_metrics["accuracy"]:.4f}')
    print(f'Test:       n_comps={len(test_per_comp)}  MIREX={test_metrics["mirex_weighted_score"]:.4f}  accuracy={test_metrics["accuracy"]:.4f}')

    # Bootstrap CI on test
    boot = bootstrap_ci(test_per_comp, n_boot=args.bootstrap_n)
    if boot['n_compositions'] > 0:
        print(f'Test bootstrap: mean={boot["mirex_mean"]:.4f}  95% CI [{boot["mirex_ci_lower"]:.4f}, {boot["mirex_ci_upper"]:.4f}]  n={boot["n_compositions"]}')

    # Write main eval JSON (same schema as evaluate_harmonic_context_model.py)
    payload = {
        'checkpoint': args.checkpoint,
        'model_type': 'moonbeam',
        'model_size': ckpt_meta.get('model_size', 'unknown'),
        'hidden_size': ckpt_meta.get('hidden_size'),
        'num_layers':  ckpt_meta.get('num_layers'),
        'use_lora':    ckpt_meta.get('use_lora', True),
        'lora_r':      ckpt_meta.get('lora_r'),
        'lora_alpha':  ckpt_meta.get('lora_alpha'),
        'seed':        ckpt_meta.get('seed'),
        'max_seq_len': args.max_seq_len,
        'window_hop':  args.window_hop,
        'validation':  val_metrics,
        'test':        test_metrics,
        'bootstrap_ci': boot,
        'causality': {
            'bidirectional': False,
            'is_oracle_result': False,
            'causal_only_flag': bool(args.causal_only),
        },
    }
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(payload, f, indent=2)
    print(f'\nSaved eval JSON to {args.output}')

    # Write per-note predictions (same schema as GRU _predictions.json)
    def pred_payload(per_comp, split):
        return {
            'checkpoint': args.checkpoint,
            'model_type': 'moonbeam',
            'split': split,
            'has_softmax': True,
            'compositions': [
                {
                    'composition_id': r['composition_id'],
                    'mirex':          r['mirex'],
                    'accuracy':       r['accuracy'],
                    'n_predictions':  r['n_predictions'],
                    'predictions':    r['predictions'],
                    'softmax':        r['softmax'],
                }
                for r in per_comp
            ],
        }

    if args.save_predictions:
        os.makedirs(os.path.dirname(args.save_predictions) or '.', exist_ok=True)
        with open(args.save_predictions, 'w') as f:
            json.dump(pred_payload(test_per_comp, 'test'), f)
        print(f'Saved test predictions to {args.save_predictions}')

    if args.save_val_predictions:
        os.makedirs(os.path.dirname(args.save_val_predictions) or '.', exist_ok=True)
        with open(args.save_val_predictions, 'w') as f:
            json.dump(pred_payload(val_per_comp, 'val'), f)
        print(f'Saved val predictions to {args.save_val_predictions}')


if __name__ == '__main__':
    main()
