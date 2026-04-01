#!/usr/bin/env python3
"""
Batch pipeline for generating per-note Roman numeral chord labels from MusicXML
scores in the ATEPP dataset.

This script reads the score-level key/note labels produced by
extract_score_key_labels.py and augments each note with harmonic analysis
(Roman numeral, chord quality, root pitch class, inversion, secondary
function).

Two automatic analysis backends are supported:

    1. AugmentedNet (default)
       Napoles Lopez, M., Cumming, J., & Fujinaga, I. (2021).
       "AugmentedNet: A Roman Numeral Analysis Network with Synthetic
       Training Examples and Additional Tasks." ISMIR 2021.
       Install: pip install augmentednet

    2. AnalysisGNN
       Karystinaios, E., Widmer, G., & McLeod, A. (2025).
       "End-to-End Roman Numeral Analysis with Graph Neural Networks."
       arXiv:2509.06654 (CMMR 2025).

Related work / alternatives not implemented here:
    - RNBert: Sailor, H. (2024). "RNBert: Transformer-based Roman Numeral
      Analysis." ISMIR 2024.
    - ChordGNN: Karystinaios, E. & Widmer, G. (2023). "Roman Numeral
      Analysis with Graph Neural Networks." ISMIR 2023, arXiv:2307.03544.

Usage
-----
    # Pilot audit on 5 scores (no backend needed -- generates stub labels)
    python build_roman_numeral_labels.py --pilot 5

    # Full run with AugmentedNet
    python build_roman_numeral_labels.py --backend augmentednet

    # Full run with AnalysisGNN
    python build_roman_numeral_labels.py --backend analysisgnn

This is a research scaffold; the actual model calls are marked with TODO
comments.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Lazy backend imports -- wrapped so the script can still run in pilot/stub
# mode without the heavy dependencies installed.
# ---------------------------------------------------------------------------

_augmentednet = None
_analysisgnn = None


def _try_import_augmentednet():
    """Attempt to import AugmentedNet. Returns the module or None."""
    global _augmentednet
    if _augmentednet is not None:
        return _augmentednet
    try:
        import augmentednet  # noqa: F401
        _augmentednet = augmentednet
        return _augmentednet
    except ImportError:
        return None


def _try_import_analysisgnn():
    """Attempt to import AnalysisGNN. Returns the module or None."""
    global _analysisgnn
    if _analysisgnn is not None:
        return _analysisgnn
    try:
        import analysisgnn  # noqa: F401
        _analysisgnn = analysisgnn
        return _analysisgnn
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, 'ATEPP_JI_Dataset')
DEFAULT_ATEPP_BASE = os.path.join(DATASET_DIR, 'ATEPP-1.2')
DEFAULT_METADATA_CSV = os.path.join(DATASET_DIR, 'ATEPP-metadata-JI.csv')
DEFAULT_LABEL_DIR = os.path.join(BASE_DIR, 'research_data', 'score_key_labels')
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, 'research_data', 'roman_numeral_labels')

# ---------------------------------------------------------------------------
# Chord quality vocabulary (shared across backends)
# ---------------------------------------------------------------------------

QUALITY_VOCAB = {
    'M': 'major',
    'maj': 'major',
    'major': 'major',
    'm': 'minor',
    'min': 'minor',
    'minor': 'minor',
    'd': 'diminished',
    'dim': 'diminished',
    'diminished': 'diminished',
    'a': 'augmented',
    'aug': 'augmented',
    'augmented': 'augmented',
    'Mm7': 'dominant7',
    'dom7': 'dominant7',
    'dominant7': 'dominant7',
    'mm7': 'minor7',
    'minor7': 'minor7',
    'MM7': 'major7',
    'major7': 'major7',
    'dd7': 'diminished7',
    'diminished7': 'diminished7',
    'dm7': 'half-diminished7',
    'half-diminished7': 'half-diminished7',
}

NOTE_NAMES_TO_PC = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'Fb': 4, 'E#': 5, 'F': 5, 'F#': 6, 'Gb': 6,
    'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10,
    'B': 11, 'Cb': 11,
}


# ---------------------------------------------------------------------------
# Backend: AugmentedNet
# ---------------------------------------------------------------------------

def _analyse_augmentednet(score_path: str) -> List[Dict[str, Any]]:
    """
    Run AugmentedNet on a MusicXML score and return a time-sorted list of
    chord spans.

    Each span dict has:
        onset_beat : float   -- onset in quarter-note beats from start
        offset_beat: float   -- offset in quarter-note beats
        roman      : str     -- raw Roman numeral string (e.g. "V65/V")
        quality    : str     -- normalised quality string
        root_pc    : int     -- pitch class 0-11
        inversion  : int     -- 0-3
        is_secondary: bool

    Returns an empty list if the backend is unavailable.
    """
    mod = _try_import_augmentednet()
    if mod is None:
        print('[WARN] augmentednet not installed -- returning empty analysis.')
        return []

    # TODO ---------------------------------------------------------------
    # AugmentedNet API call.  The exact interface depends on the version
    # installed.  The typical pattern is:
    #
    #   from augmentednet import predict
    #   predictions = predict(score_path)
    #   # predictions is a list of dicts / named tuples with fields:
    #   #   onset, offset, key, degree, quality, inversion, root
    #
    # Convert each prediction to the span dict format documented above.
    # The stub below returns an empty list so the pipeline can run end-to-
    # end in pilot mode without the dependency.
    #
    # Example conversion pseudocode:
    #   spans = []
    #   for pred in predictions:
    #       spans.append({
    #           'onset_beat': float(pred.onset),
    #           'offset_beat': float(pred.offset),
    #           'roman': str(pred.degree),
    #           'quality': QUALITY_VOCAB.get(pred.quality, pred.quality),
    #           'root_pc': NOTE_NAMES_TO_PC.get(pred.root, 0),
    #           'inversion': int(pred.inversion),
    #           'is_secondary': '/' in str(pred.degree),
    #       })
    #   return spans
    # --------------------------------------------------------------------
    raise NotImplementedError(
        'AugmentedNet integration not yet wired up. '
        'See the TODO block in _analyse_augmentednet() for instructions.'
    )


def _analyse_analysisgnn(score_path: str) -> List[Dict[str, Any]]:
    """
    Run AnalysisGNN on a MusicXML score and return time-sorted chord spans.

    Same return format as _analyse_augmentednet().
    """
    mod = _try_import_analysisgnn()
    if mod is None:
        print('[WARN] analysisgnn not installed -- returning empty analysis.')
        return []

    # TODO ---------------------------------------------------------------
    # AnalysisGNN API call.  Karystinaios et al. (arXiv:2509.06654).
    #
    # Typical usage (check their README):
    #
    #   from analysisgnn import analyze_score
    #   result = analyze_score(score_path)
    #   # result contains chords with onset/offset, roman numeral, etc.
    #
    # Convert to the same span dict format as _analyse_augmentednet().
    # --------------------------------------------------------------------
    raise NotImplementedError(
        'AnalysisGNN integration not yet wired up. '
        'See the TODO block in _analyse_analysisgnn() for instructions.'
    )


BACKENDS = {
    'augmentednet': _analyse_augmentednet,
    'analysisgnn': _analyse_analysisgnn,
}


# ---------------------------------------------------------------------------
# Stub analysis (for pilot mode when no backend is installed)
# ---------------------------------------------------------------------------

def _make_stub_label() -> Dict[str, Any]:
    """Return a placeholder Roman numeral annotation for a single note."""
    return {
        'roman_numeral': 'N/A',
        'chord_quality': 'unknown',
        'chord_root_pc': -1,
        'inversion': 0,
        'is_secondary': False,
    }


# ---------------------------------------------------------------------------
# Assigning spans to notes
# ---------------------------------------------------------------------------

def _assign_spans_to_notes(
    notes: List[Dict[str, Any]],
    spans: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    For each note, find the chord span that contains its onset and attach
    the Roman numeral fields.

    Parameters
    ----------
    notes : list of dict
        Note dicts from the score_key_labels JSON (must have 'onset_beat').
    spans : list of dict
        Chord span dicts returned by the analysis backend.

    Returns
    -------
    list of dict
        Copies of the note dicts with Roman numeral fields appended.
    """
    # Pre-sort spans by onset for binary-search friendliness.
    sorted_spans = sorted(spans, key=lambda s: s['onset_beat'])

    augmented_notes = []
    for note in notes:
        onset = note.get('onset_beat', 0.0)
        label = _make_stub_label()

        # Linear scan (fine for typical score sizes, ~1k-5k notes).
        # Could be replaced with bisect for very large scores.
        for span in sorted_spans:
            if span['onset_beat'] <= onset < span['offset_beat']:
                label = {
                    'roman_numeral': span['roman'],
                    'chord_quality': span['quality'],
                    'chord_root_pc': span['root_pc'],
                    'inversion': span['inversion'],
                    'is_secondary': span['is_secondary'],
                }
                break

        merged = copy.copy(note)
        merged.update(label)
        augmented_notes.append(merged)

    return augmented_notes


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def process_one_score(
    label_path: str,
    atepp_base: str,
    backend_fn,
    output_dir: str,
    *,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Process a single score: load existing key labels, run harmonic analysis,
    merge, and write the output JSON.

    Returns a summary dict for audit purposes.
    """
    with open(label_path, 'r', encoding='utf-8') as fh:
        payload = json.load(fh)

    score_rel = payload.get('score_path', '')
    score_abs = os.path.join(atepp_base, score_rel)

    comp_id = payload.get('composition_id', -1)
    summary: Dict[str, Any] = {
        'composition_id': comp_id,
        'composer': payload.get('composer', ''),
        'track': payload.get('track', ''),
        'note_count': payload.get('note_count', 0),
        'spans_found': 0,
        'notes_labelled': 0,
        'status': 'ok',
        'error': None,
    }

    notes = payload.get('notes', [])

    # Run analysis backend
    spans: List[Dict[str, Any]] = []
    try:
        if os.path.exists(score_abs):
            spans = backend_fn(score_abs)
        else:
            summary['status'] = 'score_missing'
            summary['error'] = f'Score file not found: {score_abs}'
            if verbose:
                print(f'  [SKIP] score missing: {score_abs}')
    except NotImplementedError:
        # Backend stub -- fall through to stub labels
        summary['status'] = 'stub'
    except Exception as exc:
        summary['status'] = 'error'
        summary['error'] = str(exc)
        if verbose:
            traceback.print_exc()

    summary['spans_found'] = len(spans)

    # Merge spans onto notes
    if spans:
        augmented_notes = _assign_spans_to_notes(notes, spans)
    else:
        # No spans available -- attach stub labels to every note.
        augmented_notes = []
        for note in notes:
            merged = copy.copy(note)
            merged.update(_make_stub_label())
            augmented_notes.append(merged)

    summary['notes_labelled'] = sum(
        1 for n in augmented_notes if n.get('roman_numeral', 'N/A') != 'N/A'
    )

    # Build output payload (extends the input format)
    out_payload = {
        'composition_id': comp_id,
        'composer': payload.get('composer', ''),
        'track': payload.get('track', ''),
        'score_path': score_rel,
        'performances': payload.get('performances', 0),
        'note_count': len(augmented_notes),
        'key_change_count': payload.get('key_change_count', 0),
        'key_changes': payload.get('key_changes', []),
        'analysis_backend': backend_fn.__name__.replace('_analyse_', ''),
        'spans_found': len(spans),
        'notes': augmented_notes,
    }

    os.makedirs(output_dir, exist_ok=True)
    out_filename = f'{comp_id:04d}.json'
    out_path = os.path.join(output_dir, out_filename)
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(out_payload, fh, indent=2)

    if verbose:
        print(
            f'  [{summary["status"].upper()}] comp {comp_id}: '
            f'{len(augmented_notes)} notes, {len(spans)} spans'
        )

    return summary


# ---------------------------------------------------------------------------
# Pilot audit
# ---------------------------------------------------------------------------

def run_pilot_audit(
    summaries: List[Dict[str, Any]],
    output_dir: str,
    audit_path: str,
) -> None:
    """
    Print detailed per-note labels for the pilot scores and save a JSON
    audit report.
    """
    print('\n' + '=' * 72)
    print('PILOT AUDIT REPORT')
    print('=' * 72)

    for summary in summaries:
        comp_id = summary['composition_id']
        print(f'\n--- Composition {comp_id}: {summary["composer"]} ---')
        print(f'    Track:  {summary["track"]}')
        print(f'    Status: {summary["status"]}')
        print(f'    Notes:  {summary["note_count"]}')
        print(f'    Spans:  {summary["spans_found"]}')
        print(f'    Labelled: {summary["notes_labelled"]}')

        # Show first 20 notes from the output file
        out_path = os.path.join(output_dir, f'{comp_id:04d}.json')
        if os.path.exists(out_path):
            with open(out_path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            sample_notes = data.get('notes', [])[:20]
            if sample_notes:
                print(f'    First {len(sample_notes)} notes:')
                for n in sample_notes:
                    print(
                        f'      idx={n["index"]:4d}  '
                        f'p={n["pitch"]:3d}  '
                        f'key={n["key"]:>4s}  '
                        f'deg={n["scale_degree"]:2d}  '
                        f'rn={n.get("roman_numeral", "?"):>8s}  '
                        f'qual={n.get("chord_quality", "?"):>16s}  '
                        f'root_pc={n.get("chord_root_pc", -1):2d}  '
                        f'inv={n.get("inversion", 0)}  '
                        f'sec={n.get("is_secondary", False)}'
                    )

    # Save machine-readable audit
    audit_report = {
        'timestamp': datetime.now(tz=__import__('datetime').timezone.utc).isoformat(),
        'pilot_count': len(summaries),
        'scores': summaries,
    }
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)
    with open(audit_path, 'w', encoding='utf-8') as fh:
        json.dump(audit_report, fh, indent=2)

    print(f'\nAudit report saved to: {audit_path}')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'Generate per-note Roman numeral chord labels for ATEPP scores. '
            'Reads score_key_labels JSON files and augments each note with '
            'harmonic analysis from AugmentedNet or AnalysisGNN.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  python build_roman_numeral_labels.py --pilot 5\n'
            '  python build_roman_numeral_labels.py --backend augmentednet\n'
            '  python build_roman_numeral_labels.py --backend analysisgnn --pilot 10\n'
        ),
    )
    parser.add_argument(
        '--label-dir',
        default=DEFAULT_LABEL_DIR,
        help='Input directory with score_key_labels JSON files '
             f'(default: {DEFAULT_LABEL_DIR})',
    )
    parser.add_argument(
        '--output-dir',
        default=DEFAULT_OUTPUT_DIR,
        help='Output directory for Roman numeral label JSON files '
             f'(default: {DEFAULT_OUTPUT_DIR})',
    )
    parser.add_argument(
        '--backend',
        choices=list(BACKENDS.keys()),
        default='augmentednet',
        help='Analysis backend to use (default: augmentednet)',
    )
    parser.add_argument(
        '--pilot',
        type=int,
        default=None,
        metavar='N',
        help='Pilot audit mode: process only N scores and print detailed '
             'per-note labels for manual inspection',
    )
    parser.add_argument(
        '--atepp-base',
        default=DEFAULT_ATEPP_BASE,
        help='Path to the ATEPP-1.2 score directory '
             f'(default: {DEFAULT_ATEPP_BASE})',
    )
    parser.add_argument(
        '--metadata-csv',
        default=DEFAULT_METADATA_CSV,
        help='Path to ATEPP metadata CSV '
             f'(default: {DEFAULT_METADATA_CSV})',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Discover input label files
    if not os.path.isdir(args.label_dir):
        print(
            f'[ERROR] Label directory not found: {args.label_dir}\n'
            'Run extract_score_key_labels.py first to generate the input data.',
            file=sys.stderr,
        )
        sys.exit(1)

    label_files = sorted([
        f for f in os.listdir(args.label_dir) if f.endswith('.json')
    ])
    if not label_files:
        print(f'[ERROR] No JSON files found in {args.label_dir}', file=sys.stderr)
        sys.exit(1)

    # Apply pilot limit
    if args.pilot is not None:
        label_files = label_files[:args.pilot]
        print(f'[PILOT] Processing {len(label_files)} of {len(label_files)} scores')

    # Resolve backend
    backend_fn = BACKENDS[args.backend]
    print(f'Backend: {args.backend}')
    print(f'Input:   {args.label_dir} ({len(label_files)} files)')
    print(f'Output:  {args.output_dir}')
    print()

    os.makedirs(args.output_dir, exist_ok=True)

    summaries: List[Dict[str, Any]] = []
    for i, fname in enumerate(label_files, 1):
        label_path = os.path.join(args.label_dir, fname)
        print(f'[{i}/{len(label_files)}] {fname}')
        summary = process_one_score(
            label_path=label_path,
            atepp_base=args.atepp_base,
            backend_fn=backend_fn,
            output_dir=args.output_dir,
            verbose=True,
        )
        summaries.append(summary)

    # Print summary
    ok = sum(1 for s in summaries if s['status'] == 'ok')
    stub = sum(1 for s in summaries if s['status'] == 'stub')
    missing = sum(1 for s in summaries if s['status'] == 'score_missing')
    errors = sum(1 for s in summaries if s['status'] == 'error')
    print(f'\nDone. ok={ok}  stub={stub}  missing={missing}  errors={errors}')

    # Pilot audit
    if args.pilot is not None:
        audit_path = os.path.join(
            BASE_DIR, 'research_data', 'roman_numeral_pilot_audit.json'
        )
        run_pilot_audit(summaries, args.output_dir, audit_path)


if __name__ == '__main__':
    main()
