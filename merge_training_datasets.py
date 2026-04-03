#!/usr/bin/env python3
"""
Merge ATEPP, DCML, and When-in-Rome key-label datasets into a unified
training set with provenance tracking.

This script produces a single JSON manifest mapping composition IDs to their
label files, data source (ATEPP-heuristic, DCML-expert, WiR-expert), and
split assignment (train/val/test).

Usage:
    python merge_training_datasets.py \
        --atepp-dir research_data/score_key_labels \
        --dcml-dir research_data/dcml_key_labels \
        --wir-dir research_data/wir_key_labels \
        --output research_data/unified_training_manifest.json
"""

from __future__ import annotations

import argparse
import json
import os
import glob
from typing import Dict, List, Optional


def scan_label_dir(
    label_dir: str,
    source_name: str,
) -> List[Dict]:
    """Scan a directory of JSON label files and return metadata for each.

    Parameters
    ----------
    label_dir : str
        Directory containing JSON label files.
    source_name : str
        Provenance tag: "atepp-heuristic", "dcml-expert", or "wir-expert".

    Returns
    -------
    list of dict
        Each dict has: file_path, source, piece_id, note_count, major_notes,
        minor_notes, key_classes (set of ints).
    """
    entries = []
    files = sorted(glob.glob(os.path.join(label_dir, "**", "*.json"), recursive=True))
    for fpath in files:
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        notes = data.get("notes", [])
        annotations = data.get("annotations", data.get("key_regions", []))

        major_count = sum(1 for n in notes if not n.get("is_minor", False))
        minor_count = sum(1 for n in notes if n.get("is_minor", False))

        # Collect unique key classes
        key_classes = set()
        for n in notes:
            tonic_pc = n.get("tonic_pc", 0)
            is_minor = n.get("is_minor", False)
            key_classes.add(tonic_pc + (12 if is_minor else 0))

        # Derive piece_id from filename or data
        piece_id = data.get("composition_id", data.get("piece_id", os.path.splitext(os.path.basename(fpath))[0]))

        entries.append({
            "file_path": os.path.abspath(fpath),
            "source": source_name,
            "piece_id": str(piece_id),
            "composer": data.get("composer", ""),
            "note_count": len(notes),
            "major_notes": major_count,
            "minor_notes": minor_count,
            "key_classes": sorted(key_classes),
            "annotation_count": len(annotations),
        })

    return entries


def assign_splits(
    entries: List[Dict],
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    seed: int = 20260309,
) -> List[Dict]:
    """Assign train/val/test splits stratified by composer.

    Parameters
    ----------
    entries : list of dict
        All dataset entries.
    train_ratio, val_ratio : float
        Split proportions (test = 1 - train - val).
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    list of dict
        Same entries with added "split" field.
    """
    import random
    rng = random.Random(seed)

    # Group by composer
    by_composer: Dict[str, List[Dict]] = {}
    for entry in entries:
        comp = entry.get("composer", "Unknown")
        by_composer.setdefault(comp, []).append(entry)

    # Stratified split within each composer
    for composer, pieces in by_composer.items():
        rng.shuffle(pieces)
        n = len(pieces)
        n_train = max(1, int(n * train_ratio))
        n_val = max(0, int(n * val_ratio))
        for i, piece in enumerate(pieces):
            if i < n_train:
                piece["split"] = "train"
            elif i < n_train + n_val:
                piece["split"] = "val"
            else:
                piece["split"] = "test"

    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge key-label datasets with provenance tracking")
    parser.add_argument("--atepp-dir", default="research_data/score_key_labels",
                        help="ATEPP label directory")
    parser.add_argument("--dcml-dir", default="research_data/dcml_key_labels",
                        help="DCML label directory")
    parser.add_argument("--wir-dir", default="research_data/wir_key_labels",
                        help="When-in-Rome label directory")
    parser.add_argument("--output", default="research_data/unified_training_manifest.json",
                        help="Output manifest path")
    args = parser.parse_args()

    all_entries: List[Dict] = []

    # Scan each source
    for label_dir, source_name in [
        (args.atepp_dir, "atepp-heuristic"),
        (args.dcml_dir, "dcml-expert"),
        (args.wir_dir, "wir-expert"),
    ]:
        if os.path.isdir(label_dir):
            entries = scan_label_dir(label_dir, source_name)
            all_entries.extend(entries)
            print(f"  {source_name}: {len(entries)} pieces")
        else:
            print(f"  {source_name}: directory not found ({label_dir}), skipping")

    if not all_entries:
        print("No datasets found. Exiting.")
        return

    # Assign splits
    all_entries = assign_splits(all_entries)

    # Compute statistics
    total_notes = sum(e["note_count"] for e in all_entries)
    total_major = sum(e["major_notes"] for e in all_entries)
    total_minor = sum(e["minor_notes"] for e in all_entries)
    sources = {}
    splits = {}
    for e in all_entries:
        sources[e["source"]] = sources.get(e["source"], 0) + 1
        splits[e["split"]] = splits.get(e["split"], 0) + 1

    manifest = {
        "generated": "merge_training_datasets.py",
        "statistics": {
            "total_pieces": len(all_entries),
            "total_notes": total_notes,
            "major_notes": total_major,
            "minor_notes": total_minor,
            "major_pct": round(100 * total_major / max(1, total_notes), 1),
            "minor_pct": round(100 * total_minor / max(1, total_notes), 1),
            "by_source": sources,
            "by_split": splits,
        },
        "entries": all_entries,
    }

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nUnified manifest: {len(all_entries)} pieces, {total_notes:,} notes")
    print(f"  Major: {total_major:,} ({manifest['statistics']['major_pct']}%)")
    print(f"  Minor: {total_minor:,} ({manifest['statistics']['minor_pct']}%)")
    print(f"  Sources: {sources}")
    print(f"  Splits: {splits}")
    print(f"  Written to: {args.output}")


if __name__ == "__main__":
    main()
