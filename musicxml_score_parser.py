#!/usr/bin/env python3
"""
Minimal MusicXML / MXL parser for research-side note and key extraction.

This parser is intentionally limited to the subset of information needed for:
- note-level pitch and timing extraction
- measure-time key signature extraction

It is used on the research data path so label extraction does not depend on a
binary SciPy stack.
"""

from __future__ import annotations

import math
import os
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, List, Optional, Tuple


STEP_TO_SEMITONE = {
    'C': 0,
    'D': 2,
    'E': 4,
    'F': 5,
    'G': 7,
    'A': 9,
    'B': 11,
}


def _namespace(tag: str) -> str:
    if tag.startswith('{'):
        return tag.split('}', 1)[0][1:]
    return ''


def _qname(namespace: str, tag: str) -> str:
    return f'{{{namespace}}}{tag}' if namespace else tag


def _load_root(score_path: str) -> ET.Element:
    if score_path.lower().endswith('.mxl'):
        try:
            with zipfile.ZipFile(score_path, 'r') as archive:
                xml_name = None
                if 'META-INF/container.xml' in archive.namelist():
                    container_root = ET.fromstring(archive.read('META-INF/container.xml'))
                    namespace = _namespace(container_root.tag)
                    rootfile = container_root.find(f'.//{_qname(namespace, "rootfile")}')
                    if rootfile is not None:
                        xml_name = rootfile.attrib.get('full-path')
                if xml_name is None:
                    for name in archive.namelist():
                        if name.lower().endswith(('.xml', '.musicxml')):
                            xml_name = name
                            break
                if xml_name is None:
                    raise FileNotFoundError(f'No XML score found inside {score_path}')
                return ET.fromstring(archive.read(xml_name))
        except zipfile.BadZipFile:
            pass

    with open(score_path, 'rb') as handle:
        return ET.fromstring(handle.read())


def _get_text(node: Optional[ET.Element], namespace: str, tag: str, default: Optional[str] = None) -> Optional[str]:
    if node is None:
        return default
    child = node.find(_qname(namespace, tag))
    if child is None or child.text is None:
        return default
    return child.text


def _pitch_to_midi(note_node: ET.Element, namespace: str) -> Optional[int]:
    pitch = note_node.find(_qname(namespace, 'pitch'))
    if pitch is None:
        return None

    step = _get_text(pitch, namespace, 'step')
    octave_text = _get_text(pitch, namespace, 'octave')
    alter_text = _get_text(pitch, namespace, 'alter', '0')
    if step is None or octave_text is None:
        return None

    semitone = STEP_TO_SEMITONE[step] + int(float(alter_text))
    octave = int(octave_text)
    return (octave + 1) * 12 + semitone


# Krumhansl-Kessler key profiles (Krumhansl, 1990, Table 2.1)
_KK_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_KK_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def _pearson(x: List[float], y: List[float]) -> float:
    """Pearson correlation between two equal-length lists."""
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if std_x < 1e-12 or std_y < 1e-12:
        return 0.0
    return cov / (std_x * std_y)


def _infer_mode_from_notes(note_pitches: List[int], fifths: int) -> str:
    """Infer major/minor mode using Krumhansl-Kessler profile correlation.

    When the MusicXML <mode> element is absent, the key signature is ambiguous
    between the major key and its relative minor.  This function builds a
    pitch-class histogram from the note MIDI pitches, rotates it to align
    with the tonic implied by the fifths value, and correlates against the
    Krumhansl-Kessler major and minor profiles to determine the most likely
    mode.

    Args:
        note_pitches: MIDI pitch numbers (0-127) for notes in the key region.
        fifths: Key signature fifths value (positive = sharps, negative = flats).

    Returns:
        'major' or 'minor'.
    """
    if len(note_pitches) < 4:
        return 'major'  # too few notes for reliable inference

    # Build pitch-class histogram
    histogram = [0.0] * 12
    for p in note_pitches:
        histogram[p % 12] += 1.0

    # Tonic pitch class from fifths (circle of fifths: each fifth adds 7 semitones)
    major_tonic_pc = (fifths * 7) % 12

    # Rotate histogram so tonic aligns at index 0
    rotated_major = histogram[major_tonic_pc:] + histogram[:major_tonic_pc]
    corr_major = _pearson(rotated_major, _KK_MAJOR)

    # Relative minor tonic is 3 semitones below major tonic
    minor_tonic_pc = (major_tonic_pc - 3) % 12
    rotated_minor = histogram[minor_tonic_pc:] + histogram[:minor_tonic_pc]
    corr_minor = _pearson(rotated_minor, _KK_MINOR)

    return 'minor' if corr_minor > corr_major else 'major'


