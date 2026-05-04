#!/usr/bin/env python3
"""Build a Phase I extended training manifest.

Extends `research_data/unified_training_manifest.json` with the Block B.3
DCML Strategy A pieces (all 141 as TRAIN; no test assignment to preserve
ATEPP-41 frozen split). Every appended record is flagged
`source = 'dcml-strategy-a'`.

Resulting manifest `research_data/unified_training_manifest_phase1.json`
is used by `train_phase1.py --manifest` when Phase I variants that need
chord supervision (T2 or any T2-containing combo) are trained.

Run:
    python phase1_beat_classical/prepare_phase1_manifest.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE_MANIFEST = ROOT / 'research_data' / 'unified_training_manifest.json'
DCML_LABELS = ROOT / 'research_data' / 'dcml_score_key_labels'
OUT_MANIFEST = ROOT / 'research_data' / 'unified_training_manifest_phase1.json'


def main() -> int:
    with open(BASE_MANIFEST) as f:
        manifest = json.load(f)
    original_n = len(manifest.get('entries', []))
    print(f'Base manifest: {original_n} entries')

    appended = 0
    for corpus_dir in sorted(DCML_LABELS.iterdir()):
        if not corpus_dir.is_dir():
            continue
        for fn in sorted(corpus_dir.glob('*.json')):
            with open(fn) as f:
                payload = json.load(f)
            stats = payload.get('statistics', {})
            notes = payload.get('notes', [])
            if not notes:
                continue
            # Compose a manifest-style entry
            keys_seen = set()
            for n in notes:
                key_cls = int(n['tonic_pc']) + (12 if n.get('is_minor') else 0)
                keys_seen.add(key_cls)
            entry = {
                'file_path': str(fn),
                'source': 'dcml-strategy-a',
                'piece_id': payload.get('piece_id', fn.stem),
                'composer': payload.get('corpus', '?'),
                'note_count': len(notes),
                'major_notes': stats.get('major_notes', 0),
                'minor_notes': stats.get('minor_notes', 0),
                'key_classes': sorted(keys_seen),
                'annotation_count': len(notes),   # per-note chord labels
                'split': 'train',                  # NEVER test — ATEPP-41 stays frozen
            }
            manifest['entries'].append(entry)
            appended += 1

    # Recompute statistics if present.
    if 'statistics' in manifest:
        manifest['statistics']['total_pieces'] = len(manifest['entries'])
        total_notes = sum(e['note_count'] for e in manifest['entries'])
        manifest['statistics']['total_notes'] = total_notes
        if 'by_source' in manifest['statistics']:
            manifest['statistics']['by_source']['dcml-strategy-a'] = appended
        if 'by_split' in manifest['statistics']:
            manifest['statistics']['by_split']['train'] = (
                manifest['statistics']['by_split'].get('train', 0) + appended
            )

    with open(OUT_MANIFEST, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f'Appended {appended} DCML Strategy A entries (all split=train).')
    print(f'New manifest: {OUT_MANIFEST} ({len(manifest["entries"])} total entries)')
    print(f'Note: ATEPP-41 test split is unchanged — no dcml-strategy-a entries '
          f'added with split=test.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
