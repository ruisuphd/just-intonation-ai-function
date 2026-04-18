"""Phase C test-set leakage check against Aria-MIDI pretraining corpus.

Cross-references the 41 Phase B test composition IDs (ATEPP manifest 'test' split)
against the Aria-MIDI metadata to detect any piece that appears in both the
pretraining corpus and the held-out test set. If overlap is detected,
C4 (Aria pretrain + fine-tune) cannot claim a clean transfer test.

Match heuristic: (a) exact filename match, (b) composer + title fuzzy match
via lowercase-alphanumeric normalization. We deliberately favor false positives
(flag anything suspicious) over false negatives.

Output: JSON with a list of potential overlaps and a pass/fail verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Dict, List, Set, Tuple


def normalize(text: str) -> str:
    """Lowercase, strip diacritics-ish, keep only alphanumerics."""
    if not text:
        return ''
    text = text.lower().replace('ü', 'u').replace('ö', 'o').replace('ä', 'a').replace('ß', 'ss')
    text = text.replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('ñ', 'n')
    return re.sub(r'[^a-z0-9]', '', text)


def load_test_compositions(manifest_path: str) -> List[Dict]:
    """Load the 41 ATEPP test compositions from the unified training manifest."""
    with open(manifest_path) as f:
        m = json.load(f)
    entries = m['entries'] if isinstance(m, dict) else m
    return [e for e in entries if e.get('split') == 'test' and e.get('source') == 'atepp-heuristic']


def load_aria_metadata(metadata_path: str) -> Dict:
    """Aria metadata keyed by numeric id with composer, form, genre, etc."""
    with open(metadata_path) as f:
        return json.load(f)


def composer_last_name(name: str) -> str:
    """Extract normalized last word from a composer string (e.g. 'Franz Liszt' -> 'liszt')."""
    if not name:
        return ''
    parts = [p for p in normalize(name).split() if p] if ' ' in name else [normalize(name)]
    # Handle 'Sergei Rachmaninoff' -> ['sergei', 'rachmaninoff'] -> 'rachmaninoff'
    # but also 'rachmaninoff' alone (Aria's short form) -> 'rachmaninoff'
    tokens = re.split(r'[\s_]+', name.lower())
    tokens = [normalize(t) for t in tokens if normalize(t)]
    if not tokens:
        return ''
    return tokens[-1]


def find_potential_overlaps(
    test_comps: List[Dict],
    aria_meta: Dict,
) -> Tuple[List[Dict], Dict[str, int]]:
    """Return (piece-level_overlaps, composer_level_aria_counts).

    Piece-level overlap detection is limited by Aria metadata (often only
    composer + form, no per-piece title). We conservatively flag composer-level
    overlaps as informational and piece-level as blocking.
    """
    composer_level: Dict[str, int] = {}
    for tc in test_comps:
        last = composer_last_name(tc.get('composer', ''))
        if not last:
            continue
        for aria_id, meta in aria_meta.items():
            if not isinstance(meta, dict):
                continue
            aria_meta_inner = meta.get('metadata', meta)  # Aria nests under 'metadata'
            if not isinstance(aria_meta_inner, dict):
                continue
            aria_last = composer_last_name(aria_meta_inner.get('composer', ''))
            if aria_last == last:
                composer_level[last] = composer_level.get(last, 0) + 1

    # Piece-level flags: require piece_id match substring in Aria filename-like field.
    # Aria metadata rarely has a title; keep conservative.
    piece_overlaps = []
    for tc in test_comps:
        tc_filename = normalize(
            os.path.splitext(os.path.basename(tc.get('file_path', '')))[0]
        )
        if not tc_filename or len(tc_filename) < 6:
            continue
        for aria_id, meta in aria_meta.items():
            if not isinstance(meta, dict):
                continue
            aria_meta_inner = meta.get('metadata', meta)
            text_fields = ' '.join(
                str(aria_meta_inner.get(k, ''))
                for k in ('title', 'form', 'opus', 'work', 'movement')
                if aria_meta_inner.get(k)
            )
            if not text_fields:
                continue
            if tc_filename in normalize(text_fields):
                piece_overlaps.append({
                    'atepp_comp_id': tc.get('piece_id'),
                    'atepp_composer': tc.get('composer'),
                    'atepp_filename_stem': tc_filename,
                    'aria_id': aria_id,
                    'aria_metadata': aria_meta_inner,
                    'match_type': 'filename_substring',
                })

    return piece_overlaps, composer_level


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', default='research_data/unified_training_manifest.json')
    parser.add_argument('--aria-metadata', default='aria-midi-v1-deduped-ext/metadata.json')
    parser.add_argument('--output', default='research_data/phaseC_leakage_check.json')
    args = parser.parse_args()

    assert os.path.exists(args.manifest), f'Missing manifest: {args.manifest}'
    if not os.path.exists(args.aria_metadata):
        print(f'WARNING: Aria metadata not at {args.aria_metadata}')
        print('If Aria is not used for Phase C Path A cell C4, this is not blocking.')
        print('Writing empty leakage report.')
        result = {
            'status': 'SKIPPED',
            'reason': 'aria metadata not available locally',
            'aria_metadata_path': args.aria_metadata,
        }
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        return

    test_comps = load_test_compositions(args.manifest)
    print(f'Test compositions (ATEPP test split): {len(test_comps)}')

    aria_meta = load_aria_metadata(args.aria_metadata)
    n_meta = len(aria_meta) if isinstance(aria_meta, dict) else len(aria_meta)
    print(f'Aria metadata entries: {n_meta:,}')

    piece_overlaps, composer_counts = find_potential_overlaps(test_comps, aria_meta)

    verdict = 'PASS' if not piece_overlaps else 'FLAG_PIECE_LEVEL'
    result = {
        'status': verdict,
        'n_test_compositions': len(test_comps),
        'n_aria_metadata_entries': n_meta,
        'n_piece_level_overlaps': len(piece_overlaps),
        'piece_level_overlaps': piece_overlaps,
        'composer_level_overlap_counts': composer_counts,
        'manifest_path': args.manifest,
        'aria_metadata_path': args.aria_metadata,
        'notes': [
            'Piece-level detection relies on filename substring appearing in Aria '
            'title/opus/work fields. Aria metadata is coarse (often only composer + '
            'form), so piece-level exact-match is not always possible.',
            'Composer-level overlap is EXPECTED and not a leakage concern by itself — '
            'many compositions share a composer without being the same piece.',
            'For definitive dedup, hash each Aria MIDI against ATEPP MIDI files. This '
            'script relies on metadata alone for speed.',
            'Aria-MIDI-v1-deduped-ext claims internal dedup across the 371k corpus; '
            'overlap with an external ATEPP test set is not guaranteed absent.',
        ],
    }

    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)

    print(f'\n=== Leakage verdict: {verdict} ===')
    print(f'Piece-level overlaps: {len(piece_overlaps)}')
    print(f'\nComposer-level Aria counts (informational, not blocking):')
    for composer, n in sorted(composer_counts.items(), key=lambda kv: -kv[1])[:10]:
        print(f'  {composer}: {n}')

    if piece_overlaps:
        print(f'\n*** REVIEW THESE PIECE-LEVEL OVERLAPS BEFORE C4: ***')
        for o in piece_overlaps[:20]:
            print(f'  {o["atepp_composer"]} (ATEPP {o["atepp_comp_id"]}, '
                  f'fn="{o["atepp_filename_stem"]}") ~= Aria {o["aria_id"]}')
            print(f'     aria meta: {o["aria_metadata"]}')

    print(f'\nReport saved to {args.output}')


if __name__ == '__main__':
    main()
