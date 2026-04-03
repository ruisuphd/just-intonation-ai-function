#!/usr/bin/env python3
"""
Build the hybrid known-piece identification assets for ATEPP_JI_Dataset.

Outputs:
- exact fingerprint database
- coarse retrieval index
- score mapping
"""

from __future__ import annotations

import csv
import os
import pickle

from tqdm import tqdm

from hybrid_piece_identifier import HybridPieceIdentifier


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(BASE_DIR, 'ATEPP_JI_Dataset')
ATEPP_DATA_PATH = os.path.join(DATASET_PATH, 'ATEPP-1.2')
METADATA_PATH = os.path.join(DATASET_PATH, 'ATEPP-metadata-JI.csv')

OUTPUT_FINGERPRINT_DB = os.path.join(BASE_DIR, 'atepp_hybrid_fingerprint_database.pkl')
OUTPUT_COARSE_INDEX = os.path.join(BASE_DIR, 'atepp_hybrid_coarse_index.pkl')
OUTPUT_SCORE_MAPPING = os.path.join(BASE_DIR, 'atepp_hybrid_score_mapping.pkl')


def main() -> None:
    if not os.path.exists(METADATA_PATH):
        raise FileNotFoundError(f'Metadata not found: {METADATA_PATH}')

    valid_entries = []

    with open(METADATA_PATH, 'r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))

    for row in tqdm(rows, total=len(rows), desc='Verifying files'):
        midi_path = os.path.join(ATEPP_DATA_PATH, row['midi_path'])
        score_path = os.path.join(ATEPP_DATA_PATH, row['score_path'])
        if os.path.exists(midi_path) and os.path.exists(score_path):
            valid_entries.append(
                {
                    'midi_path': midi_path,
                    'score_path': score_path,
                    'composer': row['composer'],
                    'track': row['track'],
                    'midi_filename': os.path.basename(midi_path),
                }
            )

    metadata_map = {}
    score_mapping = {}
    midi_files = []

    for entry in valid_entries:
        display_name = f"{entry['composer']}: {entry['track']}"
        metadata_map[entry['midi_filename']] = display_name
        score_mapping[entry['midi_filename']] = {
            'score_path': entry['score_path'],
            'composer': entry['composer'],
            'track': entry['track'],
        }
        midi_files.append(entry['midi_path'])

    identifier = HybridPieceIdentifier()
    identifier.build_indices(midi_files, metadata_map)
    identifier.fingerprinter.save_database(OUTPUT_FINGERPRINT_DB)
    identifier.coarse_retriever.save(OUTPUT_COARSE_INDEX)

    with open(OUTPUT_SCORE_MAPPING, 'wb') as handle:
        pickle.dump(score_mapping, handle)

    print(f'Saved exact fingerprint database to {OUTPUT_FINGERPRINT_DB}')
    print(f'Saved coarse retrieval index to {OUTPUT_COARSE_INDEX}')
    print(f'Saved score mapping to {OUTPUT_SCORE_MAPPING}')


if __name__ == '__main__':
    main()
