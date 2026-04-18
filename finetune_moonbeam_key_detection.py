#!/usr/bin/env python3
"""
Fine-tune Moonbeam MIDI Foundation Model for PER-NOTE 24-key detection.

Phase C Path A rewrite (2026-04-18): replaces the original window-level
majority-vote classifier with a per-token head so outputs are directly
comparable to Phase B's GRU baseline B9. Pairs cleanly with
evaluate_moonbeam_key_detection.py which writes predictions in the same
JSON schema as evaluate_harmonic_context_model.py — so ensemble_key_detector.py
and hmm_postprocessing.py consume Moonbeam predictions unchanged.

Key design:
  - compound tokens (B, T, 6) where T = notes (1 note = 1 token)
  - Moonbeam encoder → (B, T, 1920) hidden states
  - Per-token linear head → (B, T, 24) logits
  - Per-note cross-entropy with -100 ignore_index for padding

Usage (Phase C Path A cell C1, Moonbeam 309M LoRA):
    python finetune_moonbeam_key_detection.py \\
        --manifest research_data/unified_training_manifest.json \\
        --label-dirs "research_data/wir_key_labels,research_data/dcml_key_labels,research_data/score_key_labels" \\
        --model-size 309M \\
        --checkpoint research_data/C1_seed20260309.pt \\
        --use-lora --lora-r 16 --lora-alpha 32 \\
        --epochs 10 --batch-size 2 --grad-accum-steps 4 --lr 1e-4 \\
        --max-seq-len 512 --selection-metric val_mirex \\
        --seed 20260309 --device cuda
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

# Add Moonbeam source to Python path
MOONBEAM_DIR = Path(__file__).parent / "Moonbeam-MIDI-Foundation-Model-main"
sys.path.insert(0, str(MOONBEAM_DIR / "src"))
sys.path.insert(0, str(MOONBEAM_DIR / "src" / "llama_recipes" / "transformers_minimal" / "src"))

from transformers import LlamaConfig, LlamaForCausalLM

# Key labels (same as harmonic_context_model.py)
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
KEY_LABELS = NOTE_NAMES + [f'{name}m' for name in NOTE_NAMES]

CANONICAL_KEY_MAP = {
    'Cb': 'B', 'Db': 'C#', 'Eb': 'D#', 'Fb': 'E', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#',
    'Bbm': 'A#m', 'Cbm': 'Bm', 'Dbm': 'C#m', 'Ebm': 'D#m',
    'Fbm': 'Em', 'Gbm': 'F#m', 'Abm': 'G#m',
}

# MIREX lookup table — mirrors evaluate_harmonic_context_model.py:74-104
# 0..11 = major C..B, 12..23 = minor Cm..Bm
_MIREX_TABLE: Optional[torch.Tensor] = None


def key_to_index(key_str: str) -> int:
    key_str = CANONICAL_KEY_MAP.get(key_str, key_str)
    return KEY_LABELS.index(key_str) if key_str in KEY_LABELS else -1


def mirex_weighted_score(pred_idx: int, true_idx: int) -> float:
    """MIREX-weighted similarity: exact=1, fifth=0.5, relative=0.3, parallel=0.2."""
    if pred_idx < 0 or true_idx < 0:
        return 0.0
    if pred_idx == true_idx:
        return 1.0
    pred_mode = 1 if pred_idx >= 12 else 0
    true_mode = 1 if true_idx >= 12 else 0
    pred_pc = pred_idx % 12
    true_pc = true_idx % 12
    diff = (pred_pc - true_pc) % 12
    # Fifth: same mode, diff in {5, 7}
    if pred_mode == true_mode and diff in (5, 7):
        return 0.5
    # Relative: differing mode, Major pred 3 semitones above Minor true
    if pred_mode != true_mode:
        if pred_mode == 0 and diff == 3:
            return 0.3   # relative major of a minor
        if pred_mode == 1 and diff == 9:
            return 0.3   # relative minor of a major
    # Parallel: same root, different mode
    if pred_mode != true_mode and pred_pc == true_pc:
        return 0.2
    return 0.0


def build_mirex_table(device: torch.device) -> torch.Tensor:
    """Precompute 24×24 MIREX score table (symmetric by construction)."""
    global _MIREX_TABLE
    if _MIREX_TABLE is not None and _MIREX_TABLE.device == device:
        return _MIREX_TABLE
    table = torch.zeros((24, 24), dtype=torch.float32)
    for p in range(24):
        for t in range(24):
            table[p, t] = mirex_weighted_score(p, t)
    _MIREX_TABLE = table.to(device)
    return _MIREX_TABLE


def notes_to_compound_tokens(
    notes: List[Dict],
    time_resolution: int = 100,
) -> np.ndarray:
    """Convert note-level label data to Moonbeam compound tokens.

    Each note becomes a 6-element compound: [timeshift, duration, octave, pitch_class, instrument, velocity].
    One compound token per note — aligns 1:1 with per-note key labels downstream.
    """
    if not notes:
        return np.zeros((0, 6), dtype=np.int64)

    compounds = []
    prev_onset_ticks = 0

    for note in notes:
        pitch = note.get('midi_pitch', note.get('pitch', 60))
        onset_beat = note.get('onset_beat', 0.0)
        duration_beat = note.get('duration_beat', 0.25)

        onset_ticks = int(onset_beat * time_resolution)
        duration_ticks = max(1, int(duration_beat * time_resolution))
        timeshift = max(0, onset_ticks - prev_onset_ticks)

        octave = pitch // 12
        pitch_class = pitch % 12
        instrument = 0
        velocity = note.get('velocity', 80)

        # Clamp to vocab ranges (matches Moonbeam pretraining)
        timeshift = min(timeshift, 4096)
        duration_ticks = min(duration_ticks, 4096)
        octave = min(max(octave, 0), 10)
        velocity = min(max(velocity, 0), 127)

        compounds.append([timeshift, duration_ticks, octave, pitch_class, instrument, velocity])
        prev_onset_ticks = onset_ticks

    return np.array(compounds, dtype=np.int64)


class MoonbeamKeyDataset(Dataset):
    """Per-note key-classification dataset for Moonbeam.

    Unlike the original v1 dataset (which stored ONE majority-vote label per window),
    this stores PER-NOTE labels so the classifier can output per-token predictions.
    """

    def __init__(
        self,
        records: List[Dict],
        max_seq_len: int = 512,
        window_hop: int = 256,
    ):
        self.windows = []
        for rec in records:
            notes = rec.get('notes', [])
            if len(notes) < 8:
                continue
            key_labels = []
            for n in notes:
                idx = key_to_index(str(n.get('key', '')))
                key_labels.append(idx if idx >= 0 else -100)
            compounds = notes_to_compound_tokens(notes)
            n_notes = len(compounds)
            if n_notes <= max_seq_len:
                self.windows.append({
                    'compounds': compounds,
                    'labels': key_labels,
                    'piece_id': rec.get('piece_id', rec.get('composition_id', -1)),
                    'window_start': 0,
                })
                continue
            for start in range(0, n_notes - max_seq_len + 1, window_hop):
                end = start + max_seq_len
                self.windows.append({
                    'compounds': compounds[start:end],
                    'labels': key_labels[start:end],
                    'piece_id': rec.get('piece_id', rec.get('composition_id', -1)),
                    'window_start': start,
                })
            # Tail window to catch residual notes
            if (n_notes - max_seq_len) % window_hop != 0:
                tail_start = n_notes - max_seq_len
                self.windows.append({
                    'compounds': compounds[tail_start:],
                    'labels': key_labels[tail_start:],
                    'piece_id': rec.get('piece_id', rec.get('composition_id', -1)),
                    'window_start': tail_start,
                })

    def __len__(self) -> int:
        return len(self.windows)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        w = self.windows[idx]
        return {
            'compounds': torch.tensor(w['compounds'], dtype=torch.long),
            'labels': torch.tensor(w['labels'], dtype=torch.long),
            'piece_id': w['piece_id'],
            'window_start': w['window_start'],
        }


def collate_moonbeam_per_note(batch: List[Dict]) -> Dict[str, torch.Tensor]:
    """Collate for per-note output: pad compounds with 0, labels with -100."""
    max_len = max(b['compounds'].shape[0] for b in batch)
    padded_compounds, padded_labels, masks, piece_ids, window_starts = [], [], [], [], []
    for b in batch:
        seq_len = b['compounds'].shape[0]
        pad = max_len - seq_len
        if pad > 0:
            pc = F.pad(b['compounds'], (0, 0, 0, pad), value=0)
            pl = F.pad(b['labels'], (0, pad), value=-100)
        else:
            pc = b['compounds']
            pl = b['labels']
        m = torch.ones(max_len, dtype=torch.bool)
        m[seq_len:] = False
        padded_compounds.append(pc)
        padded_labels.append(pl)
        masks.append(m)
        piece_ids.append(int(b['piece_id']))
        window_starts.append(int(b['window_start']))
    return {
        'compounds': torch.stack(padded_compounds),
        'labels':    torch.stack(padded_labels),
        'attention_mask': torch.stack(masks),
        'piece_ids':      torch.tensor(piece_ids, dtype=torch.long),
        'window_starts':  torch.tensor(window_starts, dtype=torch.long),
    }


class MoonbeamPerNoteClassifier(nn.Module):
    """Moonbeam encoder + per-token 24-way classification head.

    v2 (2026-04-18): removed mean-pool — apply the LayerNorm + Linear head to every
    token position, producing (B, T, 24) logits.
    """

    def __init__(self, moonbeam_model: LlamaForCausalLM, num_classes: int = 24):
        super().__init__()
        self.encoder = moonbeam_model.model
        self.hidden_size = moonbeam_model.config.hidden_size
        self.classifier = nn.Sequential(
            nn.LayerNorm(self.hidden_size),
            nn.Dropout(0.1),
            nn.Linear(self.hidden_size, num_classes),
        )

    def forward(self, input_ids, attention_mask=None):
        # Moonbeam uses compound tokens as position_ids for onset-based RoPE.
        # No torch.no_grad() here — LoRA needs gradients through the base model.
        outputs = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
            position_ids=input_ids,
        )
        hidden = outputs.last_hidden_state  # (B, T, hidden)
        # Cast to float32 for head stability (matches original v1 defensive path)
        logits = self.classifier(hidden.float())  # (B, T, 24)
        return logits


def load_records_from_manifest(
    manifest_path: str,
    label_dirs: List[str],
    split: str,
) -> List[Dict]:
    """Load note-level label records for a given split."""
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    entries = manifest.get('entries', manifest) if isinstance(manifest, dict) else manifest
    records = []
    for entry in entries:
        if entry.get('split') != split:
            continue
        piece_id = entry.get('piece_id', entry.get('id', ''))
        found = False
        for label_dir in label_dirs:
            for pattern in (f'{piece_id}.json',):
                path = os.path.join(label_dir, pattern)
                if os.path.isfile(path):
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        if isinstance(data, dict) and 'notes' in data:
                            data['_piece_id'] = piece_id   # track for downstream
                            records.append(data)
                            found = True
                            break
                    except (json.JSONDecodeError, IOError):
                        continue
            if found:
                break
            # Try integer-format filename
            try:
                int_id = int(piece_id)
                path = os.path.join(label_dir, f'{int_id:04d}.json')
                if os.path.isfile(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, dict) and 'notes' in data:
                        data['_piece_id'] = piece_id
                        records.append(data)
                        found = True
                        break
            except (ValueError, json.JSONDecodeError, IOError):
                pass
    return records


def compute_class_weights(records: List[Dict], mode: str = 'ens', ens_beta: float = 0.999) -> torch.Tensor:
    """Compute 24-length class-weight tensor. Mirrors train_harmonic_context_model.py."""
    counts = [0] * 24
    for rec in records:
        for note in rec.get('notes', []):
            idx = key_to_index(str(note.get('key', '')))
            if 0 <= idx < 24:
                counts[idx] += 1
    weights = torch.zeros(24)
    if mode == 'none' or sum(counts) == 0:
        weights.fill_(1.0)
    elif mode == 'ens':
        for c in range(24):
            n = max(counts[c], 1)
            eff = (1.0 - ens_beta ** n) / (1.0 - ens_beta)
            weights[c] = 1.0 / eff
        weights = weights * (24.0 / weights.sum())
    elif mode == 'sqrt':
        for c in range(24):
            weights[c] = 1.0 / math.sqrt(max(counts[c], 1))
        weights = weights * (24.0 / weights.sum())
    else:
        for c in range(24):
            weights[c] = 1.0 / max(counts[c], 1)
        weights = weights * (24.0 / weights.sum())
    return weights


def evaluate_per_note(
    model: MoonbeamPerNoteClassifier,
    loader: DataLoader,
    loss_fn: nn.Module,
    device: torch.device,
) -> Dict[str, float]:
    """Compute per-note loss / accuracy / MIREX on a loader.

    Windows are NOT stitched here (that's for the evaluator). This returns
    window-averaged metrics used for val-MIREX model selection.
    """
    model.eval()
    total_loss = 0.0
    total_count = 0
    total_correct = 0
    total_mirex = 0.0
    total_valid = 0
    mirex_table = build_mirex_table(device)
    with torch.no_grad():
        for batch in loader:
            compounds = batch['compounds'].to(device)
            labels = batch['labels'].to(device)
            mask = batch['attention_mask'].to(device)
            logits = model(compounds, attention_mask=mask)       # (B, T, 24)
            logits = logits.clamp(-50, 50)
            if torch.isnan(logits).any():
                continue
            flat_logits = logits.view(-1, 24)
            flat_labels = labels.view(-1)
            loss = loss_fn(flat_logits, flat_labels)
            total_loss += loss.item() * flat_labels.shape[0]
            valid = (flat_labels != -100)
            preds = flat_logits.argmax(dim=-1)
            total_correct += (preds[valid] == flat_labels[valid]).sum().item()
            # Per-note MIREX via table lookup
            m = mirex_table[preds[valid], flat_labels[valid]]
            total_mirex += m.sum().item()
            total_valid += int(valid.sum().item())
            total_count += flat_labels.shape[0]
    if total_valid == 0:
        return {'loss': float('nan'), 'accuracy': 0.0, 'mirex_weighted_score': 0.0, 'n_valid': 0}
    return {
        'loss': total_loss / max(total_count, 1),
        'accuracy': total_correct / total_valid,
        'mirex_weighted_score': total_mirex / total_valid,
        'n_valid': total_valid,
    }


def set_seed(seed: int, deterministic: bool = False) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if deterministic:
        os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
        try:
            torch.use_deterministic_algorithms(True, warn_only=True)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
        except Exception as exc:
            print(f'  (determinism partial: {exc})')


def parse_args():
    p = argparse.ArgumentParser(description='Fine-tune Moonbeam (per-note head) for 24-key detection')
    p.add_argument('--manifest', required=True)
    p.add_argument('--label-dirs', required=True)
    p.add_argument('--model-size', choices=['309M', '839M'], default='309M')
    p.add_argument('--base-checkpoint', default=None,
                   help='Override base Moonbeam .pt path. Default inferred from --model-size.')
    p.add_argument('--config', default=None,
                   help='Override Moonbeam config JSON path. Default inferred from --model-size.')
    p.add_argument('--epochs', type=int, default=10)
    p.add_argument('--batch-size', type=int, default=2)
    p.add_argument('--lr', type=float, default=1e-4)
    p.add_argument('--max-seq-len', type=int, default=512)
    p.add_argument('--window-hop', type=int, default=256)
    p.add_argument('--grad-accum-steps', type=int, default=4)
    p.add_argument('--checkpoint', default='research_data/moonbeam_pernote.pt')
    p.add_argument('--device', default='auto')
    p.add_argument('--use-lora', action='store_true', default=True)
    p.add_argument('--lora-r', type=int, default=16)
    p.add_argument('--lora-alpha', type=int, default=32)
    p.add_argument('--freeze-encoder', action='store_true',
                   help='Freeze the Moonbeam encoder (head-only training).')
    p.add_argument('--full-finetune', action='store_true',
                   help='Disable LoRA; unfreeze base model. Requires A100-class GPU for 839M.')
    p.add_argument('--weight-mode', choices=['ens', 'sqrt', 'none', 'inverse'], default='ens')
    p.add_argument('--ens-beta', type=float, default=0.999)
    p.add_argument('--selection-metric', choices=['val_mirex', 'val_accuracy', 'val_loss'],
                   default='val_mirex')
    p.add_argument('--warmup-epochs', type=int, default=2)
    p.add_argument('--patience', type=int, default=5,
                   help='Early stop if selection metric doesn\'t improve for this many epochs.')
    p.add_argument('--seed', type=int, default=20260309)
    p.add_argument('--deterministic', action='store_true', default=False)
    return p.parse_args()


def resolve_checkpoints(args) -> Tuple[str, str]:
    """Pick the right base .pt and config JSON based on --model-size."""
    base_default = {
        '309M': 'Moonbeam MIDI Foundation Model/moonbeam_309M.pt',
        '839M': 'Moonbeam MIDI Foundation Model/moonbeam_839M.pt',
    }
    cfg_default = {
        '309M': str(MOONBEAM_DIR / 'src' / 'llama_recipes' / 'configs' / 'model_config_309M.json'),
        '839M': str(MOONBEAM_DIR / 'src' / 'llama_recipes' / 'configs' / 'model_config.json'),
    }
    base = args.base_checkpoint or base_default[args.model_size]
    cfg  = args.config          or cfg_default[args.model_size]
    return base, cfg


def main():
    args = parse_args()
    set_seed(args.seed, deterministic=args.deterministic)

    # Device
    if args.device == 'auto':
        if torch.cuda.is_available():
            device = torch.device('cuda')
        elif torch.backends.mps.is_available():
            device = torch.device('mps')
        else:
            device = torch.device('cpu')
    else:
        device = torch.device(args.device)
    print(f'Device: {device}')
    print(f'Seed: {args.seed}  Deterministic: {args.deterministic}')

    base_checkpoint, config_path = resolve_checkpoints(args)
    print(f'Moonbeam size: {args.model_size}')
    print(f'Base checkpoint: {base_checkpoint}')
    print(f'Config: {config_path}')

    # Build Moonbeam encoder
    llama_cfg = LlamaConfig.from_pretrained(config_path)
    llama_cfg.use_cache = False
    base_model = LlamaForCausalLM(llama_cfg)
    print(f'  hidden_size={llama_cfg.hidden_size}  layers={llama_cfg.num_hidden_layers}')

    ckpt = torch.load(base_checkpoint, map_location='cpu', weights_only=False)
    state_dict = ckpt.get('model_state_dict', ckpt)
    clean_sd = {(k[7:] if k.startswith('module.') else k): v for k, v in state_dict.items()}
    missing, unexpected = base_model.load_state_dict(clean_sd, strict=False)
    print(f'Loaded pretrained weights: {len(clean_sd)} tensors, {len(missing)} missing, {len(unexpected)} unexpected')

    # Wrap with per-note head
    classifier = MoonbeamPerNoteClassifier(base_model, num_classes=24)

    # Trainable-parameter strategy
    if args.full_finetune:
        print('Full fine-tune mode: encoder unfrozen, no LoRA.')
    elif args.freeze_encoder:
        for p in classifier.encoder.parameters():
            p.requires_grad = False
        print('Encoder frozen — only classifier head trains.')
    else:
        from peft import LoraConfig, get_peft_model
        lora_cfg = LoraConfig(
            r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=0.05,
            target_modules=["q_proj", "v_proj"], bias="none",
            task_type="FEATURE_EXTRACTION",
        )
        classifier.encoder = get_peft_model(classifier.encoder, lora_cfg)
        print(f'LoRA: r={args.lora_r}, alpha={args.lora_alpha}, target=[q_proj, v_proj]')

    classifier = classifier.to(device)
    total = sum(p.numel() for p in classifier.parameters())
    trainable = sum(p.numel() for p in classifier.parameters() if p.requires_grad)
    print(f'Params: total={total:,}  trainable={trainable:,} ({100*trainable/total:.2f}%)')

    # Data
    label_dirs = [d.strip() for d in args.label_dirs.split(',')]
    train_records = load_records_from_manifest(args.manifest, label_dirs, 'train')
    val_records   = load_records_from_manifest(args.manifest, label_dirs, 'val')
    print(f'Records (note-level): {len(train_records)} train, {len(val_records)} val')

    train_ds = MoonbeamKeyDataset(train_records, max_seq_len=args.max_seq_len, window_hop=args.window_hop)
    val_ds   = MoonbeamKeyDataset(val_records,   max_seq_len=args.max_seq_len, window_hop=args.window_hop)
    print(f'Windows: {len(train_ds)} train, {len(val_ds)} val')

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              collate_fn=collate_moonbeam_per_note, num_workers=0)
    val_loader   = DataLoader(val_ds,   batch_size=args.batch_size, shuffle=False,
                              collate_fn=collate_moonbeam_per_note, num_workers=0)

    # Loss
    class_weights = compute_class_weights(train_records, mode=args.weight_mode, ens_beta=args.ens_beta).to(device)
    loss_fn = nn.CrossEntropyLoss(weight=class_weights, ignore_index=-100)
    print(f'Class weights (mode={args.weight_mode}): min={class_weights.min():.3f} max={class_weights.max():.3f}')

    # Optimiser
    optim_params = [p for p in classifier.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(optim_params, lr=args.lr, weight_decay=0.01)

    def lr_lambda(epoch):
        if epoch < args.warmup_epochs:
            return float(epoch + 1) / max(1, args.warmup_epochs)
        decay = max(1, args.epochs - args.warmup_epochs)
        progress = float(epoch - args.warmup_epochs) / decay
        return max(0.0, 0.5 * (1.0 + math.cos(math.pi * progress)))
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    # Training
    best_score = -float('inf') if args.selection_metric != 'val_loss' else float('inf')
    best_epoch = -1
    epochs_without_improvement = 0
    per_epoch_log = []

    for epoch in range(1, args.epochs + 1):
        classifier.train()
        t_loss, t_correct, t_valid = 0.0, 0, 0
        optimizer.zero_grad()
        t0 = time.time()

        for step, batch in enumerate(train_loader):
            compounds = batch['compounds'].to(device)
            labels    = batch['labels'].to(device)
            mask      = batch['attention_mask'].to(device)
            logits    = classifier(compounds, attention_mask=mask)
            logits    = logits.clamp(-50, 50)
            if torch.isnan(logits).any():
                optimizer.zero_grad(); continue

            flat_logits = logits.view(-1, 24)
            flat_labels = labels.view(-1)
            loss = loss_fn(flat_logits, flat_labels) / args.grad_accum_steps
            loss.backward()

            if (step + 1) % args.grad_accum_steps == 0:
                torch.nn.utils.clip_grad_norm_(optim_params, 1.0)
                optimizer.step()
                optimizer.zero_grad()

            t_loss += loss.item() * args.grad_accum_steps
            valid = (flat_labels != -100)
            preds = flat_logits.argmax(dim=-1)
            t_correct += (preds[valid] == flat_labels[valid]).sum().item()
            t_valid   += int(valid.sum().item())

            if device.type == 'mps' and (step + 1) % 200 == 0:
                torch.mps.empty_cache()

        if (step + 1) % args.grad_accum_steps != 0:
            torch.nn.utils.clip_grad_norm_(optim_params, 1.0)
            optimizer.step(); optimizer.zero_grad()

        scheduler.step()
        train_acc = t_correct / max(t_valid, 1)
        val_metrics = evaluate_per_note(classifier, val_loader, loss_fn, device)
        epoch_time = time.time() - t0

        print(f'Epoch {epoch:>2d}/{args.epochs} '
              f'({epoch_time:5.1f}s) '
              f'train_loss={t_loss/len(train_loader):.4f} train_acc={train_acc:.4f} || '
              f'val_loss={val_metrics["loss"]:.4f} val_acc={val_metrics["accuracy"]:.4f} '
              f'val_mirex={val_metrics["mirex_weighted_score"]:.4f}')

        per_epoch_log.append({
            'epoch': epoch, 'epoch_time_s': epoch_time,
            'train_loss': t_loss / max(len(train_loader), 1),
            'train_accuracy': train_acc,
            'val_loss': val_metrics['loss'],
            'val_accuracy': val_metrics['accuracy'],
            'val_mirex': val_metrics['mirex_weighted_score'],
            'lr': optimizer.param_groups[0]['lr'],
        })

        # Model selection
        current = {
            'val_mirex': val_metrics['mirex_weighted_score'],
            'val_accuracy': val_metrics['accuracy'],
            'val_loss': val_metrics['loss'],
        }[args.selection_metric]
        is_better = (current < best_score) if args.selection_metric == 'val_loss' else (current > best_score)
        if is_better:
            best_score = current
            best_epoch = epoch
            epochs_without_improvement = 0
            os.makedirs(os.path.dirname(args.checkpoint) or '.', exist_ok=True)
            torch.save({
                'epoch': epoch,
                'model_state_dict': classifier.state_dict(),
                'val_metrics': val_metrics,
                'selection_metric': args.selection_metric,
                'selection_metric_value': current,
                'seed': args.seed,
                'model_size': args.model_size,
                'hidden_size': llama_cfg.hidden_size,
                'num_layers': llama_cfg.num_hidden_layers,
                'use_lora': not args.full_finetune and not args.freeze_encoder,
                'full_finetune': args.full_finetune,
                'freeze_encoder': args.freeze_encoder,
                'lora_r': args.lora_r if not args.full_finetune else None,
                'lora_alpha': args.lora_alpha if not args.full_finetune else None,
                'weight_mode': args.weight_mode,
                'ens_beta': args.ens_beta,
                'max_seq_len': args.max_seq_len,
                'window_hop': args.window_hop,
                'learning_rate': args.lr,
                'batch_size': args.batch_size,
                'grad_accum_steps': args.grad_accum_steps,
                'warmup_epochs': args.warmup_epochs,
                'patience': args.patience,
                'is_oracle_result': False,  # Moonbeam is causal
                'causal': True,
                'base_checkpoint': base_checkpoint,
                'config_path': config_path,
            }, args.checkpoint)
            print(f'  -> saved best (epoch {epoch}, {args.selection_metric}={current:.4f})')
        else:
            epochs_without_improvement += 1
            if args.patience > 0 and epochs_without_improvement >= args.patience:
                print(f'Early stop: no improvement in {args.patience} epochs')
                break

    # Persist training log
    log_path = os.path.splitext(args.checkpoint)[0] + '_training_log.json'
    with open(log_path, 'w') as f:
        json.dump({
            'selection_metric': args.selection_metric,
            'best_epoch': best_epoch,
            'best_value': best_score,
            'seed': args.seed,
            'model_size': args.model_size,
            'per_epoch': per_epoch_log,
        }, f, indent=2)
    print(f'\nDone. Best {args.selection_metric}={best_score:.4f} at epoch {best_epoch}.')
    print(f'Saved training log to {log_path}')


if __name__ == '__main__':
    main()
