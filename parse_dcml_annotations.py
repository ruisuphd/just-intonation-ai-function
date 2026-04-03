#!/usr/bin/env python3
"""
DCML Corpus TSV -> JSON Key Label Parser

Parses harmonic annotations from the Digital and Cognitive Musicology Lab (DCML)
corpora into the same JSON format used by extract_score_key_labels.py.

DCML annotation standard uses case convention for mode:
  - Uppercase root = major key (e.g., 'C', 'Ab', 'F#')
  - Lowercase root = minor key (e.g., 'c', 'ab', 'f#')

References:
  Hentschel, J., Neuwirth, M., & Rohrmeier, M. (2021). The Annotated Beethoven
  Corpus (ABC). Frontiers in Digital Humanities.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CORPUS_DIR = BASE_DIR / "research_data" / "dcml_corpora"
DEFAULT_OUTPUT_DIR = BASE_DIR / "research_data" / "dcml_key_labels"

# ---------------------------------------------------------------------------
# Pitch-class mappings
# ---------------------------------------------------------------------------

# Semitone offsets for note letters (C-based, mod 12)
_LETTER_TO_SEMITONE: Dict[str, int] = {
    "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11,
}

# Roman numeral -> semitone interval from tonic (major-scale based)
_ROMAN_MAJOR_INTERVALS: Dict[str, int] = {
    "I": 0, "II": 2, "III": 4, "IV": 5, "V": 7, "VI": 9, "VII": 11,
}

# Roman numeral -> semitone interval from tonic (minor-scale based)
_ROMAN_MINOR_INTERVALS: Dict[str, int] = {
    "I": 0, "II": 2, "III": 3, "IV": 5, "V": 7, "VI": 8, "VII": 10,
}


def _accidental_offset(acc_str: str) -> int:
    """Convert an accidental string (e.g., '#', 'b', '##', 'bb') to semitones.

    Parameters
    ----------
    acc_str : str
        Accidental portion of a note/key name.  May contain '#' (sharp) and
        'b' (flat) characters.

    Returns
    -------
    int
        Net semitone offset: +1 per '#', -1 per 'b'.
    """
    return acc_str.count("#") - acc_str.count("b")


def _note_name_to_pc(name: str) -> int:
    """Convert a note name like 'C', 'F#', 'Eb', 'Dbb' to pitch class 0-11.

    The first character must be an uppercase letter A-G.

    Parameters
    ----------
    name : str
        Note name with optional accidentals (e.g., 'Ab', 'F##').

    Returns
    -------
    int
        Pitch class in 0..11.

    Raises
    ------
    ValueError
        If the letter is not in A-G.
    """
    letter = name[0].upper()
    if letter not in _LETTER_TO_SEMITONE:
        raise ValueError(f"Invalid note letter in '{name}'")
    base = _LETTER_TO_SEMITONE[letter]
    acc = _accidental_offset(name[1:])
    return (base + acc) % 12


def dcml_key_to_24class(key_str: str) -> int:
    """Convert a DCML globalkey string to one of 24 key classes (0-23).

    Classes 0-11 are major keys, 12-23 are minor keys.

    Mapping (major):
        C=0, C#/Db=1, D=2, Eb=3, E=4, F=5, F#/Gb=6, G=7, Ab=8, A=9, Bb=10, B=11

    Mapping (minor -- add 12):
        c=12, c#=13, d=14, eb=15, e=16, f=17, f#=18, g=19, ab=20, a=21, bb=22, b=23

    DCML convention: uppercase first letter = major, lowercase = minor.

    Parameters
    ----------
    key_str : str
        A DCML key string such as 'F', 'c#', 'Eb', 'bb'.

    Returns
    -------
    int
        Key class in 0..23.

    Raises
    ------
    ValueError
        If the key string is empty or contains an unrecognised letter.
    """
    if not key_str or not key_str.strip():
        raise ValueError(f"Empty key string")

    key_str = key_str.strip()
    is_minor = key_str[0].islower()
    pc = _note_name_to_pc(key_str)

    return pc + (12 if is_minor else 0)


def _key_class_to_name(key_class: int) -> str:
    """Convert a 0-23 key class back to a readable name.

    Uses flats for classes that are ambiguous (e.g., class 3 -> 'Eb' not 'D#').

    Parameters
    ----------
    key_class : int
        Key class in 0..23.

    Returns
    -------
    str
        Human-readable key name.
    """
    _MAJOR_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    _MINOR_NAMES = ["c", "c#", "d", "eb", "e", "f", "f#", "g", "ab", "a", "bb", "b"]

    if 0 <= key_class < 12:
        return _MAJOR_NAMES[key_class]
    elif 12 <= key_class < 24:
        return _MINOR_NAMES[key_class - 12]
    else:
        raise ValueError(f"key_class must be 0-23, got {key_class}")


def _resolve_single_roman(
    current_pc: int,
    roman_token: str,
    context_is_minor: bool,
) -> Tuple[int, bool]:
    """Resolve one Roman-numeral token against a current pitch class.

    Parameters
    ----------
    current_pc : int
        Pitch class (0-11) of the current reference key.
    roman_token : str
        A single Roman numeral, possibly with leading accidentals, e.g.,
        'V', 'bVI', '#iv', 'i'.
    context_is_minor : bool
        Whether the current reference key is minor (determines which scale
        intervals to use).

    Returns
    -------
    tuple[int, bool]
        ``(new_pc, new_is_minor)`` where *new_pc* is the resolved pitch
        class (0-11) and *new_is_minor* indicates whether the resulting
        key is minor (inferred from the Roman numeral case).
    """
    token = roman_token.strip()
    if not token:
        return current_pc, context_is_minor

    acc_match = re.match(r"^([b#]*)", token)
    accidentals = acc_match.group(1) if acc_match else ""
    roman_part = token[len(accidentals):]
    roman_upper = roman_part.upper()

    interval_map = _ROMAN_MINOR_INTERVALS if context_is_minor else _ROMAN_MAJOR_INTERVALS

    if roman_upper not in interval_map:
        logger.warning(
            "Unrecognised Roman numeral token '%s'; treating as unison",
            roman_token,
        )
        interval = 0
    else:
        interval = interval_map[roman_upper]

    acc_offset = _accidental_offset(accidentals)
    new_pc = (current_pc + interval + acc_offset) % 12

    # Infer mode from Roman numeral case: lowercase = minor
    new_is_minor = bool(roman_part and roman_part[0].islower())

    return new_pc, new_is_minor


def resolve_local_key(
    globalkey: str,
    localkey_roman: str,
    globalkey_is_minor: bool,
    localkey_is_minor: bool,
) -> Tuple[str, int]:
    """Resolve a DCML local key (Roman numeral relative to globalkey) to an
    absolute key name and 0-23 key class.

    In the DCML standard the *localkey* column is a Roman numeral indicating
    the tonal region relative to *globalkey*.  For example, if globalkey='F'
    and localkey='V', the local key is C major (the dominant of F major).

    Nested references are supported: ``bIII/V`` means "bIII of V (of
    globalkey)".  Tokens are resolved right-to-left so that the rightmost
    numeral is applied to the globalkey first.

    Parameters
    ----------
    globalkey : str
        Absolute key string (e.g., 'F', 'c#').
    localkey_roman : str
        Roman numeral, possibly with accidentals and ``/``-separated chain,
        e.g., 'I', 'V', 'bVI', '#iv', 'iii/i', 'bIII/bIII/V'.
    globalkey_is_minor : bool
        Whether the global key is minor (from the ``globalkey_is_minor`` TSV column).
    localkey_is_minor : bool
        Whether the local key is minor (from the ``localkey_is_minor`` TSV column).

    Returns
    -------
    tuple[str, int]
        ``(local_key_name, local_key_class)`` where the name uses the DCML
        convention (uppercase = major, lowercase = minor) and the class is
        0-23.
    """
    global_pc = _note_name_to_pc(globalkey)

    # Split on '/' and resolve right-to-left (rightmost token is relative to globalkey)
    tokens = [t.strip() for t in localkey_roman.strip().split("/") if t.strip()]

    current_pc = global_pc
    current_is_minor = globalkey_is_minor

    for token in reversed(tokens):
        current_pc, current_is_minor = _resolve_single_roman(
            current_pc, token, current_is_minor,
        )

    local_pc = current_pc

    # Build the name using DCML convention.
    # Use the authoritative localkey_is_minor flag from the TSV for the final
    # result (it may disagree with the Roman-numeral case for edge cases).
    _MAJOR_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    _MINOR_NAMES = ["c", "c#", "d", "eb", "e", "f", "f#", "g", "ab", "a", "bb", "b"]

    if localkey_is_minor:
        local_name = _MINOR_NAMES[local_pc]
        local_class = local_pc + 12
    else:
        local_name = _MAJOR_NAMES[local_pc]
        local_class = local_pc

    return local_name, local_class


# ---------------------------------------------------------------------------
# TSV parsing
# ---------------------------------------------------------------------------

def _parse_beat(onset_str: str) -> float:
    """Parse an onset string that may be a fraction (e.g., '1/4', '3/8') or decimal.

    Parameters
    ----------
    onset_str : str
        Onset value from the TSV, e.g., '0', '1/4', '3/8', '1.5'.

    Returns
    -------
    float
        Numeric beat offset.
    """
    onset_str = onset_str.strip()
    if not onset_str:
        return 0.0
    if "/" in onset_str:
        parts = onset_str.split("/")
        try:
            return float(parts[0]) / float(parts[1])
        except (ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(onset_str)
    except ValueError:
        return 0.0


def parse_dcml_tsv(tsv_path: str | Path) -> List[Dict[str, Any]]:
    """Read a DCML harmonies TSV and return a list of annotation dicts.

    Each dict contains:

    - ``mn`` (int): Measure number.
    - ``mn_onset`` (float): Beat onset within the measure.
    - ``timesig`` (str): Time signature string.
    - ``globalkey`` (str): Absolute global key.
    - ``localkey`` (str): Roman numeral local key (relative to globalkey).
    - ``numeral`` (str): Chord Roman numeral.
    - ``form`` (str): Chord form (e.g., 'o', '+').
    - ``figbass`` (str): Figured-bass inversion label.
    - ``changes`` (str): Chord alterations.
    - ``relativeroot`` (str): Secondary-dominant target.
    - ``chord_type`` (str): Chord quality label (e.g., 'M', 'm', 'o7').
    - ``globalkey_is_minor`` (bool): Whether globalkey is minor.
    - ``localkey_is_minor`` (bool): Whether localkey is minor.
    - ``cadence`` (str): Cadence label if present.
    - ``phraseend`` (str): Phrase-end marker.

    Parameters
    ----------
    tsv_path : str or Path
        Path to a ``.harmonies.tsv`` file.

    Returns
    -------
    list[dict[str, Any]]
        One dict per annotation row, sorted by measure number then beat onset.

    Raises
    ------
    FileNotFoundError
        If *tsv_path* does not exist.
    """
    tsv_path = Path(tsv_path)
    if not tsv_path.exists():
        raise FileNotFoundError(f"TSV file not found: {tsv_path}")

    annotations: List[Dict[str, Any]] = []

    with open(tsv_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            # Column names vary slightly across corpora; be defensive
            mn_raw = row.get("mn", "")
            if mn_raw == "" or mn_raw is None:
                continue
            try:
                mn = int(mn_raw)
            except ValueError:
                logger.debug("Skipping row with non-integer mn: %s", mn_raw)
                continue

            mn_onset = _parse_beat(row.get("mn_onset", "0"))
            timesig = row.get("timesig", "")
            globalkey = row.get("globalkey", "")
            localkey = row.get("localkey", "")
            numeral = row.get("numeral", "")
            form = row.get("form", "")
            figbass = row.get("figbass", "")
            changes = row.get("changes", "")
            relativeroot = row.get("relativeroot", "")
            chord_type = row.get("chord_type", "")
            cadence = row.get("cadence", "")
            phraseend = row.get("phraseend", "")

            # Parse boolean flags; default to inferring from case if column missing
            gk_minor_raw = row.get("globalkey_is_minor", "")
            lk_minor_raw = row.get("localkey_is_minor", "")

            if gk_minor_raw in ("0", "1"):
                gk_is_minor = gk_minor_raw == "1"
            else:
                gk_is_minor = bool(globalkey and globalkey[0].islower())

            if lk_minor_raw in ("0", "1"):
                lk_is_minor = lk_minor_raw == "1"
            else:
                # Fall back to Roman numeral case: lowercase Roman = minor
                lk_is_minor = bool(localkey and localkey[0].islower())

            # Skip rows without a valid globalkey
            if not globalkey:
                continue

            annotations.append({
                "mn": mn,
                "mn_onset": mn_onset,
                "timesig": timesig,
                "globalkey": globalkey,
                "localkey": localkey,
                "numeral": numeral,
                "form": form,
                "figbass": figbass,
                "changes": changes,
                "relativeroot": relativeroot,
                "chord_type": chord_type,
                "globalkey_is_minor": gk_is_minor,
                "localkey_is_minor": lk_is_minor,
                "cadence": cadence,
                "phraseend": phraseend,
            })

    # Stable sort by (measure, beat)
    annotations.sort(key=lambda a: (a["mn"], a["mn_onset"]))
    return annotations


# ---------------------------------------------------------------------------
# Key-region segmentation
# ---------------------------------------------------------------------------

def _segment_key_regions(
    annotations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Collapse consecutive annotations with the same resolved local key into
    contiguous key regions.

    Parameters
    ----------
    annotations : list[dict]
        Parsed annotation dicts (output of :func:`parse_dcml_tsv`).

    Returns
    -------
    list[dict]
        Key regions, each with ``start_measure``, ``end_measure``,
        ``localkey`` (absolute name), and ``localkey_class`` (0-23).
    """
    if not annotations:
        return []

    regions: List[Dict[str, Any]] = []
    prev_key_class: Optional[int] = None
    prev_key_name: Optional[str] = None

    for ann in annotations:
        local_name, local_class = resolve_local_key(
            ann["globalkey"],
            ann["localkey"],
            ann["globalkey_is_minor"],
            ann["localkey_is_minor"],
        )

        if local_class != prev_key_class:
            # Start a new region
            if regions:
                regions[-1]["end_measure"] = ann["mn"]
            regions.append({
                "start_measure": ann["mn"],
                "end_measure": ann["mn"],
                "localkey": local_name,
                "localkey_class": local_class,
            })
            prev_key_class = local_class
            prev_key_name = local_name
        else:
            # Extend current region
            regions[-1]["end_measure"] = ann["mn"]

    return regions


