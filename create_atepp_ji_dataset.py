#!/usr/bin/env python3
"""
Creates ATEPP_JI_Dataset - a filtered version of ATEPP containing only pieces
that have MusicXML scores. This is useful for predictive tuning research where
you need guaranteed score availability.
"""

import os
import sys
import shutil
import pandas as pd
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

# Change these paths to match your setup
SOURCE_ATEPP = Path('/Users/ruisu/Desktop/phd/JustIntonation/THESIS/LR/Code/ATEPP-1.2')
SOURCE_METADATA = SOURCE_ATEPP / 'ATEPP-metadata-1.2.csv'
TARGET_DIR = Path('/Users/ruisu/Desktop/phd/JustIntonation/THESIS/LR/Code/ATEPP_JI_Dataset')
TARGET_DATA = TARGET_DIR / 'ATEPP-1.2'

print("Creating filtered ATEPP dataset (MusicXML scores only)\n")

print("Loading ATEPP metadata...")
df = pd.read_csv(SOURCE_METADATA)

total_entries = len(df)
entries_with_scores = df['score_path'].notna().sum()

print(f"Total entries: {total_entries:,}")
print(f"With MusicXML: {entries_with_scores:,} ({entries_with_scores/total_entries*100:.1f}%)\n")

df_filtered = df[df['score_path'].notna()].copy()
print(f"Filtered to {len(df_filtered):,} entries\n")

print("Verifying source files...")
files_to_copy = []  # (source, dest) tuples
missing_files = []
valid_entries = []

for idx, row in tqdm(df_filtered.iterrows(), total=len(df_filtered), desc="  Verifying"):
    midi_rel = row['midi_path']
    score_rel = row['score_path']
    
    # Source paths (relative paths are under ATEPP-1.2/)
    midi_source = SOURCE_ATEPP / 'ATEPP-1.2' / midi_rel
    score_source = SOURCE_ATEPP / 'ATEPP-1.2' / score_rel
    
    # Check if both files exist
    midi_exists = midi_source.exists()
    score_exists = score_source.exists()
    
    if midi_exists and score_exists:
        # Destination paths (maintain same relative structure)
        midi_dest = TARGET_DATA / midi_rel
        score_dest = TARGET_DATA / score_rel
        
        files_to_copy.append((midi_source, midi_dest))
        files_to_copy.append((score_source, score_dest))
        valid_entries.append(idx)
    else:
        missing = []
        if not midi_exists:
            missing.append(f"MIDI: {midi_rel}")
        if not score_exists:
            missing.append(f"Score: {score_rel}")
        missing_files.extend(missing)

print(f"Valid: {len(valid_entries):,}")
if missing_files:
    print(f"Missing: {len(missing_files)}")

# Dedupe (same score can be used by multiple performances)
unique_files = {}
for src, dest in files_to_copy:
    if str(dest) not in unique_files:
        unique_files[str(dest)] = (src, dest)
files_to_copy = list(unique_files.values())

print(f"Unique files to copy: {len(files_to_copy):,}\n")

print("Copying files...")

TARGET_DIR.mkdir(parents=True, exist_ok=True)

copied_count = 0
for src, dest in tqdm(files_to_copy, desc="Copying"):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(src, dest)
        copied_count += 1
    elif src.stat().st_size != dest.stat().st_size:
        shutil.copy2(src, dest)
        copied_count += 1

print(f"Copied {copied_count:,} files\n")

print("Creating metadata CSV...")

df_ji = df.loc[valid_entries].copy()

metadata_path = TARGET_DIR / 'ATEPP-metadata-JI.csv'
df_ji.to_csv(metadata_path, index=False)
print(f"Saved: {metadata_path}\n")

composer_counts = df_ji['composer'].value_counts()
unique_compositions = df_ji['composition_id'].nunique()
unique_scores = df_ji['score_path'].nunique()

print("Creating README...")

