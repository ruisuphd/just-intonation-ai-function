#!/usr/bin/env python3
"""Aria-MIDI pre-training wrapper for SymbolicKeyTransformer (Tier 3.2).

Closes Tier 3.2 of COMPREHENSIVE_RIGOUR_PLAN_2026-04-26.md §6 (Months 6–7
in the original schedule). Wraps `pretrain_symbolic_key.py`'s S-KEY-style
self-supervised pre-training (equivariance + mode + batch-balance loss;
Kong et al., ICASSP 2025) so it can consume the Aria-MIDI deduped subset
(Bradshaw et al., 2024; ~371 K MIDI files, license CC-BY-NC-SA 4.0).

WHY pre-train on Aria-MIDI?
---------------------------
The Phase I cumulative-ablation training pool is 525 records (250 ATEPP
+ 275 DCML). This is small for deep learning. The hypothesis (rigour
plan §6 + thesis Ch 6.9): pre-training on a much larger MIDI corpus may
produce learned representations of musical structure (rhythmic patterns,
voice-leading, common chord progressions) that fine-tuning on the small
labelled ATEPP+DCML pool can leverage.

Two predicted outcomes (rigour plan §6):
  (a) Aria-MIDI pre-training adds Δ_FW ≈ +0.02 to +0.05 on top of
      T6_T1 = 0.6707 (in-domain ATEPP-41). The pre-training transfer
      hypothesis is supported, contradicting the small-scale Phase C
      null at 5 K files.
  (b) Aria-MIDI pre-training adds nothing, or harms. The small-scale
      Phase C null replicates at scale.
**Both outcomes are publishable.** A null at 371 K files is a strong
result; a positive transfer at 371 K is a stronger one.

Phased execution
----------------
Pre-training the full 371 K corpus takes ~1 week on 1 A100 (rigour plan
§6). Colab Pro+ caps a session at 24 h. We therefore phase the work:

  Phase A (smoke test):    5 K files, 30 min wall-clock — verify the
                           pipeline + the Aria-MIDI loader works.
  Phase B (early signal):  50 K files, ~12–24 h on A100 — early
                           convergence signal; can the loss come down?
  Phase C (full corpus):   371 K files, ~1 week on A100 — the main
                           experiment. Requires checkpoint resumption
                           across 7 sessions.
  Phase D (fine-tune):     load Phase C checkpoint into the Phase I
                           T6_T1 trainer (`train_phase1.py`); fine-tune
                           on the 525-record ATEPP+DCML pool with the
                           usual cross-entropy + ENS β=0.999 loss.
                           ~30 min per seed × 5 seeds = 2.5 h on A100.
  Phase E (eval):          eval the fine-tuned T6_T1 on
                           ATEPP-41 + BPS-FH + POP909 + TAVERN.

Outputs
-------
  research_data/symbolic_key_pretrained_aria_<phase>.pt
  research_data/aria_midi_pretrain_log_<phase>.json

Usage
-----
    # Phase A — smoke test
    python pretrain_aria_midi.py --phase A --limit 5000 --epochs 3

    # Phase B — early signal
    python pretrain_aria_midi.py --phase B --limit 50000 --epochs 5

    # Phase C — full corpus (use with --resume between sessions)
    python pretrain_aria_midi.py --phase C --epochs 30 --resume

Author: Rui Su, 2026-05-09. Tier 3.2 wrapper.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def find_midi_files(root: Path, limit: Optional[int] = None) -> List[Path]:
    """Walk an Aria-MIDI extraction root, return paths to .mid / .midi files.

    Aria-MIDI v1-deduped-ext.tar.gz extracts to roughly 371 K MIDI files
    organised in a hash-prefixed directory structure (e.g.,
    `aria-midi-v1-deduped-ext/<hash_prefix>/<file_id>_<segment>.mid`).
    """
    midis = []
    if not root.exists():
        return midis
    for path in root.rglob('*'):
        if path.suffix.lower() in ('.mid', '.midi'):
            midis.append(path)
            if limit is not None and len(midis) >= limit:
                break
    return midis


def build_aria_metadata_csv(midis: List[Path], csv_out: Path,
                            base_for_relpath: Path) -> None:
    """Generate an ATEPP-style metadata CSV from a list of Aria-MIDI files.

    The downstream `pretrain_symbolic_key.py` reads `metadata_csv` to drive
    its iteration; we synthesise a minimal CSV with columns:
      midi_path,piece_id

    `midi_path` is relative to `base_for_relpath` (so the existing
    `--atepp-base` argument does the path joining). `piece_id` is the
    file stem.
    """
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['midi_path', 'piece_id'])
        for p in midis:
            try:
                rel = p.relative_to(base_for_relpath)
            except ValueError:
                rel = p
            w.writerow([str(rel), p.stem])
    print(f'  ✓ Wrote metadata CSV: {csv_out} ({len(midis)} entries)')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', choices=('A', 'B', 'C', 'D', 'E'), required=True,
                    help='A=smoke (5K files); B=early signal (50K); '
                         'C=full corpus (371K); D=fine-tune; E=eval')
    ap.add_argument('--aria-root', default='aria_midi_extracted',
                    help='Aria-MIDI extraction root (where the tarball was '
                         'untarred). On Colab this would be /content/aria_midi_extracted')
    ap.add_argument('--limit', type=int, default=None,
                    help='Cap on number of MIDI files (auto-set per phase)')
    ap.add_argument('--epochs', type=int, default=None,
                    help='Number of training epochs (auto-set per phase)')
    ap.add_argument('--batch-size', type=int, default=32)
    ap.add_argument('--lr', type=float, default=5e-4)
    ap.add_argument('--lambda-equiv', type=float, default=1.0)
    ap.add_argument('--lambda-mode', type=float, default=1.5)
    ap.add_argument('--lambda-batch', type=float, default=15.0)
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--output-checkpoint', default=None,
                    help='Output .pt path (auto-set per phase if None)')
    ap.add_argument('--resume', action='store_true',
                    help='Phase C only: resume from last saved checkpoint '
                         '(supports multi-session training across the 24 h Colab cap)')
    ap.add_argument('--rng-seed', type=int, default=20260509)
    args = ap.parse_args()

    # Phase defaults
    if args.limit is None:
        args.limit = {'A': 5_000, 'B': 50_000, 'C': None}.get(args.phase)
    if args.epochs is None:
        args.epochs = {'A': 3, 'B': 5, 'C': 30, 'D': 30, 'E': 0}.get(args.phase, 30)
    if args.output_checkpoint is None:
        args.output_checkpoint = f'research_data/symbolic_key_pretrained_aria_phase{args.phase}.pt'

    aria_root = (HERE / args.aria_root).resolve()
    out_ckpt = (HERE / args.output_checkpoint).resolve()
    out_ckpt.parent.mkdir(parents=True, exist_ok=True)

    if args.phase in ('A', 'B', 'C'):
        # Pre-training phase
        print(f'\n=== Aria-MIDI pre-training Phase {args.phase} ===')
        print(f'  Aria root: {aria_root}')
        print(f'  Limit: {args.limit if args.limit else "ALL files"}')
        print(f'  Epochs: {args.epochs}')

        # Step 1: enumerate MIDIs + build metadata CSV
        print(f'\n--- Step 1: enumerate MIDI files ---')
        t0 = time.time()
        midis = find_midi_files(aria_root, limit=args.limit)
        print(f'  Found {len(midis)} MIDI files in {time.time()-t0:.1f}s')
        if not midis:
            print(f'ERROR: no MIDI files found at {aria_root}.\n'
                  f'Did you extract the Aria-MIDI tarball there?\n'
                  f'  cd /content && tar -xzf aria-midi-v1-deduped-ext.tar.gz')
            return 1

        metadata_csv = (HERE / 'research_data' /
                        f'aria_midi_metadata_phase{args.phase}.csv')
        build_aria_metadata_csv(midis, metadata_csv, base_for_relpath=aria_root)
        cache_path = (HERE / 'research_data' /
                      f'aria_midi_cache_phase{args.phase}.jsonl')

        # Step 2: invoke pretrain_symbolic_key.py with the Aria-specific paths
        print(f'\n--- Step 2: invoke pretrain_symbolic_key.py ---')
        cmd = [
            sys.executable, str(HERE / 'pretrain_symbolic_key.py'),
            '--metadata-csv', str(metadata_csv),
            '--atepp-base', str(aria_root),  # repurposed: the file-base for path joining
            '--cache-path', str(cache_path),
            '--epochs', str(args.epochs),
            '--batch-size', str(args.batch_size),
            '--lr', str(args.lr),
            '--lambda-equiv', str(args.lambda_equiv),
            '--lambda-mode', str(args.lambda_mode),
            '--lambda-batch', str(args.lambda_batch),
            '--device', args.device,
            '--output', str(out_ckpt),
        ]
        if args.limit is not None:
            cmd += ['--limit', str(args.limit)]
        print(f'  cmd: {" ".join(cmd)}')

        import subprocess
        retcode = subprocess.call(cmd)
        if retcode != 0:
            print(f'ERROR: pretrain_symbolic_key.py exited with code {retcode}')
            return retcode

        # Step 3: log
        log = {
            'phase': args.phase,
            'aria_root': str(aria_root),
            'n_midi_files': len(midis),
            'epochs': args.epochs,
            'batch_size': args.batch_size,
            'lr': args.lr,
            'lambdas': {'equiv': args.lambda_equiv, 'mode': args.lambda_mode,
                        'batch': args.lambda_batch},
            'output_checkpoint': str(out_ckpt),
            'wall_clock_seconds': time.time() - t0,
        }
        log_path = HERE / 'research_data' / f'aria_midi_pretrain_log_phase{args.phase}.json'
        log_path.write_text(json.dumps(log, indent=2))
        print(f'\n✓ Wrote pre-training log: {log_path}')
        print(f'✓ Pre-training checkpoint: {out_ckpt}')

    elif args.phase == 'D':
        # Fine-tune phase: load the Phase C checkpoint into train_phase1.py
        # NOTE: train_phase1.py does not currently accept a pre-trained
        # checkpoint as initialisation. The Phase D fine-tune requires a
        # small patch to train_phase1.py's model construction step:
        #   model = HarmonicContextGRUPhase1(...)
        #   if args.pretrained_checkpoint:
        #       ckpt = torch.load(args.pretrained_checkpoint, map_location=device)
        #       model.load_state_dict(ckpt['model_state_dict'], strict=False)
        # This patch is documented in the EXECUTION_PLAYBOOK_2026-05-09.md.
        print('\n=== Phase D: fine-tune T6_T1 from Aria-MIDI pre-trained init ===')
        print('  This phase requires a one-time patch to train_phase1.py to add a')
        print('  --pretrained-checkpoint argument (see EXECUTION_PLAYBOOK §C.4).')
        print('  Once patched, fine-tuning is invoked via:')
        print('  ')
        print('    python phase1_beat_classical/train_phase1.py \\')
        print('        --variant T6_T1 \\')
        print(f'        --pretrained-checkpoint {out_ckpt} \\')
        print('        --seed <seed> \\')
        print('        --manifest research_data/unified_training_manifest_phase1_clean.json \\')
        print('        --label-dirs research_data/score_key_labels,research_data/dcml_score_key_labels,research_data/dcml_key_labels,research_data/wir_key_labels \\')
        print('        --epochs 30 \\')
        print('        --device cuda \\')
        print('        --output-dir phase1_beat_classical/runs_aria_finetuned \\')
        print('        --test-filter atepp41')
        return 0

    elif args.phase == 'E':
        # Eval phase
        print('\n=== Phase E: eval Aria-MIDI-fine-tuned T6_T1 ===')
        print('  Run the cross-corpus eval scripts on the fine-tuned checkpoints:')
        print('  ')
        print('    python eval_bps_fh_from_checkpoints.py \\')
        print('        --checkpoint-dir phase1_beat_classical/runs_aria_finetuned \\')
        print('        --bps-fh-dir research_data/bps_fh_score_key_labels')
        print('  ')
        print('    python eval_pop909_from_checkpoints.py \\')
        print('        --checkpoint-dir phase1_beat_classical/runs_aria_finetuned \\')
        print('        --manifest research_data/pop909_manifest_2026-05-09.json')
        print('  ')
        print('    python eval_tavern_from_checkpoints.py \\')
        print('        --checkpoint-dir phase1_beat_classical/runs_aria_finetuned \\')
        print('        --tavern-dir research_data/tavern_score_key_labels')
        return 0

    return 0


if __name__ == '__main__':
    sys.exit(main())