# ---------------------------------------------------------------------------
# Per-piece export
# ---------------------------------------------------------------------------

def _determine_quality(numeral: str, form: str, chord_type: str) -> str:
    """Infer a human-readable chord quality string.

    Prioritises the explicit ``chord_type`` column from the DCML TSV.  Falls
    back to ``form`` and ``numeral`` case.

    Parameters
    ----------
    numeral : str
        Roman numeral (e.g., 'I', 'iv', '#vii').
    form : str
        Form symbol (e.g., 'o', '+', '%').
    chord_type : str
        Explicit chord type from the TSV (e.g., 'M', 'm', 'Mm7', 'o7').

    Returns
    -------
    str
        Quality label such as 'major', 'minor', 'diminished', 'augmented',
        'dominant7', 'diminished7', etc.
    """
    ct = chord_type.strip()
    if ct:
        _TYPE_MAP = {
            "M": "major",
            "m": "minor",
            "o": "diminished",
            "+": "augmented",
            "Mm7": "dominant7",
            "mm7": "minor7",
            "MM7": "major7",
            "o7": "diminished7",
            "%7": "half-diminished7",
            "mM7": "minor-major7",
            "+M7": "augmented-major7",
            "+7": "augmented7",
            "Mm65": "dominant7",
            "Mm43": "dominant7",
            "Mm42": "dominant7",
            "Mm2": "dominant7",
        }
        if ct in _TYPE_MAP:
            return _TYPE_MAP[ct]
        # Try prefix matching for inversions like "Mm7" inside "Mm43" etc.
        for prefix in ("Mm", "mm", "MM", "mM", "+M", "+"):
            if ct.startswith(prefix):
                base = _TYPE_MAP.get(prefix + "7", ct)
                return base
        return ct

    # Fall back to form
    if form == "o":
        return "diminished"
    if form == "+":
        return "augmented"
    if form == "%":
        return "half-diminished"

    # Fall back to numeral case
    bare = re.sub(r"[^a-zA-Z]", "", numeral)
    if bare and bare[0].islower():
        return "minor"
    return "major"