readme_content = f"""# ATEPP_JI_Dataset
## Filtered Dataset for Just Intonation Research

**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Purpose:** Real-time predictive Just Intonation tuning system

---

## Dataset Overview

This is a filtered subset of the ATEPP (Aligned Transcriptions of Expressive Piano Performance) dataset,
containing only entries that have MusicXML score files available. This ensures 100% score-following
coverage for the predictive JI tuning system.

| Metric | Value |
|--------|-------|
| Total MIDI performances | {len(df_ji):,} |
| Unique compositions | {unique_compositions:,} |
| Unique MusicXML scores | {unique_scores:,} |
| Composers | {len(composer_counts):,} |

## Coverage vs Full ATEPP

| Dataset | Entries | Coverage |
|---------|---------|----------|
| Full ATEPP | {total_entries:,} | 100% |
| ATEPP_JI_Dataset | {len(df_ji):,} | {len(df_ji)/total_entries*100:.1f}% |

## Composer Distribution

| Composer | Performances |
|----------|--------------|
"""

for composer, count in composer_counts.head(15).items():
    readme_content += f"| {composer} | {count:,} |\n"

if len(composer_counts) > 15:
    readme_content += f"| ... and {len(composer_counts) - 15} more | ... |\n"

readme_content += f"""
## Directory Structure

```
ATEPP_JI_Dataset/
├── ATEPP-1.2/
│   ├── Ludwig_van_Beethoven/
│   │   ├── Piano_Sonata_No._8_in_C_Minor,_Op._13_"Pathétique"/
│   │   │   ├── I._Grave_-_Allegro_di_molto_e_con_brio/
│   │   │   │   ├── musicxml_cleaned.musicxml  (score)
│   │   │   │   ├── 00001.mid  (performance 1)
│   │   │   │   ├── 00002.mid  (performance 2)
│   │   │   │   └── ...
│   │   │   └── ...
│   │   └── ...
│   ├── Johann_Sebastian_Bach/
│   │   └── ...
│   └── ...
├── ATEPP-metadata-JI.csv  (filtered metadata)
└── README.md  (this file)
```

## File Formats

- **MIDI files**: `.mid` or `.midi` - Piano performance transcriptions
- **MusicXML files**: `.musicxml` or `.mxl` - Score files with key signatures

## Usage

### Loading the dataset:

```python
import pandas as pd
from pathlib import Path

# Load metadata
DATASET_PATH = Path('/Users/ruisu/Desktop/phd/JustIntonation/THESIS/LR/Code/ATEPP_JI_Dataset')
df = pd.read_csv(DATASET_PATH / 'ATEPP-metadata-JI.csv')

# Get file paths
for idx, row in df.iterrows():
    midi_path = DATASET_PATH / 'ATEPP-1.2' / row['midi_path']
    score_path = DATASET_PATH / 'ATEPP-1.2' / row['score_path']
    print(f"MIDI: {{midi_path}}")
    print(f"Score: {{score_path}}")
```

### Building fingerprint database:

```bash
cd prototype081225_datasets_test
python create_filtered_database.py --atepp-path ../ATEPP_JI_Dataset
```

## Metadata Columns

| Column | Description |
|--------|-------------|
| artist | Performer name |
| artist_id | Unique performer identifier |
| track | Piece/movement name |
| track_duration | Duration in seconds |
| composer | Composer name |
| composition_id | Unique composition identifier |
| score_path | Relative path to MusicXML file |
| midi_path | Relative path to MIDI file |
| youtube_links | Source YouTube URL |
| quality | Recording quality notes |
| perf_id | Unique performance identifier |
| album | Source album |
| album_date | Album release date |
| repetition | Repeat marking (if any) |

## Source

Original dataset: ATEPP 1.2
Reference: Zhang, D., Su, Y., & Gómez, E. (2022). ATEPP: A Dataset of Aligned 
Transcriptions of Expressive Piano Performance. ISMIR 2022.

---

*This filtered dataset was created for PhD research on real-time Just Intonation tuning.*
"""

readme_path = TARGET_DIR / 'README.md'
with open(readme_path, 'w') as f:
    f.write(readme_content)

print(f"Saved: {readme_path}")

# Summary
print(f"\nDone! Dataset created at {TARGET_DIR}")
print(f"  {len(files_to_copy):,} files")
print(f"  {len(df_ji):,} MIDI performances")
print(f"  {unique_compositions:,} unique compositions")
print(f"  {unique_scores:,} MusicXML scores")
print(f"\nTop composers:")
for composer, count in composer_counts.head(5).items():
    print(f"  {composer}: {count:,}")

