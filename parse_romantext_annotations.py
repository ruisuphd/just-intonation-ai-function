#!/usr/bin/env python3
"""
When-in-Rome RomanText -> JSON Key Label Parser

Parses Roman numeral annotations from the When-in-Rome meta-corpus
(Gotham et al., TISMIR 2023) into JSON format compatible with the
training pipeline.

RomanText format uses case convention for mode:
  - Uppercase key letter = major (e.g., 'C:', 'Ab:')
  - Lowercase key letter = minor (e.g., 'c:', 'f#:')

References:
  Gotham, M., et al. (2023). When in Rome: A Meta-Corpus of Functional
  Harmony. TISMIR.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants: 24-class key mapping (0-11 major, 12-23 minor)
# ---------------------------------------------------------------------------
# Chromatic pitch classes for key roots.
# Enharmonic equivalents collapse to the same class.
_MAJOR_KEY_MAP: Dict[str, int] = {
    "C":  0,  "B#": 0,
    "Db": 1,  "C#": 1,
    "D":  2,
    "Eb": 3,  "D#": 3,
    "E":  4,  "Fb": 4,
    "F":  5,  "E#": 5,
    "F#": 6,  "Gb": 6,
    "G":  7,
    "Ab": 8,  "G#": 8,
    "A":  9,
    "Bb": 10, "A#": 10,
    "B":  11, "Cb": 11,
}

_MINOR_KEY_MAP: Dict[str, int] = {
    k.lower(): v + 12 for k, v in _MAJOR_KEY_MAP.items()
}

# Reverse lookup for class -> canonical name (used in summaries)
_CLASS_TO_NAME: Dict[int, str] = {
    0: "C",   1: "Db",  2: "D",   3: "Eb",  4: "E",   5: "F",
    6: "F#",  7: "G",   8: "Ab",  9: "A",  10: "Bb", 11: "B",
    12: "c",  13: "c#", 14: "d",  15: "eb", 16: "e",  17: "f",
    18: "f#", 19: "g",  20: "ab", 21: "a",  22: "bb", 23: "b",
}

# ---------------------------------------------------------------------------
# Regex patterns for RomanText parsing
# ---------------------------------------------------------------------------
# Match measure markers: m1, m0, m123, m56a, m56b, m20var1
_RE_MEASURE = re.compile(
    r"^m(\d+)([a-z](?:var\d+)?|var\d+)?\s*(.*)"
)

# Match beat markers: b1, b2.5, b3.33, b1.66
_RE_BEAT = re.compile(r"b(\d+(?:\.\d+)?)")

# Match key declarations: C:, Ab:, f#:, bb:, Db:, etc.
# Key letter may be upper or lower, optionally followed by # or b
_RE_KEY_DECL = re.compile(r"^([A-Ga-g][#b]?):\s*(.*)")

# Match repeat/copy directives: m5-6 = m3-4
_RE_REPEAT = re.compile(
    r"^m(\d+)-(\d+)\s*=\s*m(\d+)-(\d+)$"
)

# Match single-measure repeat: m101-107 = m1-7 (range copy)
# Already handled by _RE_REPEAT above

# Metadata header lines (not measure data)
_HEADER_PREFIXES = (
    "Composer:", "Title:", "Analyst:", "Proofreader:", "Proof-reader:",
    "Note:", "Time Signature:", "Time signature:", "Key Signature:",
    "Key signature:", "Form:", "Pedal:", "Madrigal:",
)

# Roman numeral tokens -- anything that looks like a chord symbol.
# This is intentionally broad; we capture the raw token and trust the
# corpus to be syntactically correct (validated by romanUmpire).
_RE_ROMAN = re.compile(
    r"((?:[#b]*)(?:VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i|"
    r"Cad64|It6|Fr[0-9]*|Ger[0-9]*|N[0-9]*)(?:[+o]|ø)?(?:\d+(?:/\d+)*)?(?:\[[^\]]*\])*(?:/[A-Ga-g#b]*(?:VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i))?)"
)

# Pattern to detect whether a token is a roman numeral (vs. metadata)
_RE_IS_ROMAN_TOKEN = re.compile(
    r"^[#b]*(?:VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i|Cad64|It6|Fr|Ger|N)"
)


# ===========================================================================
# Key Conversion
# ===========================================================================

def romantext_key_to_24class(key_str: str) -> int:
    """Convert a RomanText key string to a 0-23 key class.

    Convention (same as DCML pipeline):
      - Uppercase first letter = major: C=0, Db=1, ... B=11
      - Lowercase first letter = minor: c=12, c#=13, ... b=23

    Parameters
    ----------
    key_str : str
        Key string such as 'C', 'Ab', 'f#', 'bb'. Must not include
        the trailing colon.

    Returns
    -------
    int
        Key class in [0, 23].

    Raises
    ------
    ValueError
        If the key string is not recognized.
    """
    key_str = key_str.strip()
    if not key_str:
        raise ValueError("Empty key string")

    first_char = key_str[0]
    if first_char.isupper():
        # Major key
        lookup = key_str[0].upper() + key_str[1:]
        if lookup in _MAJOR_KEY_MAP:
            return _MAJOR_KEY_MAP[lookup]
        raise ValueError(f"Unrecognized major key: {key_str!r}")
    else:
        # Minor key
        lookup = key_str.lower()
        if lookup in _MINOR_KEY_MAP:
            return _MINOR_KEY_MAP[lookup]
        raise ValueError(f"Unrecognized minor key: {key_str!r}")


def key_class_to_name(key_class: int) -> str:
    """Return canonical key name for a 0-23 class."""
    return _CLASS_TO_NAME.get(key_class, f"?{key_class}")


def is_minor_key(key_class: int) -> bool:
    """Return True if key_class represents a minor key (12-23)."""
    return key_class >= 12


# ===========================================================================
# RomanText Line Parser
# ===========================================================================

def _parse_measure_line(
    line: str,
    current_key: Optional[str],
    current_key_class: Optional[int],
) -> Tuple[int, Optional[str], List[Dict[str, Any]], Optional[str], Optional[int]]:
    """Parse a single measure line from a RomanText file.

    Returns
    -------
    (measure_num, variant_tag, annotations, new_key, new_key_class)
        - measure_num: integer measure number
        - variant_tag: e.g. 'a', 'b', 'var1', or None
        - annotations: list of annotation dicts
        - new_key: updated key string (or current_key if unchanged)
        - new_key_class: updated key class (or current_key_class)
    """
    m = _RE_MEASURE.match(line)
    if not m:
        return -1, None, [], current_key, current_key_class

    measure_num = int(m.group(1))
    variant_tag = m.group(2)  # None, 'a', 'b', 'var1'
    remainder = m.group(3).strip()

    # Remove trailing || (phrase boundary / pivot marker) and ||: / :||
    # These are structural markers, not harmonic content to skip entirely.
    remainder = remainder.replace("||:", "").replace(":||", "")
    remainder = remainder.replace("||", "")
    remainder = remainder.strip()

    if not remainder:
        return measure_num, variant_tag, [], current_key, current_key_class

    annotations = []
    active_key = current_key
    active_key_class = current_key_class
    current_beat = 1.0

    # Tokenize the remainder by whitespace
    tokens = remainder.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]

        # Skip empty tokens
        if not token:
            i += 1
            continue

        # Beat marker
        beat_match = _RE_BEAT.match(token)
        if beat_match:
            current_beat = float(beat_match.group(1))
            i += 1
            continue

        # Key declaration: token ends with colon or is "X:" form
        key_match = _RE_KEY_DECL.match(token)
        if key_match:
            key_part = key_match.group(1)
            after_colon = key_match.group(2).strip()
            try:
                active_key = key_part
                active_key_class = romantext_key_to_24class(key_part)
            except ValueError:
                logger.warning(
                    "Skipping unrecognized key %r in measure %d",
                    key_part, measure_num
                )
                i += 1
                continue

            # If there's a roman numeral glued after the colon
            if after_colon and _RE_IS_ROMAN_TOKEN.match(after_colon):
                annotations.append({
                    "measure": measure_num,
                    "beat": current_beat,
                    "key": active_key,
                    "key_class": active_key_class,
                    "numeral": after_colon,
                })
            i += 1
            continue

        # Check if the token itself is "KEY: NUMERAL" split across tokens
        # e.g. "C:" followed by "I"
        if token.endswith(":") and len(token) >= 2:
            key_candidate = token[:-1]
            try:
                active_key = key_candidate
                active_key_class = romantext_key_to_24class(key_candidate)
            except ValueError:
                # Not a key declaration; might be something else
                i += 1
                continue
            # Next token should be the roman numeral
            if i + 1 < len(tokens) and _RE_IS_ROMAN_TOKEN.match(tokens[i + 1]):
                i += 1
                annotations.append({
                    "measure": measure_num,
                    "beat": current_beat,
                    "key": active_key,
                    "key_class": active_key_class,
                    "numeral": tokens[i],
                })
            i += 1
            continue

        # Roman numeral token
        if _RE_IS_ROMAN_TOKEN.match(token):
            if active_key is not None:
                annotations.append({
                    "measure": measure_num,
                    "beat": current_beat,
                    "key": active_key,
                    "key_class": active_key_class,
                    "numeral": token,
                })
            else:
                logger.debug(
                    "Roman numeral %r at m%d before any key declaration",
                    token, measure_num
                )
            i += 1
            continue

        # Unknown token -- skip silently (e.g. 'rest', stray text)
        i += 1

    return measure_num, variant_tag, annotations, active_key, active_key_class


# ===========================================================================
# File Parser
# ===========================================================================

def parse_romantext_file(txt_path: str) -> Dict[str, Any]:
    """Parse a RomanText analysis file into a structured dict.

    Parameters
    ----------
    txt_path : str
        Path to an analysis.txt file in RomanText format.

    Returns
    -------
    dict
        Parsed representation with keys: metadata, global_key,
        global_key_class, annotations, key_regions.
    """
    txt_path = str(txt_path)
    metadata: Dict[str, str] = {}
    all_annotations: List[Dict[str, Any]] = []
    repeat_directives: List[Tuple[int, int, int, int]] = []  # dst_start, dst_end, src_start, src_end

    current_key: Optional[str] = None
    current_key_class: Optional[int] = None
    global_key: Optional[str] = None
    global_key_class: Optional[int] = None

    # Map measure_num -> list of annotations (for repeat resolution)
    measure_annotations: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    # Track the key state at the START of each measure (for repeat key propagation)
    measure_entry_key: Dict[int, Tuple[Optional[str], Optional[int]]] = {}
    # Track the key state at the END of each measure
    measure_exit_key: Dict[int, Tuple[Optional[str], Optional[int]]] = {}

    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError) as exc:
        logger.error("Cannot read %s: %s", txt_path, exc)
        return {
            "metadata": {},
            "global_key": None,
            "global_key_class": None,
            "annotations": [],
            "key_regions": [],
            "parse_errors": [str(exc)],
        }

    for line_num, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip comment lines (sometimes % is used)
        if line.startswith("%"):
            continue

        # Extract metadata headers
        is_header = False
        for prefix in _HEADER_PREFIXES:
            if line.startswith(prefix):
                key_name = prefix.rstrip(":").strip()
                value = line[len(prefix):].strip()
                # Store first occurrence only for each header
                if key_name not in metadata:
                    metadata[key_name] = value
                is_header = True
                break

        if is_header:
            continue

        # Check for repeat directive: m33-40 = m1-8
        rep_match = _RE_REPEAT.match(line)
        if rep_match:
            dst_start = int(rep_match.group(1))
            dst_end = int(rep_match.group(2))
            src_start = int(rep_match.group(3))
            src_end = int(rep_match.group(4))
            repeat_directives.append((dst_start, dst_end, src_start, src_end))
            continue

        # Check for measure line
        if not line.startswith("m") or not (len(line) > 1 and line[1].isdigit()):
            # Not a measure line; skip (could be unrecognized metadata)
            continue

        # Record key state entering this measure
        measure_match = _RE_MEASURE.match(line)
        if not measure_match:
            continue

        m_num = int(measure_match.group(1))
        variant = measure_match.group(2)

        # Skip variant lines (m20var1, m56a second pass, etc.)
        # We take only the primary reading
        if variant and ("var" in variant):
            continue

        measure_entry_key[m_num] = (current_key, current_key_class)

        parsed_num, parsed_var, anns, new_key, new_key_class = _parse_measure_line(
            line, current_key, current_key_class
        )

        if parsed_num < 0:
            continue

        # Capture the global key from the very first key declaration
        if global_key is None and new_key is not None:
            global_key = new_key
            global_key_class = new_key_class

        current_key = new_key
        current_key_class = new_key_class

        measure_exit_key[m_num] = (current_key, current_key_class)

        # For split measures (m56a, m56b), use the base measure number
        effective_measure = parsed_num

        for ann in anns:
            ann["measure"] = effective_measure
            all_annotations.append(ann)
            measure_annotations[effective_measure].append(ann)

    # -----------------------------------------------------------------------
    # Resolve repeat directives
    # -----------------------------------------------------------------------
    for dst_start, dst_end, src_start, src_end in repeat_directives:
        src_span = src_end - src_start
        dst_span = dst_end - dst_start
        if src_span != dst_span:
            logger.warning(
                "Repeat span mismatch in %s: m%d-%d = m%d-%d",
                txt_path, dst_start, dst_end, src_start, src_end
            )
            continue

        # Get the key state at the entry of the destination range.
        # Look for the latest known key before dst_start.
        dest_entry_key = None
        dest_entry_class = None
        if dst_start in measure_entry_key:
            dest_entry_key, dest_entry_class = measure_entry_key[dst_start]
        else:
            # Fallback: use the exit key of the measure just before
            for prev in range(dst_start - 1, -1, -1):
                if prev in measure_exit_key:
                    dest_entry_key, dest_entry_class = measure_exit_key[prev]
                    break

        for offset in range(src_span + 1):
            src_m = src_start + offset
            dst_m = dst_start + offset
            if src_m in measure_annotations:
                for src_ann in measure_annotations[src_m]:
                    new_ann = dict(src_ann)
                    new_ann["measure"] = dst_m
                    all_annotations.append(new_ann)
                    measure_annotations[dst_m].append(new_ann)
                # Propagate the exit key from source to destination
                if src_m in measure_exit_key:
                    measure_exit_key[dst_m] = measure_exit_key[src_m]

    # Sort annotations by (measure, beat)
    all_annotations.sort(key=lambda a: (a["measure"], a["beat"]))

    # -----------------------------------------------------------------------
    # Build key regions (contiguous spans with the same key)
    # -----------------------------------------------------------------------
    key_regions: List[Dict[str, Any]] = []
    if all_annotations:
        region_key = all_annotations[0].get("key")
        region_class = all_annotations[0].get("key_class")
        region_start = all_annotations[0]["measure"]

        for ann in all_annotations[1:]:
            if ann.get("key_class") != region_class:
                key_regions.append({
                    "start_measure": region_start,
                    "end_measure": ann["measure"] - 1,
                    "key": region_key,
                    "key_class": region_class,
                })
                region_key = ann.get("key")
                region_class = ann.get("key_class")
                region_start = ann["measure"]

        # Close final region using last annotation's measure
        key_regions.append({
            "start_measure": region_start,
            "end_measure": all_annotations[-1]["measure"],
            "key": region_key,
            "key_class": region_class,
        })

    return {
        "metadata": metadata,
        "global_key": global_key,
        "global_key_class": global_key_class,
        "annotations": all_annotations,
        "key_regions": key_regions,
    }


# ===========================================================================
# Piece ID Generation
# ===========================================================================

def _generate_piece_id(rel_path: str) -> str:
    """Generate a compact piece ID from a relative file path.

    Example:
        'Corpus/Piano_Sonatas/Beethoven,_Ludwig_van/Op002_No1/1/analysis.txt'
        -> 'beethoven_op002no1_1'
    """
    parts = Path(rel_path).parts

    # Remove 'Corpus' prefix and 'analysis.txt' suffix
    parts = [p for p in parts if p not in ("Corpus", "analysis.txt")]

    if len(parts) < 2:
        return "_".join(parts).lower().replace(",", "").replace(" ", "_")

    # Category is parts[0] (e.g., 'Piano_Sonatas')
    # Composer is parts[1] (e.g., 'Beethoven,_Ludwig_van')
    # Rest is piece identifier
    composer_raw = parts[1] if len(parts) > 1 else ""
    # Extract surname (before comma)
    surname = composer_raw.split(",")[0].strip().replace("_", "").lower()

    # Remaining path elements form the piece identifier
    piece_parts = parts[2:]
    piece_str = "_".join(piece_parts).lower()

    # Clean up the piece string
    piece_str = re.sub(r"[,\s]+", "_", piece_str)
    piece_str = re.sub(r"_+", "_", piece_str)
    piece_str = piece_str.strip("_")

    piece_id = f"{surname}_{piece_str}" if surname else piece_str

    # Remove analysis.txt if still present
    piece_id = piece_id.replace("analysis.txt", "").strip("_")

    return piece_id


# ===========================================================================
# Corpus Export
# ===========================================================================

def export_wir_labels(
    repo_dir: str,
    output_dir: str,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Walk the When-in-Rome Corpus directory, parse all analysis.txt files,
    and export JSON key labels.

    Parameters
    ----------
    repo_dir : str
        Root of the cloned When-in-Rome repository.
    output_dir : str
        Directory for JSON output files.
    verbose : bool
        If True, log per-file details.

    Returns
    -------
    dict
        Aggregate statistics.
    """
    repo_path = Path(repo_dir)
    corpus_dir = repo_path / "Corpus"
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not corpus_dir.is_dir():
        logger.error("Corpus directory not found: %s", corpus_dir)
        return {"error": f"Corpus directory not found: {corpus_dir}"}

    # Collect all analysis.txt files (primary readings only)
    analysis_files = sorted(corpus_dir.rglob("analysis.txt"))
    logger.info("Found %d analysis.txt files in %s", len(analysis_files), corpus_dir)

    # Aggregate statistics
    stats = {
        "total_files": len(analysis_files),
        "successfully_parsed": 0,
        "parse_failures": 0,
        "total_annotations": 0,
        "total_key_regions": 0,
        "major_annotations": 0,
        "minor_annotations": 0,
        "key_distribution": Counter(),
        "corpus_distribution": Counter(),
        "pieces_by_key_class": Counter(),
        "failed_files": [],
    }

    for analysis_file in analysis_files:
        rel_path = str(analysis_file.relative_to(repo_path))
        piece_id = _generate_piece_id(rel_path)

        # Determine corpus category
        rel_parts = Path(rel_path).parts
        corpus_category = rel_parts[1] if len(rel_parts) > 1 else "unknown"

        if verbose:
            logger.info("Parsing: %s", rel_path)

        parsed = parse_romantext_file(str(analysis_file))

        if parsed.get("parse_errors"):
            stats["parse_failures"] += 1
            stats["failed_files"].append(rel_path)
            continue

        annotations = parsed["annotations"]
        if not annotations:
            # File parsed but had no annotations (possibly metadata-only)
            stats["parse_failures"] += 1
            stats["failed_files"].append(rel_path)
            continue

        stats["successfully_parsed"] += 1
        stats["total_annotations"] += len(annotations)
        stats["total_key_regions"] += len(parsed["key_regions"])
        stats["corpus_distribution"][corpus_category] += 1

        # Count major/minor annotations
        n_major = sum(1 for a in annotations if a.get("key_class") is not None and a["key_class"] < 12)
        n_minor = sum(1 for a in annotations if a.get("key_class") is not None and a["key_class"] >= 12)
        stats["major_annotations"] += n_major
        stats["minor_annotations"] += n_minor

        # Track key distribution
        for ann in annotations:
            kc = ann.get("key_class")
            if kc is not None:
                stats["key_distribution"][kc] += 1

        # Track piece-level global key
        gkc = parsed.get("global_key_class")
        if gkc is not None:
            stats["pieces_by_key_class"][gkc] += 1

        # Compute per-file statistics
        unique_keys = set()
        for ann in annotations:
            kc = ann.get("key_class")
            if kc is not None:
                unique_keys.add(kc)

        file_stats = {
            "total_annotations": len(annotations),
            "unique_keys": len(unique_keys),
            "major_annotations": n_major,
            "minor_annotations": n_minor,
        }

        # Build output JSON
        output_record = {
            "source": "when_in_rome",
            "file_path": rel_path,
            "piece_id": piece_id,
            "global_key": parsed["global_key"],
            "global_key_class": parsed["global_key_class"],
            "annotations": annotations,
            "key_regions": parsed["key_regions"],
            "statistics": file_stats,
        }

        # Write JSON file
        out_file = out_path / f"{piece_id}.json"

        # Handle collisions (rare but possible)
        if out_file.exists():
            counter = 2
            while out_file.exists():
                out_file = out_path / f"{piece_id}_{counter}.json"
                counter += 1

        with open(out_file, "w", encoding="utf-8") as fout:
            json.dump(output_record, fout, indent=2, ensure_ascii=False)

    # Convert Counter objects to dicts for JSON serialization
    stats["key_distribution"] = dict(stats["key_distribution"])
    stats["corpus_distribution"] = dict(stats["corpus_distribution"])
    stats["pieces_by_key_class"] = dict(stats["pieces_by_key_class"])

    # Write aggregate statistics
    stats_file = out_path / "_corpus_statistics.json"
    with open(stats_file, "w", encoding="utf-8") as fout:
        json.dump(stats, fout, indent=2, ensure_ascii=False)

    return stats