def build_piece_json(
    tsv_path: Path,
    corpus_name: str,
) -> Dict[str, Any]:
    """Build the full JSON payload for one piece.

    Parameters
    ----------
    tsv_path : Path
        Path to the harmonies TSV.
    corpus_name : str
        Name of the corpus (e.g., 'ABC').

    Returns
    -------
    dict
        JSON-serialisable payload with keys: ``source``, ``corpus``,
        ``piece_id``, ``global_key``, ``global_key_class``, ``annotations``,
        ``key_regions``, ``statistics``.
    """
    annotations = parse_dcml_tsv(tsv_path)

    if not annotations:
        return {}

    # Derive piece_id from filename
    piece_id = tsv_path.stem.replace(".harmonies", "")

    # Global key from first annotation
    globalkey = annotations[0]["globalkey"]
    try:
        global_key_class = dcml_key_to_24class(globalkey)
    except ValueError:
        logger.warning("Cannot parse globalkey '%s' in %s", globalkey, tsv_path)
        global_key_class = -1

    # Build annotations list
    annotation_records: List[Dict[str, Any]] = []
    major_count = 0
    minor_count = 0
    local_keys_seen: set[int] = set()

    for ann in annotations:
        local_name, local_class = resolve_local_key(
            ann["globalkey"],
            ann["localkey"],
            ann["globalkey_is_minor"],
            ann["localkey_is_minor"],
        )
        local_keys_seen.add(local_class)

        quality = _determine_quality(ann["numeral"], ann["form"], ann["chord_type"])

        # Beat: mn_onset converted to 1-indexed beat
        # DCML mn_onset is fraction of bar from 0; convert to beat number
        # e.g., 0 -> beat 1.0, 1/4 in 4/4 -> beat 2.0
        beat_offset = ann["mn_onset"]
        # Parse time sig to get beat duration
        beat = 1.0 + beat_offset  # simplified: offset in whole notes from bar start
        try:
            ts_parts = ann["timesig"].split("/")
            if len(ts_parts) == 2:
                denom = int(ts_parts[1])
                # mn_onset is in fractions of a whole note; convert to beats
                # where beat = quarter note
                beat = 1.0 + beat_offset * (denom / 4.0) * 4.0
                # Actually, DCML mn_onset is in fractions of a whole note.
                # To get quarter-note beats: multiply by 4
                beat = 1.0 + beat_offset * 4.0
        except (ValueError, IndexError):
            beat = 1.0 + beat_offset * 4.0

        if local_class >= 12:
            minor_count += 1
        else:
            major_count += 1

        annotation_records.append({
            "measure": ann["mn"],
            "beat": round(beat, 4),
            "localkey": local_name,
            "localkey_class": local_class,
            "numeral": ann["numeral"],
            "quality": quality,
            "form": ann["form"],
            "figbass": ann["figbass"],
        })

    key_regions = _segment_key_regions(annotations)

    payload: Dict[str, Any] = {
        "source": "dcml",
        "corpus": corpus_name,
        "piece_id": piece_id,
        "global_key": globalkey,
        "global_key_class": global_key_class,
        "annotations": annotation_records,
        "key_regions": key_regions,
        "statistics": {
            "total_annotations": len(annotation_records),
            "unique_local_keys": len(local_keys_seen),
            "major_annotations": major_count,
            "minor_annotations": minor_count,
        },
    }

    return payload


