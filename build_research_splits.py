#!/usr/bin/env python3
"""
Create deterministic composition-level research splits for ATEPP_JI_Dataset.

The split policy is intentionally composition-based to avoid leakage across
multiple performances of the same work.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import csv
from dataclasses import dataclass
from typing import Dict, List


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
METADATA_PATH = os.path.join(BASE_DIR, 'ATEPP_JI_Dataset', 'ATEPP-metadata-JI.csv')
OUTPUT_DIR = os.path.join(BASE_DIR, 'research_data')
OUTPUT_PATH = os.path.join(OUTPUT_DIR, 'composition_splits.json')
SEED = 20260309

TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
TEST_RATIO = 0.15


@dataclass
class CompositionEntry:
    composition_id: int
    composer: str
    track: str
    score_path: str
    performances: int


def stable_sort_key(seed: int, composer: str, composition_id: int) -> str:
    token = f'{seed}:{composer}:{composition_id}'.encode('utf-8')
    return hashlib.sha256(token).hexdigest()


def split_counts(count: int) -> Dict[str, int]:
    if count <= 1:
        return {'train': count, 'validation': 0, 'test': 0}

    train = math.floor(count * TRAIN_RATIO)
    validation = math.floor(count * VAL_RATIO)
    test = count - train - validation

    if validation == 0 and count >= 3:
        validation = 1
        train -= 1
    if test == 0 and count >= 5:
        test = 1
        train -= 1

    if train <= 0:
        train = max(1, count - validation - test)

    return {'train': train, 'validation': validation, 'test': test}


def load_compositions() -> List[CompositionEntry]:
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

    entries = []
    for row in sorted(grouped.values(), key=lambda item: item['composition_id']):
        entries.append(
            CompositionEntry(
                composition_id=int(row['composition_id']),
                composer=str(row['composer']),
                track=str(row['track']),
                score_path=str(row['score_path']),
                performances=int(row['performances']),
            )
        )

    return entries


def build_splits(entries: List[CompositionEntry]) -> Dict[str, List[CompositionEntry]]:
    by_composer: Dict[str, List[CompositionEntry]] = {}
    for entry in entries:
        by_composer.setdefault(entry.composer, []).append(entry)

    splits = {'train': [], 'validation': [], 'test': []}

    for composer in sorted(by_composer):
        composer_entries = sorted(
            by_composer[composer],
            key=lambda item: stable_sort_key(SEED, composer, item.composition_id),
        )
        counts = split_counts(len(composer_entries))

        train_end = counts['train']
        validation_end = train_end + counts['validation']

        splits['train'].extend(composer_entries[:train_end])
        splits['validation'].extend(composer_entries[train_end:validation_end])
        splits['test'].extend(composer_entries[validation_end:])

    return splits


def summarize_split(entries: List[CompositionEntry]) -> Dict[str, object]:
    composer_counts: Dict[str, int] = {}
    performance_count = 0

    for entry in entries:
        composer_counts[entry.composer] = composer_counts.get(entry.composer, 0) + 1
        performance_count += entry.performances

    return {
        'compositions': len(entries),
        'performances': performance_count,
        'composer_distribution': dict(sorted(composer_counts.items())),
    }


def main() -> None:
    if not os.path.exists(METADATA_PATH):
        raise FileNotFoundError(f'Metadata not found: {METADATA_PATH}')

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    entries = load_compositions()
    splits = build_splits(entries)

    payload = {
        'seed': SEED,
        'split_by': 'composition_id',
        'ratios': {
            'train': TRAIN_RATIO,
            'validation': VAL_RATIO,
            'test': TEST_RATIO,
        },
        'summary': {name: summarize_split(items) for name, items in splits.items()},
        'splits': {
            name: [
                {
                    'composition_id': item.composition_id,
                    'composer': item.composer,
                    'track': item.track,
                    'score_path': item.score_path,
                    'performances': item.performances,
                }
                for item in sorted(items, key=lambda row: row.composition_id)
            ]
            for name, items in splits.items()
        },
    }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2)

    print(f'Saved composition splits to {OUTPUT_PATH}')
    for split_name, summary in payload['summary'].items():
        print(
            f"{split_name}: {summary['compositions']} compositions, "
            f"{summary['performances']} performances"
        )


if __name__ == '__main__':
    main()