# ===========================================================================
# Statistics Display
# ===========================================================================

def print_statistics(stats: Dict[str, Any]) -> None:
    """Print formatted corpus statistics to stdout."""
    print("\n" + "=" * 72)
    print("  When-in-Rome RomanText Corpus -- Parse Statistics")
    print("=" * 72)

    print(f"\n  Total analysis files found:     {stats['total_files']}")
    print(f"  Successfully parsed:            {stats['successfully_parsed']}")
    print(f"  Parse failures / empty:         {stats['parse_failures']}")
    print(f"  Total annotations extracted:    {stats['total_annotations']}")
    print(f"  Total key regions identified:   {stats['total_key_regions']}")

    print(f"\n  --- Annotation Mode Distribution ---")
    total = stats["major_annotations"] + stats["minor_annotations"]
    if total > 0:
        maj_pct = 100.0 * stats["major_annotations"] / total
        min_pct = 100.0 * stats["minor_annotations"] / total
        print(f"  Major-key annotations:          {stats['major_annotations']:>8}  ({maj_pct:.1f}%)")
        print(f"  Minor-key annotations:          {stats['minor_annotations']:>8}  ({min_pct:.1f}%)")
    else:
        print("  (no annotations)")

    print(f"\n  --- Corpus Category Distribution ---")
    for cat, count in sorted(
        stats["corpus_distribution"].items(), key=lambda x: -x[1]
    ):
        print(f"    {cat:<30s}  {count:>5}")

    print(f"\n  --- Global Key Distribution (pieces) ---")
    pk = stats.get("pieces_by_key_class", {})
    if pk:
        # Group by major/minor
        major_pieces = {k: v for k, v in pk.items() if int(k) < 12}
        minor_pieces = {k: v for k, v in pk.items() if int(k) >= 12}

        if major_pieces:
            print("    Major keys:")
            for kc, count in sorted(major_pieces.items(), key=lambda x: -x[1]):
                name = key_class_to_name(int(kc))
                print(f"      {name:<6s}  {count:>5}")

        if minor_pieces:
            print("    Minor keys:")
            for kc, count in sorted(minor_pieces.items(), key=lambda x: -x[1]):
                name = key_class_to_name(int(kc))
                print(f"      {name:<6s}  {count:>5}")

    if stats.get("failed_files"):
        print(f"\n  --- Failed Files ({len(stats['failed_files'])}) ---")
        for fp in stats["failed_files"][:20]:
            print(f"    {fp}")
        if len(stats["failed_files"]) > 20:
            print(f"    ... and {len(stats['failed_files']) - 20} more")

    print("\n" + "=" * 72)


# ===========================================================================
# CLI
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse When-in-Rome RomanText annotations to JSON key labels.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--repo-dir",
        type=str,
        required=True,
        help="Path to the cloned When-in-Rome repository root.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Output directory for JSON key label files.",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        default=False,
        help="Print detailed statistics after parsing.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose per-file logging.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO).",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("Repo dir:   %s", args.repo_dir)
    logger.info("Output dir: %s", args.output_dir)

    stats = export_wir_labels(
        repo_dir=args.repo_dir,
        output_dir=args.output_dir,
        verbose=args.verbose,
    )

    if args.stats or True:  # Always print stats for CLI usage
        print_statistics(stats)


if __name__ == "__main__":
    main()
