#!/usr/bin/env python3
"""POP909 ingestion adapter — Phase I cross-corpus generalisation.

POP909 is a corpus of 909 pop songs with melody / bridge / piano tracks
plus chord, beat, and key annotations. Reference:

    Wang, Z., Chen, K., Jiang, J., Zhang, Y., Xu, M., Dai, S., Bin, G.,
    & Xia, G. (2020). POP909: A Pop-song Dataset for Music Arrangement
    Generation. ISMIR 2020.

Per-song directory layout (verified 2026-05-02):
    POP909/<NNN>/<NNN>.mid          MIDI: tracks MELODY / BRIDGE / PIANO
    POP909/<NNN>/chord_midi.txt     start_sec\tend_sec\thart_label
    POP909/<NNN>/chord_audio.txt    same, audio-aligned timestamps
    POP909/<NNN>/key_audio.txt      start_sec\tend_sec\tharte_key
    POP909/<NNN>/beat_midi.txt      time_sec beat_in_bar downbeat
    POP909/<NNN>/beat_audio.txt
    POP909/<NNN>/versions/

POP909 conventions:
  - Time stamps in seconds throughout. We convert to beats using the
    MIDI tempo (single tempo event per song; constant within song).
  - Chord labels in Harte notation: 'C:maj', 'A:min', 'G:7', 'N' for none.
  - Key annotation in `key_audio.txt`: one or more (start_sec, end_sec,
    harte_key) segments per song. POP909 songs are mostly tonally stable;
    a small fraction modulate (e.g., song 010 has G:maj → F:min).
  - We ASSIGN per-note key from the key segments (per-note, not per-song),
    so modulating songs are handled correctly.

We merge the MELODY + BRIDGE + PIANO tracks into a single note stream
(equivalent to what an audio-domain key detector would receive). The
combined stream gives the model the full harmonic content.

Output JSON shape (matches the project's canonical Strategy A schema):
  {
    "id": "POP909_<song_id>",
    "source": "pop909",
    "converter_strategy": "A",
    "notes": [
      {"pitch": int_midi, "onset_beat": float, "duration_beat": float,
       "velocity": int, "key": str, "tonic_pc": int, "is_minor": bool,
       "chord_numeral": "", "chord_type": str,
       "chord_relativeroot": null, "chord_root_pc": int}
    ]
  }

Author: Rui Su, 2026-05-02. Phase I Month 2 cross-corpus adapter.
Verified end-to-end against the 909-song dataset locally before zip.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from bisect import bisect_right
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Pitch-class lookup (Harte-style names)
PC_LOOKUP = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'Fb': 4, 'F': 5, 'E#': 5, 'F#': 6, 'Gb': 6,
    'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10,
    'B': 11, 'Cb': 11,
}
PC_TO_NAME = {0: 'C', 1: 'C#', 2: 'D', 3: 'D#', 4: 'E', 5: 'F',
              6: 'F#', 7: 'G', 8: 'G#', 9: 'A', 10: 'A#', 11: 'B'}

# Krumhansl-Kessler profiles for fallback key inference (when key_audio.txt
# is empty or unparseable). Project keeps the same profiles as
# evaluate_classical_baseline.py for consistency.
KK_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
            2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KK_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
            2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


# ─────────────────────────────────────────────────────────────────────────
# Harte chord-label parsing

HARTE_CHORD_RE = re.compile(r'^([A-G][#b]?)(?::(\w+))?(?:\(([^)]*)\))?(?:/(\d+))?$')


def parse_harte_chord(label: str) -> Optional[Dict[str, Any]]:
    """Parse a Harte-format chord label. Returns root_pc + chord_type, or None."""
    label = label.strip()
    if not label or label.lower() in ('n', 'x', 'n.c.'):
        return None
    m = HARTE_CHORD_RE.match(label)
    if not m:
        return None
    root_name = m.group(1)
    quality = (m.group(2) or 'maj').lower()
    if root_name not in PC_LOOKUP:
        return None
    return {
        'root_pc': PC_LOOKUP[root_name],
        'chord_type': quality,
        'is_minor_chord': quality.startswith('min'),
    }


def parse_harte_key(label: str) -> Optional[Tuple[str, int, bool]]:
    """Parse a Harte-format key label like 'Gb:maj' or 'F:min' →
    (canonical_key_string, tonic_pc, is_minor). Returns None on parse error."""
    label = label.strip()
    if not label:
        return None
    if ':' in label:
        root, mode = label.split(':', 1)
    else:
        root, mode = label, 'maj'
    root = root.strip()
    mode = mode.strip().lower()
    if root not in PC_LOOKUP:
        return None
    tonic_pc = PC_LOOKUP[root]
    is_minor = mode.startswith('min')
    canonical = root + ('m' if is_minor else '')
    return (canonical, tonic_pc, is_minor)


# ─────────────────────────────────────────────────────────────────────────
# File readers

def _read_chord_midi(chord_file: Path) -> List[Dict[str, Any]]:
    """Read POP909 chord_midi.txt (start_sec\\tend_sec\\thart_label)."""
    chords: List[Dict[str, Any]] = []
    with open(chord_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t') if '\t' in line else line.split()
            if len(parts) < 3:
                continue
            try:
                start = float(parts[0])
                end = float(parts[1])
            except ValueError:
                continue
            label = ' '.join(parts[2:])
            parsed = parse_harte_chord(label)
            if parsed is None:
                continue
            chords.append({
                'start_sec': start, 'end_sec': end, 'label': label,
                **parsed,
            })
    chords.sort(key=lambda c: c['start_sec'])
    return chords


def _read_key_audio(key_file: Path) -> List[Dict[str, Any]]:
    """Read key_audio.txt — list of (start_sec, end_sec, key_label) segments."""
    segs: List[Dict[str, Any]] = []
    with open(key_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t') if '\t' in line else line.split()
            if len(parts) < 3:
                continue
            try:
                start = float(parts[0])
                end = float(parts[1])
            except ValueError:
                continue
            label = ' '.join(parts[2:])
            parsed = parse_harte_key(label)
            if parsed is None:
                continue
            canonical, tonic_pc, is_minor = parsed
            segs.append({
                'start_sec': start, 'end_sec': end,
                'key': canonical, 'tonic_pc': tonic_pc, 'is_minor': is_minor,
                'label': label,
            })
    segs.sort(key=lambda s: s['start_sec'])
    return segs


def _kk_key_finding(pitch_class_histogram: List[float]) -> Tuple[str, int, bool]:
    """Krumhansl-Kessler correlation key-finding fallback."""
    if sum(pitch_class_histogram) <= 0:
        return ('C', 0, False)

    def pearson(x, y):
        n = len(x); mx, my = sum(x) / n, sum(y) / n
        num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
        denx = sum((xi - mx) ** 2 for xi in x) ** 0.5
        deny = sum((yi - my) ** 2 for yi in y) ** 0.5
        return num / (denx * deny + 1e-12)

    h = pitch_class_histogram
    best_score = -2.0
    best = ('C', 0, False)
    for tonic in range(12):
        rotated = h[tonic:] + h[:tonic]
        s_maj = pearson(rotated, KK_MAJOR)
        s_min = pearson(rotated, KK_MINOR)
        if s_maj > best_score:
            best_score, best = s_maj, (PC_TO_NAME[tonic], tonic, False)
        if s_min > best_score:
            best_score, best = s_min, (f'{PC_TO_NAME[tonic]}m', tonic, True)
    return best


def _read_pop909_midi_to_notes(midi_file: Path) -> Tuple[List[Dict[str, Any]], float]:
    """Extract note events from a POP909 MIDI file.

    Returns (notes, beat_duration_sec) where each note has
    onset_sec / duration_sec / pitch / velocity, plus the beat-duration
    so the caller can convert to beats.
    """
    try:
        import mido  # type: ignore
    except ImportError as e:
        raise RuntimeError('mido required: pip install mido') from e

    mid = mido.MidiFile(str(midi_file))
    tpb = mid.ticks_per_beat
    # Get first tempo event (POP909 songs are constant tempo per the README).
    tempo_us = 500_000  # MIDI default
    for tr in mid.tracks:
        for msg in tr:
            if msg.type == 'set_tempo':
                tempo_us = msg.tempo
                break
        else:
            continue
        break
    beat_duration_sec = tempo_us / 1e6
    sec_per_tick = beat_duration_sec / tpb

    # Track-merge: gather (abs_tick, msg) pairs, separately per track so
    # absolute-time conversion is correct (delta times are per-track).
    notes: List[Dict[str, Any]] = []
    for tr_idx, tr in enumerate(mid.tracks):
        track_name = tr.name or f'track_{tr_idx}'
        # Skip empty / non-note tracks (POP909 has an empty track 0)
        if not any(m.type == 'note_on' and m.velocity > 0 for m in tr):
            continue
        abs_tick = 0
        open_notes: Dict[int, Tuple[int, int]] = {}  # pitch → (start_tick, vel)
        for msg in tr:
            abs_tick += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                open_notes[msg.note] = (abs_tick, msg.velocity)
            elif (msg.type == 'note_off') or \
                 (msg.type == 'note_on' and msg.velocity == 0):
                if msg.note in open_notes:
                    start_tick, vel = open_notes.pop(msg.note)
                    onset_sec = start_tick * sec_per_tick
                    duration_sec = max(0.05,
                                       (abs_tick - start_tick) * sec_per_tick)
                    notes.append({
                        'pitch': int(msg.note),
                        'onset_sec': float(onset_sec),
                        'duration_sec': float(duration_sec),
                        'velocity': int(vel),
                        'track': track_name,
                    })
    notes.sort(key=lambda n: n['onset_sec'])
    return notes, beat_duration_sec


def _attach_chord_and_key_to_pop909_notes(
    notes: List[Dict[str, Any]],
    chords: List[Dict[str, Any]],
    keys: List[Dict[str, Any]],
    beat_duration_sec: float,
    fallback_key: Tuple[str, int, bool],
) -> List[Dict[str, Any]]:
    """For each POP909 note, attach the active chord + the active key segment.

    Uses the seconds-domain timestamps from chord_midi.txt and key_audio.txt
    directly, then converts the note onset to BEATS at the end (using the
    constant beat_duration_sec). Notes outside any chord segment are
    dropped, consistent with the Strategy-A behaviour.
    """
    if not notes or not chords:
        return []
    chord_starts = [c['start_sec'] for c in chords]
    key_starts = [k['start_sec'] for k in keys] if keys else []
    out: List[Dict[str, Any]] = []
    for n in notes:
        # Active chord at note onset
        idx = bisect_right(chord_starts, n['onset_sec']) - 1
        if idx < 0:
            continue
        c = chords[idx]
        if n['onset_sec'] >= c['end_sec']:
            continue
        # Active key segment at note onset; fall back to KK-derived global
        # key if no segment covers this time.
        key_str, tonic_pc, is_minor = fallback_key
        if keys:
            kidx = bisect_right(key_starts, n['onset_sec']) - 1
            if kidx >= 0 and n['onset_sec'] < keys[kidx]['end_sec']:
                k = keys[kidx]
                key_str, tonic_pc, is_minor = k['key'], k['tonic_pc'], k['is_minor']
        # Convert to beats
        onset_beat = n['onset_sec'] / max(1e-6, beat_duration_sec)
        duration_beat = n['duration_sec'] / max(1e-6, beat_duration_sec)
        out.append({
            'pitch': n['pitch'],
            'onset_beat': float(onset_beat),
            'duration_beat': float(duration_beat),
            'velocity': n['velocity'],
            'key': key_str,
            'tonic_pc': tonic_pc,
            'is_minor': is_minor,
            'chord_numeral': '',  # POP909 uses Harte not Roman; left blank
            'chord_type': c['chord_type'],
            'chord_relativeroot': None,
            'chord_root_pc': c['root_pc'],
        })
    return out


def convert_one_song(song_dir: Path, output_dir: Path) -> Optional[Path]:
    """Convert one POP909 song directory to a Strategy-A-compatible JSON."""
    song_id = song_dir.name  # '001'
    midi_files = list(song_dir.glob('*.mid'))
    chord_file = song_dir / 'chord_midi.txt'
    key_file = song_dir / 'key_audio.txt'
    if not midi_files or not chord_file.exists():
        logger.info('skipping %s: missing midi or chord_midi.txt', song_id)
        return None

    # Pick the song MIDI (not any version-MIDI under versions/)
    midi_file = sorted(midi_files)[0]

    try:
        notes, beat_duration_sec = _read_pop909_midi_to_notes(midi_file)
    except Exception as e:  # noqa: BLE001
        logger.warning('skipping %s: midi parse failed: %s', song_id, e)
        return None
    chords = _read_chord_midi(chord_file)
    if not notes or not chords:
        return None

    # Read key_audio.txt if present; otherwise infer via KK on chord-root histogram.
    keys: List[Dict[str, Any]] = []
    if key_file.exists():
        keys = _read_key_audio(key_file)
    fallback_hist = [0.0] * 12
    for c in chords:
        dur = max(0.0, c['end_sec'] - c['start_sec'])
        fallback_hist[c['root_pc']] += dur if dur > 0 else 1.0
    fallback_key = _kk_key_finding(fallback_hist)

    paired = _attach_chord_and_key_to_pop909_notes(
        notes, chords, keys, beat_duration_sec, fallback_key,
    )
    if not paired:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f'POP909_{song_id}.json'
    payload = {
        'id': f'POP909_{song_id}',
        'source': 'pop909',
        'converter_strategy': 'A',
        'reference': 'Wang Z. et al. (2020), POP909, ISMIR 2020',
        'beat_duration_sec_at_constant_tempo': beat_duration_sec,
        'has_native_key_annotation': bool(keys),
        'fallback_key_kk': {
            'key': fallback_key[0], 'tonic_pc': fallback_key[1],
            'is_minor': fallback_key[2],
        },
        'notes': paired,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True, help='POP909 root directory')
    ap.add_argument('--output', required=True, help='Output dir for per-song JSONs')
    ap.add_argument('--limit', type=int, default=0,
                    help='Process only the first N songs (default: all)')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(levelname)s %(message)s',
    )

    in_root = Path(args.input).expanduser().resolve()
    out_root = Path(args.output).expanduser().resolve()
    if not in_root.is_dir():
        print(f'ERROR: input dir does not exist: {in_root}')
        return 1

    song_dirs = sorted(p for p in in_root.iterdir()
                       if p.is_dir() and p.name.isdigit())
    if args.limit > 0:
        song_dirs = song_dirs[:args.limit]
    out_root.mkdir(parents=True, exist_ok=True)

    n_ok, n_skip, n_with_key = 0, 0, 0
    for song_dir in song_dirs:
        result = convert_one_song(song_dir, out_root)
        if result is None:
            n_skip += 1
        else:
            n_ok += 1
            if (out_root / result.name).exists():
                d = json.loads(result.read_text())
                if d.get('has_native_key_annotation'):
                    n_with_key += 1
            if n_ok % 50 == 0:
                print(f'  ... {n_ok} songs converted')
    print(f'POP909: converted {n_ok} songs ({n_with_key} with native key annotation), '
          f'skipped {n_skip}')
    print(f'Output: {out_root}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
