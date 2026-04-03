#!/usr/bin/env python3
"""
Builds fingerprint database for the ATEPP_JI_Dataset (filtered subset with MusicXML scores).
This ensures 100% score coverage for the predictive tuning system.
"""

import os
import pickle
import sys
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, 'MIDI-Zero-main')
from simple_ngram_fingerprinting import SimpleNGramFingerprinter, get_midi_files

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JI_DATASET_PATH = os.path.join(BASE_DIR, '..', 'ATEPP_JI_Dataset')
ATEPP_DATA_PATH = os.path.join(JI_DATASET_PATH, 'ATEPP-1.2')
METADATA_PATH = os.path.join(JI_DATASET_PATH, 'ATEPP-metadata-JI.csv')
OUTPUT_FINGERPRINT_DB = 'atepp_ji_fingerprint_database.pkl'
OUTPUT_SCORE_MAPPING = 'atepp_ji_score_mapping.pkl'


def main():
    print("Building fingerprint database for ATEPP_JI_Dataset\n")
    
    print(f"Dataset: {JI_DATASET_PATH}")
    print(f"Metadata: {METADATA_PATH}\n")

    if not os.path.exists(METADATA_PATH):
        print(f"Error: Metadata not found at {METADATA_PATH}")
        sys.exit(1)

    if not os.path.exists(ATEPP_DATA_PATH):
        print(f"Error: Data directory not found at {ATEPP_DATA_PATH}")
        sys.exit(1)

    # Load metadata
    print("Loading metadata...")
    df = pd.read_csv(METADATA_PATH)
    print(f"Loaded {len(df):,} entries (all have MusicXML scores)\n")

    # Verify files exist
    print("Verifying files...")
    
    valid_entries = []
    missing_files = []
    
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="  Verifying"):
        midi_rel = row['midi_path']
        score_rel = row['score_path']
        
        # Build full paths
        midi_path = os.path.join(ATEPP_DATA_PATH, midi_rel)
        score_path = os.path.join(ATEPP_DATA_PATH, score_rel)
        
        # Verify both files exist
        if os.path.exists(midi_path) and os.path.exists(score_path):
            valid_entries.append({
                'midi_path': midi_path,
                'score_path': score_path,
                'composer': row['composer'],
                'track': row['track'],
                'midi_filename': os.path.basename(midi_path)
            })
        else:
            missing_files.append((midi_rel, score_rel))
    
    print(f"Valid entries: {len(valid_entries):,}")
    if missing_files:
        print(f"Missing files: {len(missing_files)}")
    print()

    # Build metadata mapping
    print("Building display names...")
    
    metadata_map = {}
    for entry in valid_entries:
        filename = entry['midi_filename']
        display_name = f"{entry['composer']}: {entry['track']}"
        metadata_map[filename] = display_name
    
    print(f"Created display names for {len(metadata_map):,} pieces\n")

    # Build fingerprint database
    print("Building fingerprint database (this takes 5-10 min)...\n")
    
    midi_files = [entry['midi_path'] for entry in valid_entries]
    
    fingerprinter = SimpleNGramFingerprinter(n=4)
    fingerprinter.build_database(midi_files, metadata_map)
    
    fingerprinter.save_database(OUTPUT_FINGERPRINT_DB)

    # Build score mapping
    print("\nBuilding score mapping...")
    
    score_mapping = {}
    for entry in valid_entries:
        score_mapping[entry['midi_filename']] = {
            'score_path': entry['score_path'],
            'composer': entry['composer'],
            'track': entry['track']
        }
    
    with open(OUTPUT_SCORE_MAPPING, 'wb') as f:
        pickle.dump(score_mapping, f)
    
    print(f"Saved: {OUTPUT_SCORE_MAPPING}")

    # Done
    print(f"\nDone! {len(valid_entries):,} pieces, {len(fingerprinter.database):,} fingerprints")
    print(f"\nOutput files:")
    print(f"  {OUTPUT_FINGERPRINT_DB}")
    print(f"  {OUTPUT_SCORE_MAPPING}")
    print(f"\nTo start the server:")
    print(f"  python two_stage_server.py --fingerprint-db {OUTPUT_FINGERPRINT_DB} --score-mapping {OUTPUT_SCORE_MAPPING}")


if __name__ == '__main__':
    main()
