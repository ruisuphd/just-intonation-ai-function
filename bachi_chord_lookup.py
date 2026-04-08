#!/usr/bin/env python3
"""
BACHI chord label loader and Just Intonation ratio mapping.

Loads pre-computed BACHI chord labels and maps chord qualities to JI ratio tables.
Ports the chord-aware JI calculation from js/tuning-core.js to Python for offline
evaluation and integration with the tuning pipeline.

Usage:
    python bachi_chord_lookup.py --composition-id 7
    python bachi_chord_lookup.py --test-mapping
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import os
from typing import Dict, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACHI_CLASSICAL_DIR = os.path.join(BASE_DIR, 'research_data', 'bachi_chord_labels_classical')

# --- BACHI quality to JI chord type mapping ---
# Maps BACHI chord quality labels to the chord type keys used in CHORD_JI_RATIOS.
# None = no chord-aware tuning; fall back to key-based JI.
BACHI_TO_JI_QUALITY = {
    'M':     'major',
    'm':     'minor',
    'D7':    'dominant7',
    'Mm7':   'dominant7',
    'mm7':   'minor7',
    'MM7':   'major7',
    'o':     'diminished',
    'o7':    'dim7',
    '/o7':   'halfDim7',
    '+':     'augmented',
    '+7':    'augmented',
    'sus4':  None,
    'sus2':  None,
    'N':     None,
    'other': None,
}

# --- Chord-specific JI ratio tables (ported from js/tuning-core.js) ---
# Keys are intervals (0-11) above the chord root; values are frequency ratios.
CHORD_JI_RATIOS = {
    'dominant7':   {0: 1/1, 4: 5/4, 7: 3/2, 10: 7/4},
    'major':       {0: 1/1, 4: 5/4, 7: 3/2},
    'minor':       {0: 1/1, 3: 6/5, 7: 3/2},
    'diminished':  {0: 1/1, 3: 6/5, 6: 7/5},
    'augmented':   {0: 1/1, 4: 5/4, 8: 25/16},
    'minor7':      {0: 1/1, 3: 6/5, 7: 3/2, 10: 9/5},
    'major7':      {0: 1/1, 4: 5/4, 7: 3/2, 11: 15/8},
    'halfDim7':    {0: 1/1, 3: 6/5, 6: 45/32, 10: 9/5},
    'dim7':        {0: 1/1, 3: 6/5, 6: 7/5, 9: 12/7},
}

# 5-limit JI ratios for key-based fallback (scale degrees relative to tonic)
KEY_JI_RATIOS = {
    'major': {
        0: 1/1, 1: 16/15, 2: 9/8, 3: 6/5, 4: 5/4, 5: 4/3,
        6: 45/32, 7: 3/2, 8: 8/5, 9: 5/3, 10: 9/5, 11: 15/8,
    },
    'minor': {
        0: 1/1, 1: 16/15, 2: 9/8, 3: 6/5, 4: 5/4, 5: 4/3,
        6: 45/32, 7: 3/2, 8: 8/5, 9: 5/3, 10: 9/5, 11: 15/8,
    },
}

# Pitch class for each note name
NOTE_TO_PC = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'Fb': 4, 'E#': 5, 'F': 5, 'F#': 6, 'Gb': 6,
    'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10,
    'B': 11, 'Cb': 11,
}


def ratio_to_cents(ratio: float) -> float:
    """Convert frequency ratio to cents deviation from 12-TET."""
    if ratio <= 0:
        return 0.0
    return 1200.0 * math.log2(ratio)


def ji_cents_deviation(interval: int, ratio: float) -> float:
    """Compute cents deviation of a JI ratio from the 12-TET interval."""
    ji_cents = ratio_to_cents(ratio)
    et_cents = interval * 100.0
    return ji_cents - et_cents


class BACHIChordLookup:
    """Looks up BACHI chord labels by beat position for a given composition."""

    def __init__(self, composition_id: int, label_dir: str = BACHI_CLASSICAL_DIR):
        self.composition_id = composition_id
        self.chords: List[Dict] = []
        self.beat_positions: List[float] = []

        # Try to load BACHI labels
        path = os.path.join(label_dir, f'{composition_id:04d}.json')
        if os.path.isfile(path):
            with open(path, 'r') as f:
                data = json.load(f)
            self.chords = data.get('chords', data if isinstance(data, list) else [])
            self.beat_positions = [float(c.get('beat', 0)) for c in self.chords]

    def chord_at_beat(self, beat: float) -> Optional[Dict]:
        """Get the active chord at a given beat position."""
        if not self.beat_positions:
            return None
        # Find the last chord that starts at or before this beat
        idx = bisect.bisect_right(self.beat_positions, beat) - 1
        if idx < 0:
            return None
        return self.chords[idx]

    def chord_info_at_beat(self, beat: float) -> Optional[Dict]:
        """Get chord info in the format expected by calculate_ji_cents_with_function.

        Returns:
            Dict with 'chordRootPc' (int 0-11) and 'chordQuality' (str), or None.
        """
        chord = self.chord_at_beat(beat)
        if chord is None:
            return None

        root = chord.get('root', '')
        quality = chord.get('quality', '')

        root_pc = NOTE_TO_PC.get(root)
        if root_pc is None:
            return None

        ji_quality = BACHI_TO_JI_QUALITY.get(quality)
        if ji_quality is None:
            return None

        return {'chordRootPc': root_pc, 'chordQuality': ji_quality}


def calculate_ji_cents_for_note(midi_note: int, key_root_pc: int, is_minor: bool) -> float:
    """Calculate JI cents deviation for a note based on key context only (5-limit)."""
    note_pc = midi_note % 12
    interval = (note_pc - key_root_pc + 12) % 12
    ratios = KEY_JI_RATIOS['minor' if is_minor else 'major']
    ratio = ratios.get(interval, 1.0)
    return ji_cents_deviation(interval, ratio)


def calculate_ji_cents_with_function(
    midi_note: int,
    key_root_pc: int,
    is_minor: bool,
    chord_info: Optional[Dict] = None,
) -> Tuple[float, str]:
    """Calculate JI pitch deviation using chord-function context.

    Ports calculateJICentsWithFunction from js/tuning-core.js to Python.

    Args:
        midi_note: MIDI note number (0-127)
        key_root_pc: Pitch class of current key root (0-11)
        is_minor: Whether current key is minor
        chord_info: Optional dict with 'chordRootPc' and 'chordQuality'

    Returns:
        (cents_deviation, source) where source is 'chord' or 'key'
    """
    # Fallback: no chord context
    if chord_info is None:
        return calculate_ji_cents_for_note(midi_note, key_root_pc, is_minor), 'key'

    chord_root_pc = chord_info['chordRootPc']
    chord_quality = chord_info['chordQuality']

    chord_ratios = CHORD_JI_RATIOS.get(chord_quality)
    if chord_ratios is None:
        return calculate_ji_cents_for_note(midi_note, key_root_pc, is_minor), 'key'

    # Interval of note relative to chord root
    note_pc = midi_note % 12
    interval_from_chord = (note_pc - chord_root_pc + 12) % 12

    if interval_from_chord in chord_ratios:
        ratio = chord_ratios[interval_from_chord]
        chord_tone_dev = ji_cents_deviation(interval_from_chord, ratio)

        # Chord root's own deviation from 12-TET relative to the key
        root_interval = (chord_root_pc - key_root_pc + 12) % 12
        key_ratios = KEY_JI_RATIOS['minor' if is_minor else 'major']
        root_ratio = key_ratios.get(root_interval, 1.0)
        root_dev = ji_cents_deviation(root_interval, root_ratio)

        return root_dev + chord_tone_dev, 'chord'

    # Not a chord tone — fall back to key-based
    return calculate_ji_cents_for_note(midi_note, key_root_pc, is_minor), 'key'


def test_mapping() -> None:
    """Verify BACHI-to-JI mapping with concrete examples."""
    print('BACHI Quality -> JI Chord Type -> Ratio Table:')
    print(f'{"BACHI":<10} {"JI Type":<15} {"Ratios":}')
    print('-' * 65)
    for bachi_q, ji_type in sorted(BACHI_TO_JI_QUALITY.items()):
        if ji_type is None:
            print(f'{bachi_q:<10} {"(fallback)":<15} key-based 5-limit')
        else:
            ratios = CHORD_JI_RATIOS[ji_type]
            ratio_str = ', '.join(f'{k}:{v:.4f}' for k, v in sorted(ratios.items()))
            print(f'{bachi_q:<10} {ji_type:<15} {ratio_str}')

    # Example: G7 chord in key of C major, playing B (leading tone)
    # B is interval 4 above G (G=7, B=11, diff=4) → 5/4 ratio
    print('\nExample: B4 (MIDI 71) in G dominant 7th, key of C major')
    cents, source = calculate_ji_cents_with_function(
        midi_note=71, key_root_pc=0, is_minor=False,
        chord_info={'chordRootPc': 7, 'chordQuality': 'dominant7'},
    )
    print(f'  Cents deviation: {cents:+.2f} (source: {source})')
    print(f'  Expected: B as major 3rd of G = 5/4 = -13.69 cents from 12-TET')
    print(f'  Plus G root offset in C major: 3/2 = +1.96 cents')
    print(f'  Total expected: ~-11.73 cents')

    # Example: F in G7 (septimal 7th = 7/4)
    print('\nExample: F4 (MIDI 65) as 7th of G dominant 7th, key of C major')
    cents, source = calculate_ji_cents_with_function(
        midi_note=65, key_root_pc=0, is_minor=False,
        chord_info={'chordRootPc': 7, 'chordQuality': 'dominant7'},
    )
    print(f'  Cents deviation: {cents:+.2f} (source: {source})')
    print(f'  7/4 = 968.8 cents, 12-TET minor 7th = 1000 cents')
    print(f'  Expected: ~-31.2 + 1.96 = ~-29.2 cents (septimal tuning)')


def main() -> None:
    parser = argparse.ArgumentParser(description='BACHI chord label lookup and JI mapping')
    parser.add_argument('--composition-id', type=int, default=None,
                        help='Show chord labels for a specific composition')
    parser.add_argument('--test-mapping', action='store_true',
                        help='Run mapping verification tests')
    parser.add_argument('--label-dir', default=BACHI_CLASSICAL_DIR)
    args = parser.parse_args()

    if args.test_mapping:
        test_mapping()
        return

    if args.composition_id is not None:
        lookup = BACHIChordLookup(args.composition_id, args.label_dir)
        print(f'Composition {args.composition_id}: {len(lookup.chords)} chords')
        for chord in lookup.chords[:20]:
            beat = chord.get('beat', 0)
            info = lookup.chord_info_at_beat(beat)
            quality = chord.get('quality', '?')
            root = chord.get('root', '?')
            ji_type = BACHI_TO_JI_QUALITY.get(quality, '?')
            print(f'  Beat {beat:>8.2f}: {root} {quality:<6} -> JI: {ji_type}')
        if len(lookup.chords) > 20:
            print(f'  ... and {len(lookup.chords) - 20} more chords')
    else:
        # Count all available chord labels
        label_dir = args.label_dir
        count = 0
        total_chords = 0
        for f in os.listdir(label_dir):
            if f.endswith('.json'):
                count += 1
                with open(os.path.join(label_dir, f), 'r') as fh:
                    data = json.load(fh)
                    chords = data.get('chords', data if isinstance(data, list) else [])
                    total_chords += len(chords)
        print(f'BACHI labels: {count} compositions, {total_chords} total chords')
        print(f'Label directory: {label_dir}')
        print('\nRun with --test-mapping to verify the JI ratio mapping.')
        print('Run with --composition-id N to inspect a specific composition.')


if __name__ == '__main__':
    main()
