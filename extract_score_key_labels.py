#!/usr/bin/env python3
"""
Extract score-note local-key labels and note-level JI teacher labels from MusicXML.

This script is intended for local research use. It does not assume that the
generated outputs are automatically redistributable.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import csv
from typing import Dict, List, Tuple

from musicxml_score_parser import parse_musicxml_score


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, 'ATEPP_JI_Dataset')
ATEPP_BASE = os.path.join(DATASET_DIR, 'ATEPP-1.2')
METADATA_PATH = os.path.join(DATASET_DIR, 'ATEPP-metadata-JI.csv')
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, 'research_data', 'score_key_labels')


FIFTHS_TO_MAJOR_KEY = {
    -7: 'Cb', -6: 'Gb', -5: 'Db', -4: 'Ab', -3: 'Eb', -2: 'Bb', -1: 'F',
    0: 'C', 1: 'G', 2: 'D', 3: 'A', 4: 'E', 5: 'B', 6: 'F#', 7: 'C#'
}

FIFTHS_TO_MINOR_KEY = {
    -7: 'Abm', -6: 'Ebm', -5: 'Bbm', -4: 'Fm', -3: 'Cm', -2: 'Gm', -1: 'Dm',
    0: 'Am', 1: 'Em', 2: 'Bm', 3: 'F#m', 4: 'C#m', 5: 'G#m', 6: 'D#m', 7: 'A#m'
}

KEY_TO_TONIC = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'Fb': 4,
    'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10,
    'Bb': 10, 'B': 11, 'Cb': 11,
    'Am': 9, 'A#m': 10, 'Bbm': 10, 'Bm': 11, 'Cm': 0, 'C#m': 1, 'Dbm': 1,
    'Dm': 2, 'D#m': 3, 'Ebm': 3, 'Em': 4, 'Fm': 5, 'F#m': 6, 'Gbm': 6,
    'Gm': 7, 'G#m': 8, 'Abm': 8,
}

JI_RATIOS_MAJOR = {
    0: 1.0, 1: 16 / 15, 2: 9 / 8, 3: 6 / 5, 4: 5 / 4, 5: 4 / 3,
    6: 45 / 32, 7: 3 / 2, 8: 8 / 5, 9: 5 / 3, 10: 9 / 5, 11: 15 / 8,
}

JI_RATIOS_MINOR = {
    0: 1.0, 1: 16 / 15, 2: 9 / 8, 3: 6 / 5, 4: 5 / 4, 5: 4 / 3,
    6: 45 / 32, 7: 3 / 2, 8: 8 / 5, 9: 5 / 3, 10: 16 / 9, 11: 15 / 8,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Extract score-note local-key labels from MusicXML')
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR, help='Directory for JSON label files')
    parser.add_argument('--limit', type=int, default=None, help='Optional limit for debugging')
    parser.add_argument(
        '--composition-ids',
        nargs='*',
        type=int,
        default=None,
        help='Optional composition ids to process',
    )
    parser.add_argument(
        '--include-grace-notes',
        action='store_true',
        help='Include grace notes in the extracted note array',
    )
    return parser.parse_args()


def load_unique_scores() -> List[Dict[str, object]]:
    grouped: Dict[int, Dict[str, object]] = {}

    with open(METADATA_PATH, 'r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            composition_id = int(row['composition_id'])
            if composition_id not in grouped:
                grouped[composition_id] = {
                    'composition_id': composition_id,
                    'composer': row['composer'],
                    'track': row['track'],
                    'score_path': row['score_path'],
                    'performances': 0,
                }
            grouped[composition_id]['performances'] += 1

    return [grouped[key] for key in sorted(grouped)]


def build_note_payload(note_row: Dict[str, object], note_index: int) -> Dict[str, object]:
    mode = str(note_row.get('mode', 'major')).lower()
    is_minor = mode in {'minor', 'min', 'm'}
    fifths = int(note_row.get('fifths', 0))
    key_name = FIFTHS_TO_MINOR_KEY.get(fifths, 'Am') if is_minor else FIFTHS_TO_MAJOR_KEY.get(fifths, 'C')
    tonic_pc = KEY_TO_TONIC.get(key_name, 0)
    pitch = int(note_row['pitch'])
    scale_degree = (pitch - tonic_pc) % 12
    ji_ratio = JI_RATIOS_MINOR if is_minor else JI_RATIOS_MAJOR
    ratio = ji_ratio.get(scale_degree, 1.0)
    cents_offset = 1200 * math.log2(ratio) - (scale_degree * 100)

    return {
        'index': note_index,
        'pitch': pitch,
        'measure_index': int(note_row.get('measure_index', 0)),
        'onset_div': float(note_row.get('onset_div', note_index)),
        'onset_beat': float(note_row.get('onset_beat', 0.0)),
        'duration_div': float(note_row.get('duration_div', 0.0)),
        'duration_beat': float(note_row.get('duration_beat', 0.0)),
        'key': key_name,
        'tonic_pc': tonic_pc,
        'is_minor': is_minor,
        'scale_degree': scale_degree,
        'ji_ratio': ratio,
        'cents_offset': round(cents_offset, 4),
    }


def export_labels(record: Dict[str, object], args: argparse.Namespace) -> None:
    full_score_path = os.path.join(ATEPP_BASE, str(record['score_path']))
    if not os.path.exists(full_score_path):
        raise FileNotFoundError(f'Score not found: {full_score_path}')

    if args.include_grace_notes:
        raise NotImplementedError('Grace-note extraction is not yet supported in the pure MusicXML parser path')

    parsed_score = parse_musicxml_score(full_score_path)

    notes = [
        build_note_payload(note_row, note_index)
        for note_index, note_row in enumerate(parsed_score['notes'])
    ]

    payload = {
        'composition_id': int(record['composition_id']),
        'composer': str(record['composer']),
        'track': str(record['track']),
        'score_path': str(record['score_path']),
        'performances': int(record['performances']),
        'include_grace_notes': bool(args.include_grace_notes),
        'note_count': len(notes),
        'key_change_count': len(parsed_score['key_changes']),
        'key_changes': parsed_score['key_changes'],
        'notes': notes,
    }

    filename = f"{int(record['composition_id']):04d}.json"
    output_path = os.path.join(args.output_dir, filename)
    with open(output_path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2)


def main() -> None:
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    records = load_unique_scores()
    if args.composition_ids:
        allowed = set(args.composition_ids)
        records = [record for record in records if int(record['composition_id']) in allowed]
    if args.limit is not None:
        records = records[:args.limit]

    for record in records:
        export_labels(record, args)
        print(f"Exported composition {record['composition_id']}: {record['composer']} - {record['track']}")


if __name__ == '__main__':
    main()
