#!/usr/bin/env python3
"""
Builds the fingerprint database from the full ATEPP dataset.
Run this if you have the complete ATEPP-1.2 collection.
"""

import os
import sys
import pandas as pd

sys.path.insert(0, 'MIDI-Zero-main')
from simple_ngram_fingerprinting import SimpleNGramFingerprinter, get_midi_files

print("Building ATEPP fingerprint database...\n")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ATEPP_PATH = os.path.join(BASE_DIR, 'ATEPP-1.2', 'ATEPP-1.2')
METADATA_PATH = os.path.join(BASE_DIR, 'ATEPP-1.2', 'ATEPP-metadata-1.2.csv')
OUTPUT_DB = "atepp_fingerprint_database.pkl"

print(f"ATEPP path: {ATEPP_PATH}")
print(f"Metadata: {METADATA_PATH}")
print(f"Output: {OUTPUT_DB}\n")

# Load MIDI files
print("Loading ATEPP MIDI files...")
midi_files = get_midi_files(ATEPP_PATH)
print(f"Found {len(midi_files)} MIDI files\n")

# Load metadata
print("Loading metadata...")
try:
    df = pd.read_csv(METADATA_PATH)
    metadata_map = {}
    
    for _, row in df.iterrows():
        midi_path = row['midi_path']
        if pd.notna(midi_path):
            filename = os.path.basename(midi_path)
            composer = row.get('composer', '')
            track = row.get('track', '')
            
            if composer and track:
                display_name = f"{composer}: {track}"
            else:
                display_name = filename.replace('.mid', '')
            
            metadata_map[filename] = display_name
    
    print(f"Loaded metadata for {len(metadata_map)} compositions\n")
except Exception as e:
    print(f"Warning: Could not load metadata: {e}")
    metadata_map = {}

# Build fingerprint database (this takes a while)
print("Building fingerprint database...")
print("This takes about 10-15 minutes...\n")

fingerprinter = SimpleNGramFingerprinter(n=4)
fingerprinter.build_database(midi_files, metadata_map)


# Save it
print("\nSaving database...")
fingerprinter.save_database(OUTPUT_DB)

# Done
num_pieces = len(set(piece for fp_dict in fingerprinter.database.values() for piece in fp_dict))
print(f"\nDone! {num_pieces} pieces, {len(fingerprinter.database):,} unique fingerprints")
print(f"Saved to: {OUTPUT_DB}")