def parse_musicxml_score(score_path: str) -> Dict[str, object]:
    root = _load_root(score_path)
    namespace = _namespace(root.tag)
    part = root.find(_qname(namespace, 'part'))
    if part is None:
        raise ValueError(f'No part found in score: {score_path}')

    notes: List[Dict[str, object]] = []
    key_changes: List[Dict[str, object]] = []

    divisions = 1
    global_measure_start = 0.0
    current_fifths = 0
    current_mode: Optional[str] = None  # None signals mode is unspecified

    for measure_index, measure in enumerate(part.findall(_qname(namespace, 'measure'))):
        measure_position = 0.0
        measure_max_position = 0.0
        last_note_onset = None

        for child in list(measure):
            child_tag = child.tag.split('}', 1)[-1]

            if child_tag == 'attributes':
                divisions_text = _get_text(child, namespace, 'divisions')
                if divisions_text is not None:
                    divisions = max(1, int(float(divisions_text)))

                key_node = child.find(_qname(namespace, 'key'))
                if key_node is not None:
                    fifths = int(_get_text(key_node, namespace, 'fifths', '0'))
                    mode = _get_text(key_node, namespace, 'mode', None)  # None if <mode> absent
                    if not key_changes or key_changes[-1]['fifths'] != fifths or key_changes[-1]['mode'] != mode:
                        key_changes.append(
                            {
                                'onset_div': global_measure_start + measure_position,
                                'measure_index': measure_index,
                                'fifths': fifths,
                                'mode': mode,
                            }
                        )
                    current_fifths = fifths
                    current_mode = mode

            elif child_tag == 'backup':
                duration_text = _get_text(child, namespace, 'duration', '0')
                measure_position = max(0.0, measure_position - int(float(duration_text)))

            elif child_tag == 'forward':
                duration_text = _get_text(child, namespace, 'duration', '0')
                measure_position += int(float(duration_text))
                measure_max_position = max(measure_max_position, measure_position)

            elif child_tag == 'note':
                is_chord = child.find(_qname(namespace, 'chord')) is not None
                is_rest = child.find(_qname(namespace, 'rest')) is not None
                duration_text = _get_text(child, namespace, 'duration', '0')
                duration_div = int(float(duration_text))

                onset_in_measure = last_note_onset if is_chord and last_note_onset is not None else measure_position
                onset_div = global_measure_start + onset_in_measure

                if not is_rest:
                    midi_pitch = _pitch_to_midi(child, namespace)
                    if midi_pitch is not None:
                        notes.append(
                            {
                                'pitch': midi_pitch,
                                'measure_index': measure_index,
                                'onset_div': onset_div,
                                'onset_beat': onset_in_measure / divisions,
                                'duration_div': duration_div,
                                'duration_beat': duration_div / divisions,
                                'fifths': current_fifths,
                                'mode': current_mode,
                            }
                        )

                if not is_chord:
                    last_note_onset = onset_in_measure
                    measure_position += duration_div
                    measure_max_position = max(measure_max_position, measure_position)

        global_measure_start += measure_max_position

    if not key_changes:
        key_changes.append(
            {
                'onset_div': 0.0,
                'measure_index': 0,
                'fifths': 0,
                'mode': None,  # will be resolved by heuristic below
            }
        )

    # --- Two-pass mode resolution ---
    # For any key region where mode is None (MusicXML omitted <mode>),
    # collect note pitches in that region and infer mode via K-K profiles.
    for kc_idx, kc in enumerate(key_changes):
        if kc['mode'] is not None:
            continue
        # Determine the onset range for this key region
        region_start = kc['onset_div']
        region_end = (
            key_changes[kc_idx + 1]['onset_div']
            if kc_idx + 1 < len(key_changes)
            else float('inf')
        )
        # Collect pitches of notes in this region
        region_pitches = [
            n['pitch']
            for n in notes
            if region_start <= n['onset_div'] < region_end
        ]
        inferred_mode = _infer_mode_from_notes(region_pitches, kc['fifths'])
        kc['mode'] = inferred_mode

    # Update note mode fields to match resolved key regions
    kc_idx = 0
    for note in notes:
        while (
            kc_idx + 1 < len(key_changes)
            and note['onset_div'] >= key_changes[kc_idx + 1]['onset_div']
        ):
            kc_idx += 1
        note['mode'] = key_changes[kc_idx]['mode']

    return {
        'notes': notes,
        'key_changes': key_changes,
    }
