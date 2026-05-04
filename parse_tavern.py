#!/usr/bin/env python3
"""TAVERN ingestion adapter (Theme-and-Variations corpus).

TAVERN (deWaard, 2009; Devaney, Arthur, Condit-Schultz, & Nisula, 2015)
is 27 sets of theme-and-variations for piano: 17 by Beethoven (B065–B080,
Opus34, Opus76; ~181 variations total) and 10 by Mozart (K025–K613;
~100 variations total). The corpus splits each variation into phrases;
each phrase is encoded in Humdrum **kern format with parallel
**function (functional analysis) + **harm (Roman numeral) + **kern × 2
(left-hand + right-hand notes) streams.

Reference:
    Devaney, J., Arthur, C., Condit-Schultz, N., & Nisula, K. (2015).
    Theme And Variation Encodings with Roman Numerals (TAVERN): A new
    data set for symbolic music analysis. Proceedings of ISMIR 2015,
    728-734.

Per-piece file layout:
    TAVERN-master/{Composer}/{Opus}/Joined/{Opus}_{var:02d}_{phrase:02d}{content_letter}_{annotator}.krn

Phrase id structure:
    BO34_00_01a_a.krn = Beethoven Opus 34, Theme (variation 00),
                       phrase 01, content letter 'a', annotator A.

For symbolic-key-finding we use the **kern stream's note events + the
*key directive (e.g. *F:) for the local key annotation. Roman numeral
annotations are ignored (TAVERN's Roman numerals are at the phrase
level, not per-event, so they don't add fine-grained chord supervision
over what we already get from BPS-FH).

Output JSON shape (matches the project's canonical Strategy A schema,
identical to parse_bps_fh.py):
  {
    "id": "TAVERN_BO34_00_01a",
    "source": "tavern",
    "composer": "beethoven",
    "opus": "Opus34",
    "variation": "00",
    "phrase": "01",
    "phrase_letter": "a",
    "converter_strategy": "A",
    "notes": [
      {"pitch": int_midi, "onset_beat": float, "duration_beat": float,
       "velocity": int, "key": "F" | "Fm" | ..., "tonic_pc": int,
       "is_minor": bool, "chord_numeral": str, "chord_type": str,
       "chord_relativeroot": null, "chord_root_pc": int}
    ]
  }

Author: Rui Su, 2026-05-09. TAVERN ingestion for the σ-collapse paper +
the modulating-subset secondary test (rigour plan §3 Tier 2.3).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Pitch-class lookup (Humdrum: lowercase = octave 4+; uppercase = octave 3-)
NOTE_LETTER_PC = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}


# ─────────────────────────────────────────────────────────────────────────
# Humdrum **kern note parsing
#
# A kern token is e.g. "8cc" (eighth-note middle-C-octave c), "4f#" (quarter
# F-sharp), "16AAA" (sixteenth A1), "(4f cc)" (chord).
# Format reference: https://www.humdrum.org/Humdrum/representations/kern.html

_DUR_RE = re.compile(r'(\d+)\.*')        # leading digit(s) + optional dots = duration
_PITCH_RE = re.compile(r'([a-gA-G]+)([#-]*)(?:[/\\nq])?')  # pitch letter(s) + accidentals
_REST_RE = re.compile(r'^[^a-gA-G]*r')   # 'r' anywhere after duration = rest
_GRACE_RE = re.compile(r'q')             # grace note marker

_FLAGS_TO_SKIP = ('=', '!', '*', '.')    # bar/comment/interpretation/null tokens


def _kern_pitch_to_midi(letters: str, accidentals: str) -> Optional[int]:
    """Convert a Humdrum kern pitch token to a MIDI number.

    letters = repeated letter encoding octave + class:
      - 'c'    = C4 (middle C; MIDI 60)
      - 'cc'   = C5
      - 'C'    = C3
      - 'CC'   = C2
    accidentals: '#' raises by 1 semitone (per #), '-' lowers by 1 (per -).
    """
    if not letters:
        return None
    base_letter = letters[0].lower()
    pc = NOTE_LETTER_PC.get(base_letter)
    if pc is None:
        return None
    # Octave: lower-case letters octave 4+ (with each repeat adding +12),
    #         upper-case letters octave 3- (with each repeat adding -12).
    if letters[0].islower():
        octave = 4 + (len(letters) - 1)
    else:
        octave = 3 - (len(letters) - 1)
    midi = (octave + 1) * 12 + pc
    # Accidentals
    for ch in accidentals:
        if ch == '#':
            midi += 1
        elif ch == '-':
            midi -= 1
    if midi < 0 or midi > 127:
        return None
    return midi


def _parse_kern_token(token: str) -> List[Dict[str, Any]]:
    """Parse a single kern token (which may contain multiple notes for a chord).

    Returns a list of note dicts: [{'pitch': int_midi, 'duration_beat': float}]
    Returns [] for rests, grace notes, ties continuations, and unparsable tokens.
    """
    if not token or token in _FLAGS_TO_SKIP:
        return []
    # Some tokens have prefix flags like '(' or accent markers — strip them.
    tok = token.lstrip('(').rstrip(')').strip()
    if not tok or tok[0] in _FLAGS_TO_SKIP:
        return []

    # Chord = space-separated sub-tokens within the same kern column
    sub_tokens = tok.split(' ')
    notes: List[Dict[str, Any]] = []
    for sub in sub_tokens:
        sub = sub.strip()
        if not sub:
            continue
        # Skip rests
        if 'r' in sub.lower() and not any(c.isalpha() and c not in 'r' for c in sub):
            continue
        # Skip grace notes
        if _GRACE_RE.search(sub):
            continue
        # Duration
        m_dur = _DUR_RE.match(sub)
        if not m_dur:
            continue
        n_dur = int(m_dur.group(1))
        if n_dur <= 0:
            continue
        # Recurrence dots: each '.' multiplies duration by 1.5 cumulatively
        # (Humdrum convention). Approximation: count dots after the digits.
        dots = 0
        idx = m_dur.end()
        while idx < len(sub) and sub[idx] == '.':
            dots += 1
            idx += 1
        # Duration in beats: 4/n_dur (where 4=quarter=1 beat)
        beat_value = 4.0 / n_dur
        for _ in range(dots):
            beat_value *= 1.5
        # Pitch
        m_pitch = _PITCH_RE.search(sub[idx:])
        if not m_pitch:
            continue
        pitch = _kern_pitch_to_midi(m_pitch.group(1), m_pitch.group(2))
        if pitch is None:
            continue
        notes.append({'pitch': pitch, 'duration_beat': beat_value})
    return notes


# ─────────────────────────────────────────────────────────────────────────
# Local-key parsing
#
# Humdrum *key directives use the convention:
#   *F:    = F major
#   *f:    = F minor
#   *F#:   = F# major
#   *f#:   = F# minor
#   *F-:   = F-flat major
#   *f-:   = F-flat minor
# (The trailing colon is mandatory.)

def _parse_humdrum_key(directive: str) -> Optional[Tuple[str, int, bool]]:
    """Parse a *key: directive into (canonical_key_string, tonic_pc, is_minor).

    Returns None if not a valid *key directive.
    """
    s = directive.strip().rstrip(':').lstrip('*').strip()
    if not s or len(s) > 4:
        return None
    letter = s[0]
    # NOTE_LETTER_PC has lowercase keys. The case of `letter` itself encodes
    # the mode (uppercase = major, lowercase = minor); look up by lowercase.
    if letter.lower() not in NOTE_LETTER_PC:
        return None
    is_minor = letter.islower()
    pc = NOTE_LETTER_PC[letter.lower()]
    accidentals = s[1:]
    canonical_letter = letter.upper()
    canonical_accidental = ''
    for ch in accidentals:
        if ch == '#':
            pc = (pc + 1) % 12
            canonical_accidental += '#'
        elif ch == '-':
            pc = (pc - 1) % 12
            canonical_accidental += 'b'
        else:
            return None
    canonical = canonical_letter + canonical_accidental + ('m' if is_minor else '')
    return canonical, pc, is_minor


# ─────────────────────────────────────────────────────────────────────────
# File reader

def parse_kern_file(path: Path) -> List[Dict[str, Any]]:
    """Parse one TAVERN .krn file into a list of note dicts with key labels.

    Each note dict has: pitch (int MIDI), onset_beat (float, cumulative),
    duration_beat (float), velocity (80, default), key, tonic_pc, is_minor,
    chord_numeral (empty), chord_type (empty), chord_relativeroot (None),
    chord_root_pc (-1).

    Returns [] if the file has no parseable notes.
    """
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except Exception as e:
        logger.warning('skip %s: %s', path, e)
        return []

    notes: List[Dict[str, Any]] = []
    onset_beat = 0.0
    current_key: Optional[Tuple[str, int, bool]] = None
    in_data = False
    n_kern_streams = 0

    for line in lines:
        line = line.rstrip()
        if not line:
            continue
        # Identify column structure: when we see the **kern header, count streams
        if line.startswith('**'):
            cols = line.split('\t')
            n_kern_streams = sum(1 for c in cols if c == '**kern')
            in_data = True
            continue
        # Skip exclusive interpretations / interpretation markers / comments
        if line.startswith('!'):
            continue
        if line.startswith('*'):
            # Interpretation tokens — look for *key: directive on any column
            for col in line.split('\t'):
                key = _parse_humdrum_key(col)
                if key is not None:
                    current_key = key
            continue
        if line.startswith('='):
            # Bar line; do not advance time
            continue
        if not in_data:
            continue

        # Data line: tab-separated, last n_kern_streams columns are kern tokens
        cols = line.split('\t')
        if len(cols) < n_kern_streams:
            continue
        kern_cols = cols[-n_kern_streams:]
        # Find the maximum duration on this line (this is the time advance)
        max_duration = 0.0
        line_notes: List[Dict[str, Any]] = []
        for col in kern_cols:
            sub_notes = _parse_kern_token(col)
            for n in sub_notes:
                line_notes.append(n)
                if n['duration_beat'] > max_duration:
                    max_duration = n['duration_beat']
        # Emit notes with their cumulative onset
        for n in line_notes:
            notes.append({
                'pitch': n['pitch'],
                'onset_beat': onset_beat,
                'duration_beat': n['duration_beat'],
                'velocity': 80,  # TAVERN has no velocity; default
                'key': current_key[0] if current_key else 'C',
                'tonic_pc': current_key[1] if current_key else 0,
                'is_minor': current_key[2] if current_key else False,
                'chord_numeral': '',
                'chord_type': '',
                'chord_relativeroot': None,
                'chord_root_pc': -1,
            })
        onset_beat += max_duration

    return notes


# ─────────────────────────────────────────────────────────────────────────
# Phrase id parsing

_PHRASE_ID_RE = re.compile(
    r'^(?P<opus>[BMOK][a-zA-Z0-9]+)_(?P<var>\d+)_(?P<phrase>\d+)(?P<letter>[a-z])(?:_(?P<annot>[ab]))?\.krn$',
    re.IGNORECASE,
)


def parse_phrase_id(filename: str) -> Optional[Dict[str, str]]:
    """Parse e.g. 'BO34_00_01a_a.krn' or 'BO34_00_01a.krn' → dict."""
    m = _PHRASE_ID_RE.match(filename)
    if not m:
        return None
    return m.groupdict()


# ─────────────────────────────────────────────────────────────────────────
# Driver

def convert_one_phrase(krn_path: Path, output_dir: Path,
                       composer: str, opus: str) -> Optional[Path]:
    """Convert one TAVERN phrase .krn → canonical Strategy-A JSON."""
    notes = parse_kern_file(krn_path)
    if not notes:
        logger.warning('skipping %s: 0 notes parsed', krn_path.name)
        return None
    pid = parse_phrase_id(krn_path.name)
    if not pid:
        logger.warning('skipping %s: bad phrase-id format', krn_path.name)
        return None
    phrase_id = f'TAVERN_{opus}_{pid["var"]}_{pid["phrase"]}{pid["letter"]}'
    payload = {
        'id': phrase_id,
        'source': 'tavern',
        'composer': composer,
        'opus': opus,
        'variation': pid['var'],
        'phrase': pid['phrase'],
        'phrase_letter': pid['letter'],
        'converter_strategy': 'A',
        'reference': ('Devaney, J., Arthur, C., Condit-Schultz, N., & '
                      'Nisula, K. (2015). TAVERN: A new data set for '
                      'symbolic music analysis. ISMIR 2015, 728-734.'),
        'notes': notes,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f'{phrase_id}.json'
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True,
                    help='TAVERN-master/ root (with Beethoven/ + Mozart/ subdirs)')
    ap.add_argument('--output', required=True,
                    help='Per-phrase JSON output directory')
    ap.add_argument('--annotator', default='a',
                    help='Annotator label (a or b); we use one annotator per phrase '
                         'for parsimony (the per-event note content is identical '
                         'between annotators; only the function/harm streams differ)')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(levelname)s %(message)s',
    )

    in_root = Path(args.input).expanduser().resolve()
    out_root = Path(args.output).expanduser().resolve()
    if not in_root.is_dir():
        print(f'ERROR: input dir does not exist: {in_root}'); return 1
    out_root.mkdir(parents=True, exist_ok=True)

    n_ok, n_skip = 0, 0
    by_composer = defaultdict(int)
    for composer_dir in sorted(in_root.iterdir()):
        if not composer_dir.is_dir():
            continue
        composer = composer_dir.name.lower()
        if composer not in ('beethoven', 'mozart'):
            continue
        for opus_dir in sorted(composer_dir.iterdir()):
            if not opus_dir.is_dir():
                continue
            joined_dir = opus_dir / 'Joined'
            if not joined_dir.is_dir():
                continue
            # Pick one annotator per phrase
            for path in sorted(joined_dir.iterdir()):
                if path.suffix != '.krn':
                    continue
                # Only take the requested annotator's phrase files
                if not path.stem.endswith(f'_{args.annotator}'):
                    continue
                result = convert_one_phrase(path, out_root, composer, opus_dir.name)
                if result is None:
                    n_skip += 1
                else:
                    n_ok += 1
                    by_composer[composer] += 1
                    if args.verbose:
                        print(f'  ✓ {composer}/{opus_dir.name}/{path.name} → {result.name}')
    print(f'\nTAVERN: converted {n_ok} phrases, skipped {n_skip}')
    print(f'  Beethoven phrases: {by_composer["beethoven"]}')
    print(f'  Mozart phrases:    {by_composer["mozart"]}')
    print(f'  Output: {out_root}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
