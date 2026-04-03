#!/usr/bin/env python3
"""
Creates a filtered fingerprint database containing only pieces that have MusicXML scores.
This ensures the score following system always has a score to work with.
"""

import os
import sys
import pickle
import pandas as pd
from tqdm import tqdm
from simple_ngram_fingerprinting import SimpleNGramFingerprinter

print("Creating filtered ATEPP database (pieces with MusicXML scores only)\n")

# Load metadata
print("Loading metadata...")
metadata_path = 'ATEPP_JI_Dataset/ATEPP-metadata-JI.csv'
df = pd.read_csv(metadata_path)

total_tracks = len(df)
with_scores = df['score_path'].notna().sum()

print(f"Total tracks: {total_tracks}")
print(f"With MusicXML: {with_scores} ({with_scores/total_tracks*100:.1f}%)\n")

df_with_scores = df[df['score_path'].notna()].copy()

print("Verifying score files exist...")
valid_entries = []
atepp_base = 'ATEPP_JI_Dataset/ATEPP-1.2'

for idx, row in tqdm(df_with_scores.iterrows(), total=len(df_with_scores), desc="Verifying"):
    # CORRECTED: Both paths are relative and go under ATEPP-1.2/ATEPP-1.2/
    score_path = os.path.join(atepp_base, row['score_path'])
    midi_path = os.path.join(atepp_base, row['midi_path'])
    
    # Check both files exist
    if os.path.exists(score_path) and os.path.exists(midi_path):
        valid_entries.append({
            'midi_path': midi_path,
            'score_path': score_path,
            'composer': row['composer'],
            'track': row['track'],
            'midi_filename': os.path.basename(midi_path)
        })

print(f"Found {len(valid_entries)} valid MIDI + MusicXML pairs\n")

print(f"Building fingerprint database for {len(valid_entries)} pieces...\n")

fingerprinter = SimpleNGramFingerprinter(n=4)

# Create metadata mapping
metadata_map = {}
for entry in valid_entries:
    filename = entry['midi_filename']
    display_name = f"{entry['composer']}: {entry['track']}"
    metadata_map[filename] = display_name

# Get MIDI file paths
midi_files = [entry['midi_path'] for entry in valid_entries]

# Build database
fingerprinter.build_database(midi_files, metadata_map)

output_path = 'atepp_filtered_database.pkl'
fingerprinter.save_database(output_path)

# Save score mapping so the server knows where to find MusicXML files
print("\nSaving score mapping...")

score_mapping = {}
for entry in valid_entries:
    score_mapping[entry['midi_filename']] = {
        'score_path': entry['score_path'],
        'composer': entry['composer'],
        'track': entry['track']
    }

with open('atepp_score_mapping.pkl', 'wb') as f:
    pickle.dump(score_mapping, f)

print(f"Saved score mapping for {len(score_mapping)} pieces")

print(f"\nDone!")
print(f"  {len(valid_entries)} pieces with scores")
print(f"  {len(fingerprinter.database):,} unique fingerprints")
print(f"  Output: {output_path}, atepp_score_mapping.pkl")

