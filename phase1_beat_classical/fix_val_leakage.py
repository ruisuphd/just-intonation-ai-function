#!/usr/bin/env python3
"""Produce a leakage-free Phase I manifest by removing the 18 DCML pieces
that appear in both train (via source=dcml-strategy-a) and val (via
source=dcml-expert).

Safer to remove from train than from val: val stays bit-identical to
Phase B's val split, preserving back-compat of val-MIREX comparisons.

Reconstructed 2026-04-25 after the original was removed in a directory cleanup.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_IN = ROOT / 'research_data' / 'unified_training_manifest_phase1.json'
MANIFEST_OUT = ROOT / 'research_data' / 'unified_training_manifest_phase1_clean.json'


def piece_stem(e):
    p = e.get('piece_id', '')
    if p: return str(p)
    fp = e.get('file_path', '')
    return fp.rsplit('/', 1)[-1].replace('.json', '') if fp else ''


def main() -> int:
    with open(MANIFEST_IN) as f:
        m = json.load(f)
    val_ids = {piece_stem(e) for e in m['entries']
               if e['split'] == 'val'}
    sa_train = [e for e in m['entries']
                if e['source'] == 'dcml-strategy-a' and e['split'] == 'train']
    sa_leaked = {piece_stem(e) for e in sa_train if piece_stem(e) in val_ids}
    print(f'Leaked pieces to remove from Strategy A train: {len(sa_leaked)}')
    for p in sorted(sa_leaked):
        print(f'  - {p}')

    cleaned = dict(m)
    cleaned['entries'] = [
        e for e in m['entries']
        if not (e['source'] == 'dcml-strategy-a'
                and e['split'] == 'train'
                and piece_stem(e) in sa_leaked)
    ]
    removed = len(m['entries']) - len(cleaned['entries'])
    print(f'\nOriginal: {len(m["entries"])} entries')
    print(f'Cleaned:  {len(cleaned["entries"])} entries ({removed} removed)')
    src_counter = Counter(e['source'] for e in cleaned['entries'])
    print(f'By source: {dict(src_counter)}')
    split_counter = Counter(e['split'] for e in cleaned['entries'])
    print(f'By split: {dict(split_counter)}')

    val_orig = sorted(piece_stem(e) for e in m['entries'] if e['split'] == 'val')
    val_clean = sorted(piece_stem(e) for e in cleaned['entries'] if e['split'] == 'val')
    assert val_orig == val_clean, 'val split changed — should not happen'
    print('\n✓ Val split preserved bit-identical to original')

    sa_clean = {piece_stem(e) for e in cleaned['entries']
                if e['source'] == 'dcml-strategy-a'}
    remaining_leak = {piece_stem(e) for e in cleaned['entries']
                      if e['split'] == 'val'} & sa_clean
    print(f'✓ Remaining leakage: {len(remaining_leak)} pieces')
    assert len(remaining_leak) == 0

    if 'statistics' in cleaned:
        cleaned['statistics']['total_pieces'] = len(cleaned['entries'])

    with open(MANIFEST_OUT, 'w') as f:
        json.dump(cleaned, f, indent=2)
    print(f'\nWrote {MANIFEST_OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
