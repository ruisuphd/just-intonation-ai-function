#!/usr/bin/env python3
"""Normalise the `key` string in every DCML Strategy A per-note JSON.

The B.3 parser emits keys in DCML convention (`"b"` for B minor); the base
training pipeline expects ATEPP convention (`"Bm"`). This one-time batch
rewrites every per-note JSON under `research_data/dcml_score_key_labels/`
in place, replacing the `key` field on every note while preserving
`tonic_pc` / `is_minor` and every chord-aware extra unchanged.

Safe to re-run — idempotent: if the keys are already in ATEPP form the
rewrite is a no-op.

Run:
    python phase1_beat_classical/normalise_dcml_key_strings.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DCML_LABELS = ROOT / 'research_data' / 'dcml_score_key_labels'

PITCH = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def dcml_to_atepp(tonic_pc: int, is_minor: bool) -> str:
    return PITCH[int(tonic_pc) % 12] + ('m' if is_minor else '')


def rewrite(path: Path) -> bool:
    with open(path) as f:
        d = json.load(f)
    notes = d.get('notes', [])
    if not notes:
        return False
    changed = False
    for n in notes:
        tpc = n.get('tonic_pc')
        im = n.get('is_minor', False)
        if tpc is None:
            continue
        new_key = dcml_to_atepp(tpc, im)
        if n.get('key') != new_key:
            n['key'] = new_key
            changed = True
    # Key regions
    for reg in d.get('key_regions', []):
        kc = reg.get('key_class')
        if kc is None: continue
        new = PITCH[kc % 12] + ('m' if kc >= 12 else '')
        if reg.get('key') != new:
            reg['key'] = new
            changed = True
    # Global key
    if 'global_key_class' in d:
        gcls = d['global_key_class']
        new_gk = PITCH[gcls % 12] + ('m' if gcls >= 12 else '')
        if d.get('global_key') != new_gk:
            d['global_key'] = new_gk
            changed = True
    if changed:
        with open(path, 'w') as f:
            json.dump(d, f, indent=2)
    return changed


def main() -> int:
    touched = 0
    total = 0
    for sub in sorted(DCML_LABELS.iterdir()):
        if not sub.is_dir(): continue
        for fn in sorted(sub.glob('*.json')):
            total += 1
            if rewrite(fn):
                touched += 1
    print(f'Scanned {total} JSONs, rewrote {touched} ({touched/max(total,1)*100:.1f} %).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
