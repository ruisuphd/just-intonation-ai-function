#!/usr/bin/env python3
"""BPS-FH cross-corpus eval manifest builder.

Closes R4.2 of POSTDOC_REVIEWER_PASS_2026-05-09.md (extract BPS-FH manifest
analogue from inline Colab Cell 4 / Cell 5 into a standalone script).

Background
----------
The BPS-FH cross-corpus eval (Tier 2.2) does NOT train a new model — it
zero-shot-evaluates the canonical ATEPP-trained Phase I checkpoints on
the 32 Beethoven Piano Sonata first movements. The "manifest" here is
therefore a single-split eval-only manifest (all 32 pieces tagged as
split='test'), used by `eval_bps_fh_from_checkpoints.py` to enumerate
which BPS-FH per-piece JSONs to evaluate.

Note: unlike POP909, BPS-FH does NOT need train/val splits — there is no
training step. The manifest is purely a record of which pieces were
evaluated and where their per-piece JSONs live, for reproducibility.

Usage
-----
    python build_bps_fh_manifest.py
    python build_bps_fh_manifest.py \\
        --input-dir research_data/bps_fh_score_key_labels \\
        --output research_data/bps_fh_manifest_2026-05-09.json

Author: Rui Su, 2026-05-09. R4.2 closure script.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).resolve().parent


def build_manifest(input_dir: Path, source_tag: str = 'bps_fh') -> Dict:
    """Enumerate BPS-FH ingested per-piece JSONs and return a single-split
    eval-only manifest dict."""
    if not input_dir.is_dir():
        raise SystemExit(
            f'BPS-FH input directory not found: {input_dir}\n'
            f'Run `python parse_bps_fh.py --input <BPS-FH root> '
            f'--output {input_dir}` first.'
        )

    pattern = str(input_dir / 'BPS_FH_*.json')
    files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit(
            f'No BPS_FH_*.json files found in {input_dir}. '
            f'Run `python parse_bps_fh.py` to generate them.'
        )

    entries = []
    for path in files:
        try:
            d = json.load(open(path))
        except Exception as e:
            print(f'  WARN: skipping unreadable {path}: {e}')
            continue
        if not d.get('notes'):
            print(f'  WARN: skipping {path} (no notes array)')
            continue
        entries.append({
            'id': d.get('id', os.path.splitext(os.path.basename(path))[0]),
            'composition_id': d.get('id', os.path.splitext(os.path.basename(path))[0]),
            'source': source_tag,
            'split': 'test',  # eval-only; no training split
            'file_path': str(path),
            'converter_strategy': 'A',
            'reference': d.get('reference', 'Chen & Su (2018), ISMIR'),
        })

    return {
        'created': str(date.today()),
        'corpus': 'BPS-FH (Beethoven Piano Sonatas, first movements; n=32)',
        'reference': 'Chen, T.-P., & Su, L. (2018). Functional harmony recognition '
                     'with multi-task recurrent neural networks. ISMIR 2018.',
        'eval_only': True,  # marker: no training splits
        'n_test': len(entries),
        'entries': entries,
    }


def validate_manifest(manifest: Dict) -> None:
    """Sanity checks for the BPS-FH eval-only manifest."""
    n = len(manifest['entries'])
    if n != manifest['n_test']:
        raise SystemExit(f'Manifest internal inconsistency: n_test={manifest["n_test"]} '
                         f'but {n} entries.')
    if n != 32:
        print(f'  WARN: expected 32 BPS-FH pieces, got {n}')
    # All entries should be split=test (this is an eval-only manifest)
    bad = [e for e in manifest['entries'] if e.get('split') != 'test']
    if bad:
        raise SystemExit(f'Manifest validation failed: {len(bad)} entries '
                         f'have non-test split (expected all split=test for eval-only).')
    # No duplicate piece IDs
    ids = [e['id'] for e in manifest['entries']]
    if len(set(ids)) != len(ids):
        from collections import Counter
        dupes = [k for k, v in Counter(ids).items() if v > 1]
        raise SystemExit(f'Manifest validation failed: duplicate IDs {dupes[:5]}')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--input-dir',
                    default='research_data/bps_fh_score_key_labels',
                    help='Directory of per-piece BPS_FH_*.json files '
                         '(output of parse_bps_fh.py)')
    ap.add_argument('--output',
                    default=f'research_data/bps_fh_manifest_{date.today().isoformat()}.json',
                    help='Output manifest JSON path')
    args = ap.parse_args()

    input_dir = (HERE / args.input_dir).resolve()
    output_path = (HERE / args.output).resolve()

    print(f'Building BPS-FH eval-only manifest...')
    print(f'  Input dir: {input_dir}')
    print(f'  Output: {output_path}')

    manifest = build_manifest(input_dir)
    validate_manifest(manifest)

    print(f'  ✓ Built manifest: {len(manifest["entries"])} entries '
          f'(all split=test, eval-only)')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2))
    print(f'  ✓ Wrote {output_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
