#!/usr/bin/env python3
"""POP909 manifest builder (Phase I-compatible).

Closes R4.2 of POSTDOC_REVIEWER_PASS_2026-05-09.md (extract POP909 manifest
builder from inline Colab Cell 6/Cell 31 into a standalone script).

Background
----------
The POP909 cross-corpus evaluation (Tier 2.1) requires a Phase I manifest
that the trainer (`phase1_beat_classical/train_phase1.py`) and the eval
script (`eval_pop909_from_checkpoints.py`) can both consume. The manifest
shape mirrors the unified ATEPP+DCML manifest:

  {
    'created': 'YYYY-MM-DD',
    'rng_seed': 20260508,
    'split_ratios': {'train': 0.70, 'val': 0.15, 'test': 0.15},
    'n_train': N_TRAIN, 'n_val': N_VAL, 'n_test': N_TEST,
    'entries': [
      {'id': 'POP909_001', 'composition_id': 'POP909_001',
       'source': 'pop909', 'split': 'train',
       'file_path': 'research_data/pop909_score_key_labels/POP909_001.json',
       'converter_strategy': 'A'},
      ...
    ]
  }

Critical correctness check (R4.5 in POSTDOC_REVIEWER_PASS_2026-05-09.md):
the manifest MUST have non-zero counts in all three splits. The original
POP909 manifest version 1 (2026-05-08) had 80/20 train/test with 0 val,
which trapped the trainer's best_epoch at 1 and rendered the eval JSONs
zero. This script ALWAYS writes a 70/15/15 manifest and refuses to write
one with any empty split.

Usage
-----
    # Default 70/15/15 split with the canonical RNG seed
    python build_pop909_manifest.py

    # Specify alternative paths and split ratios
    python build_pop909_manifest.py \\
        --input-dir research_data/pop909_score_key_labels \\
        --output research_data/pop909_manifest_2026-05-09.json \\
        --rng-seed 20260508 \\
        --train-frac 0.70 --val-frac 0.15

Author: Rui Su, 2026-05-09. R4.2 closure script.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).resolve().parent


def build_manifest(input_dir: Path, train_frac: float, val_frac: float,
                   rng_seed: int, source_tag: str = 'pop909') -> Dict:
    """Enumerate POP909 ingested JSONs, shuffle deterministically, and
    return a Phase I-compatible manifest dict.

    Refuses to return a manifest with any empty split — protects against
    the val-empty bug that trapped the 2026-05-08 trainer at epoch 1.
    """
    if not input_dir.is_dir():
        raise SystemExit(f'POP909 input directory not found: {input_dir}\n'
                         f'Run `python parse_pop909.py --input <POP909 root> '
                         f'--output {input_dir}` first.')

    pattern = str(input_dir / 'POP909_*.json')
    files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit(f'No POP909_*.json files found in {input_dir}.\n'
                         f'Run `python parse_pop909.py` to generate them.')

    if not (0 < train_frac < 1 and 0 < val_frac < 1 and train_frac + val_frac < 1):
        raise SystemExit(f'Invalid split fractions: train={train_frac}, '
                         f'val={val_frac}; need 0 < each < 1 and train + val < 1')

    rng = random.Random(rng_seed)
    files_copy = list(files)
    rng.shuffle(files_copy)
    n = len(files_copy)
    n_train = int(train_frac * n)
    n_val = int(val_frac * n)
    train_files = files_copy[:n_train]
    val_files = files_copy[n_train:n_train + n_val]
    test_files = files_copy[n_train + n_val:]

    splits = {'train': train_files, 'val': val_files, 'test': test_files}
    empty = [s for s, fs in splits.items() if len(fs) == 0]
    if empty:
        raise SystemExit(
            f'Manifest builder refused: empty splits {empty}. '
            f'Increase the input corpus size or adjust split fractions. '
            f'(The trainer requires non-zero val for proper checkpoint '
            f'selection; an empty val split causes best_epoch to lock at 1 '
            f'with val_mirex stuck at 0 — see Su 2026r §3.1.)'
        )

    entries = []
    for split_name, file_list in splits.items():
        for path in file_list:
            try:
                d = json.load(open(path))
            except Exception as e:
                print(f'  WARN: skipping unreadable {path}: {e}')
                continue
            entries.append({
                'id': d.get('id', os.path.splitext(os.path.basename(path))[0]),
                'composition_id': d.get('id', os.path.splitext(os.path.basename(path))[0]),
                'source': source_tag,
                'split': split_name,
                'file_path': str(path),
                'converter_strategy': 'A',
            })

    return {
        'created': str(date.today()),
        'rng_seed': rng_seed,
        'split_ratios': {'train': train_frac, 'val': val_frac,
                         'test': 1 - train_frac - val_frac},
        'n_train': len(train_files),
        'n_val': len(val_files),
        'n_test': len(test_files),
        'entries': entries,
    }


def validate_manifest(manifest: Dict) -> None:
    """Sanity checks. R4.5 — refuses any manifest with empty splits."""
    splits_tally = {s: sum(1 for e in manifest['entries'] if e.get('split') == s)
                    for s in ('train', 'val', 'test')}
    empty = [s for s, n in splits_tally.items() if n == 0]
    if empty:
        raise SystemExit(
            f'Manifest validation failed: empty splits {empty}. '
            f'Refusing to write — would break trainer best_epoch selection.'
        )
    # Cross-check the entry count matches the n_* fields
    for s in ('train', 'val', 'test'):
        expected = manifest[f'n_{s}']
        actual = splits_tally[s]
        if expected != actual:
            raise SystemExit(
                f'Manifest internal inconsistency: n_{s}={expected} but '
                f'entries with split={s!r} count to {actual}.'
            )
    # No duplicate piece IDs
    ids = [e['id'] for e in manifest['entries']]
    if len(set(ids)) != len(ids):
        from collections import Counter
        dupes = [k for k, v in Counter(ids).items() if v > 1]
        raise SystemExit(f'Manifest validation failed: duplicate IDs {dupes[:5]}...')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--input-dir',
                    default='research_data/pop909_score_key_labels',
                    help='Directory of per-piece POP909_*.json files '
                         '(output of parse_pop909.py)')
    ap.add_argument('--output',
                    default=f'research_data/pop909_manifest_{date.today().isoformat()}.json',
                    help='Output manifest JSON path')
    ap.add_argument('--rng-seed', type=int, default=20260508,
                    help='Deterministic shuffle seed (default 20260508 — '
                         'matches the 2026-05-08 frozen split for cross-tool '
                         'consistency)')
    ap.add_argument('--train-frac', type=float, default=0.70)
    ap.add_argument('--val-frac', type=float, default=0.15)
    args = ap.parse_args()

    input_dir = (HERE / args.input_dir).resolve()
    output_path = (HERE / args.output).resolve()

    print(f'Building POP909 manifest...')
    print(f'  Input dir: {input_dir}')
    print(f'  Output: {output_path}')
    print(f'  Split: train={args.train_frac:.2f}, val={args.val_frac:.2f}, '
          f'test={1 - args.train_frac - args.val_frac:.2f}')
    print(f'  RNG seed: {args.rng_seed}')

    manifest = build_manifest(input_dir, args.train_frac, args.val_frac,
                              args.rng_seed)
    validate_manifest(manifest)

    print(f'  ✓ Built manifest: {len(manifest["entries"])} entries '
          f'({manifest["n_train"]} train + {manifest["n_val"]} val + '
          f'{manifest["n_test"]} test)')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2))
    print(f'  ✓ Wrote {output_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