# ---------------------------------------------------------------------------
# Batch export
# ---------------------------------------------------------------------------

def export_dcml_labels(
    corpus_dir: str | Path,
    output_dir: str | Path,
    corpus_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Batch-process all harmonies TSV files in a corpus directory.

    Writes one JSON file per piece into *output_dir*.

    Parameters
    ----------
    corpus_dir : str or Path
        Root directory of a single DCML corpus (e.g., ``dcml_corpora/ABC``).
    output_dir : str or Path
        Directory where JSON files will be written.
    corpus_name : str, optional
        Name label for the corpus.  Defaults to the directory name.

    Returns
    -------
    list[dict]
        Summary records with ``piece_id``, ``global_key``, ``total_annotations``.
    """
    corpus_dir = Path(corpus_dir)
    output_dir = Path(output_dir)

    if corpus_name is None:
        corpus_name = corpus_dir.name

    harmonies_dir = corpus_dir / "harmonies"
    if not harmonies_dir.is_dir():
        logger.error("No harmonies/ subdirectory in %s", corpus_dir)
        return []

    tsv_files = sorted(harmonies_dir.glob("*.harmonies.tsv"))
    if not tsv_files:
        logger.warning("No .harmonies.tsv files found in %s", harmonies_dir)
        return []

    # Ensure corpus-specific output directory exists
    corpus_output = output_dir / corpus_name
    corpus_output.mkdir(parents=True, exist_ok=True)

    summaries: List[Dict[str, Any]] = []
    errors: List[str] = []

    for tsv_path in tsv_files:
        try:
            payload = build_piece_json(tsv_path, corpus_name)
            if not payload:
                logger.warning("Empty payload for %s; skipping", tsv_path.name)
                continue

            out_file = corpus_output / f"{payload['piece_id']}.json"
            with open(out_file, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)

            summaries.append({
                "piece_id": payload["piece_id"],
                "global_key": payload["global_key"],
                "total_annotations": payload["statistics"]["total_annotations"],
                "major_annotations": payload["statistics"]["major_annotations"],
                "minor_annotations": payload["statistics"]["minor_annotations"],
            })
        except Exception as exc:
            logger.error("Error processing %s: %s", tsv_path.name, exc)
            errors.append(f"{tsv_path.name}: {exc}")

    logger.info(
        "Exported %d pieces from %s (%d errors)",
        len(summaries),
        corpus_name,
        len(errors),
    )
    if errors:
        for err in errors:
            logger.error("  %s", err)

    return summaries


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def print_corpus_statistics(summaries: List[Dict[str, Any]], corpus_name: str) -> None:
    """Print an overview of key distribution statistics for a processed corpus.

    Parameters
    ----------
    summaries : list[dict]
        Summary records returned by :func:`export_dcml_labels`.
    corpus_name : str
        Label for display.
    """
    if not summaries:
        print(f"  No data for {corpus_name}.")
        return

    total_ann = sum(s["total_annotations"] for s in summaries)
    total_major = sum(s["major_annotations"] for s in summaries)
    total_minor = sum(s["minor_annotations"] for s in summaries)
    n_pieces = len(summaries)

    key_counts: Counter[str] = Counter()
    for s in summaries:
        key_counts[s["global_key"]] += 1

    print(f"\n{'='*60}")
    print(f"  Corpus: {corpus_name}")
    print(f"{'='*60}")
    print(f"  Pieces processed:        {n_pieces}")
    print(f"  Total annotations:       {total_ann}")
    print(f"  Major-key annotations:   {total_major} ({100*total_major/max(total_ann,1):.1f}%)")
    print(f"  Minor-key annotations:   {total_minor} ({100*total_minor/max(total_ann,1):.1f}%)")
    print(f"\n  Global key distribution:")
    for key, count in key_counts.most_common():
        print(f"    {key:>4s}: {count:3d} piece(s)")
    print()


def print_aggregate_statistics(
    all_output_dir: Path,
) -> None:
    """Read all exported JSON files and print aggregate statistics.

    Parameters
    ----------
    all_output_dir : Path
        The top-level output directory containing corpus subdirectories.
    """
    overall_major = 0
    overall_minor = 0
    overall_ann = 0
    overall_pieces = 0
    key_class_counts: Counter[int] = Counter()
    corpus_stats: Dict[str, Dict[str, int]] = {}

    for corpus_subdir in sorted(all_output_dir.iterdir()):
        if not corpus_subdir.is_dir():
            continue
        corpus_name = corpus_subdir.name
        c_major = 0
        c_minor = 0
        c_ann = 0
        c_pieces = 0

        for json_file in sorted(corpus_subdir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                stats = data.get("statistics", {})
                c_ann += stats.get("total_annotations", 0)
                c_major += stats.get("major_annotations", 0)
                c_minor += stats.get("minor_annotations", 0)
                c_pieces += 1

                gk_class = data.get("global_key_class", -1)
                if gk_class >= 0:
                    key_class_counts[gk_class] += 1
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("Error reading %s: %s", json_file, exc)

        corpus_stats[corpus_name] = {
            "pieces": c_pieces,
            "annotations": c_ann,
            "major": c_major,
            "minor": c_minor,
        }
        overall_pieces += c_pieces
        overall_ann += c_ann
        overall_major += c_major
        overall_minor += c_minor

    print(f"\n{'='*60}")
    print(f"  AGGREGATE STATISTICS")
    print(f"{'='*60}")
    print(f"  Total corpora:           {len(corpus_stats)}")
    print(f"  Total pieces:            {overall_pieces}")
    print(f"  Total annotations:       {overall_ann}")
    print(f"  Major-key annotations:   {overall_major} ({100*overall_major/max(overall_ann,1):.1f}%)")
    print(f"  Minor-key annotations:   {overall_minor} ({100*overall_minor/max(overall_ann,1):.1f}%)")

    print(f"\n  Per-corpus breakdown:")
    for cname, cs in sorted(corpus_stats.items()):
        pct_major = 100 * cs["major"] / max(cs["annotations"], 1)
        print(
            f"    {cname:30s}  {cs['pieces']:3d} pieces  "
            f"{cs['annotations']:6d} ann  "
            f"{pct_major:5.1f}% major"
        )

    print(f"\n  Global key class distribution (across all corpora):")
    for kc, count in key_class_counts.most_common():
        name = _key_class_to_name(kc)
        mode = "minor" if kc >= 12 else "major"
        print(f"    {name:>4s} ({mode:5s}): {count:3d} piece(s)")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Parameters
    ----------
    argv : sequence of str, optional
        Argument list; defaults to ``sys.argv[1:]``.

    Returns
    -------
    argparse.Namespace
    """
    parser = argparse.ArgumentParser(
        description="Parse DCML corpus harmonic annotations into JSON key labels.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Process a single corpus\n"
            "  python parse_dcml_annotations.py --corpus-dir research_data/dcml_corpora/ABC\n\n"
            "  # Process all corpora in the default location\n"
            "  python parse_dcml_annotations.py --all\n\n"
            "  # Print statistics from already-exported JSON\n"
            "  python parse_dcml_annotations.py --stats\n"
        ),
    )
    parser.add_argument(
        "--corpus-dir",
        type=str,
        default=None,
        help=(
            "Path to a single DCML corpus directory (must contain a harmonies/ "
            "subdirectory).  If omitted and --all is not set, defaults to "
            "processing the ABC corpus."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every corpus found under the default dcml_corpora/ directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Root directory for JSON output (default: %(default)s).",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print key-distribution statistics (reads from --output-dir).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Entry point."""
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.stats:
        print_aggregate_statistics(output_dir)
        return

    if args.all:
        # Process every subdirectory in the default corpora location
        corpora_root = DEFAULT_CORPUS_DIR
        if not corpora_root.is_dir():
            logger.error("Corpora root not found: %s", corpora_root)
            sys.exit(1)
        corpus_dirs = sorted(
            d for d in corpora_root.iterdir()
            if d.is_dir() and (d / "harmonies").is_dir()
        )
        if not corpus_dirs:
            logger.error("No corpora with harmonies/ found under %s", corpora_root)
            sys.exit(1)
        for cdir in corpus_dirs:
            summaries = export_dcml_labels(cdir, output_dir)
            print_corpus_statistics(summaries, cdir.name)
    else:
        # Single corpus
        if args.corpus_dir:
            corpus_path = Path(args.corpus_dir)
        else:
            corpus_path = DEFAULT_CORPUS_DIR / "ABC"

        if not corpus_path.is_dir():
            logger.error("Corpus directory not found: %s", corpus_path)
            sys.exit(1)

        summaries = export_dcml_labels(corpus_path, output_dir)
        print_corpus_statistics(summaries, corpus_path.name)


if __name__ == "__main__":
    main()
