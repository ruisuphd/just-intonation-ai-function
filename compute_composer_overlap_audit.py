#!/usr/bin/env python3
"""Composer-overlap audit for cross-corpus evaluation claims.

Closes R2.1 (BPS-FH) + R2.2 (TAVERN) of POSTDOC_REVIEWER_PASS_2026-05-09.md.

Background
----------
Cross-corpus claims like "T6_T1 generalises zero-shot to BPS-FH" can be
challenged on two distinct kinds of leakage:

  (i)  PIECE-LEVEL leakage: same piece (or same composer + same opus +
       same movement number) appears in BOTH the training pool AND the
       cross-corpus test set. This is the strict definition of leakage;
       its presence invalidates a zero-shot claim outright.

  (ii) COMPOSER-LEVEL overlap: the SAME composer is in both training pool
       and test corpus, but DIFFERENT pieces (e.g., Beethoven string
       quartets in training, Beethoven piano sonatas in test). This is
       not strictly leakage but must be disclosed because it weakens the
       "fully out-of-distribution" framing.

This script computes both for any (training_manifest, test_corpus) pair.
For BPS-FH (verified 2026-05-09), it should return: 0 piece-level leaks,
some composer-level overlap (Beethoven via DCML string quartets).

Output
------
  research_data/composer_overlap_audit_2026-05-09.json
  research_data/composer_overlap_audit_2026-05-09.md

Usage
-----
    # Full audit for both BPS-FH and TAVERN (when adapter ships)
    python compute_composer_overlap_audit.py

    # BPS-FH only
    python compute_composer_overlap_audit.py --skip-tavern

    # Specify alternative paths
    python compute_composer_overlap_audit.py \\
        --training-manifest research_data/unified_training_manifest_phase1_clean.json \\
        --bps-fh-dir research_data/bps_fh_score_key_labels \\
        --tavern-root TAVERN-master

Author: Rui Su, 2026-05-09. R2.1 / R2.2 closure script.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


# ─────────────────────────────────────────────────────────────────────────
# Step 1 — reconstruct the actual loaded train set from the unified manifest
#
# A naive "look at the manifest entries" overcounts because the loader
# (train_harmonic_context_model.py:783) skips entries whose label file
# has no `notes` array (e.g., wir_expert annotation-only files).
# Replicate that filter here so the reported overlap matches the model's
# actual training experience.

def reconstruct_loaded_train_pieces(
    manifest_path: Path,
    label_dirs: List[Path],
    splits: Tuple[str, ...] = ('train', 'val'),
) -> List[Dict]:
    """Replicate train_harmonic_context_model.load_records_from_manifest's
    'notes-required' filter and return the records that ACTUALLY get fed
    to the model during training (train) and best-checkpoint selection (val).

    NOTE: the default splits=('train', 'val') intentionally EXCLUDES the
    in-domain test split. For the cross-corpus leakage question — "what
    composers does the trained T6_T1 checkpoint know about?" — only
    train + val matter; test was held out from training. Pass
    splits=('train','val','test') only if you want to include the
    in-domain test composers (e.g., for an ATEPP-41-vs-itself audit).

    Returns a list of dicts with at least: piece_id, composer (parsed),
    op_number (parsed), movement (parsed).
    """
    if not manifest_path.exists():
        raise SystemExit(f'Training manifest not found: {manifest_path}')
    m = json.load(open(manifest_path))

    # Pre-build a filename → absolute-path index over the label dirs
    file_index: Dict[str, List[Path]] = defaultdict(list)
    for label_dir in label_dirs:
        if not label_dir.is_dir():
            continue
        for root, _dirs, files in os.walk(label_dir):
            for fname in files:
                if fname.endswith('.json'):
                    file_index[fname].append(Path(root) / fname)

    loaded = []
    for entry in m.get('entries', []):
        if entry.get('split') not in splits:
            continue
        rel_path = entry.get('file_path', '')
        fname = os.path.basename(rel_path)
        candidates = []
        # Try the as-is path first
        if rel_path:
            p = Path(rel_path)
            if p.is_file():
                candidates.append(p)
            # And the label-dir-resolved candidates
            candidates.extend(file_index.get(fname, []))
        for p in candidates:
            try:
                d = json.load(open(p))
            except Exception:
                continue
            # Replicate the notes-required loader filter
            if 'notes' not in d:
                continue
            # Replicate the Strategy B skip logic
            if d.get('converter_strategy') == 'B':
                continue
            # Pull out the piece metadata
            loaded.append({
                'source': entry.get('source'),
                'composition_id': d.get('composition_id', entry.get('composition_id')),
                'piece_id': d.get('piece_id', entry.get('id')),
                'split': entry.get('split'),
                'file_path': str(p),
            })
            break  # found the file
    return loaded


def parse_composer_from_path(file_path: str) -> Optional[str]:
    """Extract composer name from a label file path.

    Heuristics:
      - dcml_score_key_labels/ABC/n01op18-1_01.json  → 'beethoven' (ABC = Annotated Beethoven Corpus)
      - dcml_score_key_labels/mozart_piano_sonatas/.../*.json → 'mozart'
      - score_key_labels/0007.json → ATEPP (composer is in the ATEPP metadata; not parsed here)
      - wir_key_labels/beethoven_op002_no1_1.json → 'beethoven'
      - wir_key_labels/mozart_k331_1.json → 'mozart'
      - wir_key_labels/bach_chorales_001.json → 'bach'
    """
    p = file_path.lower()
    # 'ABC' subdir = Annotated Beethoven Corpus
    if '/dcml_score_key_labels/abc/' in p or '/dcml_key_labels/abc/' in p:
        return 'beethoven'
    # Composer-name patterns from filename or path
    composers = ('beethoven', 'mozart', 'bach', 'chopin', 'schumann', 'schubert',
                 'brahms', 'liszt', 'debussy', 'haydn', 'dvorak', 'grieg',
                 'tchaikovsky', 'rachmaninov', 'rachmaninoff', 'mendelssohn')
    for c in composers:
        if c in p:
            return c
    return None


def parse_beethoven_op_movement(file_path: str) -> Optional[Tuple[str, str]]:
    """Extract (opus, movement) from a Beethoven label-file path.

    Returns ('op002', '1') for `wir_key_labels/beethoven_op002_no1_1.json`,
    ('op018', '1') for `dcml_score_key_labels/ABC/n01op18-1_01.json`, etc.

    Returns None if the path doesn't match a Beethoven naming pattern.
    """
    p = file_path.lower()
    # wir-style: beethoven_op002_no1_1
    m = re.search(r'beethoven_op0*(\d+)_no\d+_(\d+)', p)
    if m:
        return (f'op{int(m.group(1)):03d}', m.group(2))
    # dcml ABC-style: n01op18-1_01.json (n01 = quartet number, op18 = opus, -1 = quartet within op, _01 = movement)
    m = re.search(r'/abc/n\d+op(\d+)-?\d*_(\d+)\.', p)
    if m:
        return (f'op{int(m.group(1)):03d}', m.group(2))
    # Fallback dcml: any abc/...op<NN> pattern
    m = re.search(r'/abc/.*op(\d+)', p)
    if m:
        return (f'op{int(m.group(1)):03d}', '?')
    return None


def parse_mozart_kn_movement(file_path: str) -> Optional[Tuple[str, str]]:
    """Extract (K-number, movement) from a Mozart label file path.

    Returns ('k331', '1') for `mozart_k331_1.json`.
    """
    p = file_path.lower()
    m = re.search(r'mozart[/_]k0*(\d+)[a-z]?[/_-](\d+)', p)
    if m:
        return (f'k{int(m.group(1)):03d}', m.group(2))
    m = re.search(r'mozart_piano_sonatas[^/]*/k0*(\d+)', p)
    if m:
        return (f'k{int(m.group(1)):03d}', '?')
    return None


# ─────────────────────────────────────────────────────────────────────────
# Step 2 — enumerate the test corpus

def enumerate_bps_fh(bps_fh_dir: Path) -> List[Dict]:
    """BPS-FH ships 32 first-movements of Beethoven piano sonatas.

    The internal piece numbering (1..32) is the Chen-Su 2018 ordering.
    For composer-overlap audit purposes, we just record composer and
    movement = '1' for all 32.

    Returns a list of dicts: {piece_id, composer, op_number, movement}.
    """
    records = []
    if not bps_fh_dir.is_dir():
        return records
    for path in sorted(bps_fh_dir.glob('BPS_FH_*.json')):
        d = json.load(open(path))
        records.append({
            'piece_id': d.get('id', path.stem),
            'composer': 'beethoven',
            'op_number': None,  # BPS-FH ID doesn't directly map to opus without the BPS-FH README
            'movement': '1',
            'source_path': str(path),
        })
    return records


def enumerate_tavern(tavern_root: Path) -> List[Dict]:
    """TAVERN ships theme-and-variations for Beethoven (17 works) and
    Mozart (10 works), each variation as a separate phrase.

    Returns one record PER WORK (not per phrase) for composer-overlap
    purposes; the audit is at the work level.
    """
    records = []
    if not tavern_root.is_dir():
        return records
    for composer_dir in sorted(tavern_root.iterdir()):
        if not composer_dir.is_dir():
            continue
        composer = composer_dir.name.lower()
        if composer not in ('beethoven', 'mozart'):
            continue
        for work_dir in sorted(composer_dir.iterdir()):
            if not work_dir.is_dir():
                continue
            work_name = work_dir.name  # e.g. 'B066', 'Opus34', 'K265'
            # Parse opus / WoO / K-number
            op_number, movement = None, '?'
            if composer == 'beethoven':
                m = re.match(r'^B0*(\d+)$', work_name, re.I)  # WoO
                if m:
                    op_number = f'WoO{int(m.group(1)):03d}'
                m = re.match(r'^Opus0*(\d+)$', work_name, re.I)
                if m:
                    op_number = f'op{int(m.group(1)):03d}'
            elif composer == 'mozart':
                m = re.match(r'^K0*(\d+)$', work_name, re.I)
                if m:
                    op_number = f'k{int(m.group(1)):03d}'
            records.append({
                'piece_id': f'{composer.capitalize()}_{work_name}',
                'composer': composer,
                'op_number': op_number,
                'work_name': work_name,
                'movement': movement,
                'source_path': str(work_dir),
            })
    return records


# ─────────────────────────────────────────────────────────────────────────
# Step 3 — audit a (training_pool, test_corpus) pair

def audit_corpus(training_pool: List[Dict], test_corpus: List[Dict],
                 corpus_name: str) -> Dict:
    """Compute composer-level + piece-level overlap statistics."""
    # Compute composers in each
    train_composers = Counter()
    train_beethoven_ops = set()
    train_mozart_ks = set()
    for r in training_pool:
        c = parse_composer_from_path(r['file_path'])
        if c:
            train_composers[c] += 1
            if c == 'beethoven':
                op = parse_beethoven_op_movement(r['file_path'])
                if op:
                    train_beethoven_ops.add(op[0])
            elif c == 'mozart':
                k = parse_mozart_kn_movement(r['file_path'])
                if k:
                    train_mozart_ks.add(k[0])

    test_composers = Counter(r['composer'] for r in test_corpus)
    test_composers_set = set(test_composers)

    # Composer-level overlap
    composer_overlap = test_composers_set & set(train_composers)

    # Piece-level overlap (best-effort: match on (composer, op_number))
    test_pieces = [(r['composer'], r.get('op_number')) for r in test_corpus
                   if r.get('op_number')]
    piece_overlap = []
    for composer, op in test_pieces:
        if composer == 'beethoven' and op in train_beethoven_ops:
            piece_overlap.append(f'beethoven {op}')
        elif composer == 'mozart' and op in train_mozart_ks:
            piece_overlap.append(f'mozart {op}')

    return {
        'corpus_name': corpus_name,
        'n_test_pieces': len(test_corpus),
        'test_composers': dict(test_composers),
        'train_composers': dict(train_composers),
        'composer_overlap': sorted(composer_overlap),
        'composer_overlap_count': len(composer_overlap),
        'beethoven_ops_in_train': sorted(train_beethoven_ops),
        'mozart_ks_in_train': sorted(train_mozart_ks),
        'piece_level_overlap_examples': sorted(set(piece_overlap)),
        'piece_level_overlap_count': len(set(piece_overlap)),
    }


# ─────────────────────────────────────────────────────────────────────────
# Driver

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--training-manifest',
                    default='research_data/unified_training_manifest_phase1_clean.json')
    ap.add_argument('--label-dirs', nargs='+',
                    default=[
                        'research_data/score_key_labels',
                        'research_data/dcml_score_key_labels',
                        'research_data/dcml_key_labels',
                        'research_data/wir_key_labels',
                    ])
    ap.add_argument('--bps-fh-dir',
                    default='research_data/bps_fh_score_key_labels')
    ap.add_argument('--tavern-root', default='TAVERN-master')
    ap.add_argument('--skip-bps-fh', action='store_true')
    ap.add_argument('--skip-tavern', action='store_true')
    ap.add_argument('--output-json',
                    default='research_data/composer_overlap_audit_2026-05-09.json')
    ap.add_argument('--output-md',
                    default='research_data/composer_overlap_audit_2026-05-09.md')
    args = ap.parse_args()

    manifest = (HERE / args.training_manifest).resolve()
    label_dirs = [(HERE / ld).resolve() for ld in args.label_dirs]
    bps_dir = (HERE / args.bps_fh_dir).resolve()
    tavern_root = (HERE / args.tavern_root).resolve()

    # ─── Step 1: reconstruct loaded training pool ──────────────────────
    print(f'\n--- Reconstructing actually-loaded training pool ---')
    print(f'  Manifest: {manifest}')
    train_pool = reconstruct_loaded_train_pieces(manifest, label_dirs)
    print(f'  Loaded train+val records (in-domain test excluded by design): {len(train_pool)}')

    # ─── Step 2: audit BPS-FH ──────────────────────────────────────────
    audits = {}
    if not args.skip_bps_fh:
        print(f'\n--- Auditing BPS-FH ({bps_dir}) ---')
        bps_corpus = enumerate_bps_fh(bps_dir)
        if not bps_corpus:
            print(f'  WARN: 0 BPS-FH records found at {bps_dir}; skipping')
        else:
            audits['bps_fh'] = audit_corpus(train_pool, bps_corpus, 'BPS-FH')
            a = audits['bps_fh']
            print(f'  n_test_pieces: {a["n_test_pieces"]}')
            print(f'  test_composers: {a["test_composers"]}')
            print(f'  composer_overlap with training pool: {a["composer_overlap"]}')
            print(f'  Beethoven opus-numbers in training pool: {len(a["beethoven_ops_in_train"])} '
                  f'({a["beethoven_ops_in_train"][:8]}...)')
            print(f'  piece-level overlap: {a["piece_level_overlap_count"]} '
                  f'(examples: {a["piece_level_overlap_examples"][:5]})')

    # ─── Step 3: audit TAVERN ──────────────────────────────────────────
    if not args.skip_tavern:
        print(f'\n--- Auditing TAVERN ({tavern_root}) ---')
        tavern_corpus = enumerate_tavern(tavern_root)
        if not tavern_corpus:
            print(f'  WARN: 0 TAVERN records found at {tavern_root}; skipping')
        else:
            audits['tavern'] = audit_corpus(train_pool, tavern_corpus, 'TAVERN')
            a = audits['tavern']
            print(f'  n_test_works: {a["n_test_pieces"]}')
            print(f'  test_composers: {a["test_composers"]}')
            print(f'  composer_overlap with training pool: {a["composer_overlap"]}')
            print(f'  Mozart K-numbers in training pool: {len(a["mozart_ks_in_train"])} '
                  f'({a["mozart_ks_in_train"][:8]}...)')
            print(f'  piece-level overlap: {a["piece_level_overlap_count"]} '
                  f'(examples: {a["piece_level_overlap_examples"][:5]})')

    # ─── Save outputs ──────────────────────────────────────────────────
    out_doc = {
        'date': '2026-05-09',
        'training_manifest': str(manifest.name),
        'n_loaded_train_records': len(train_pool),
        'audits': audits,
    }
    out_json = HERE / args.output_json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out_doc, indent=2))

    # Markdown
    md = ['# Composer-overlap audit — 2026-05-09', '']
    md.append(f'**Training manifest:** `{manifest.name}`')
    md.append(f'**Loaded train+val records:** {len(train_pool)} '
              '(after the loader\'s `if "notes" not in data: continue` filter; '
              'in-domain test split is excluded — the cross-corpus leakage question '
              'is "what composers does the trained checkpoint know about?", '
              'and test records were never used for training or selection)')
    md.append('')
    md.append('## How this audit defines "leakage" vs "overlap"')
    md.append('')
    md.append('- **Piece-level leakage** = same piece (composer + opus + movement) '
              'in both training and test. Strict definition; if non-zero, the zero-shot '
              'claim is invalidated.')
    md.append('- **Composer-level overlap** = same composer in training AND test, '
              'but different pieces. Not strictly leakage; must be disclosed in chapter prose '
              'as "partially-seen composer."')
    md.append('')

    for key, name in (('bps_fh', 'BPS-FH (Beethoven Piano Sonatas, first movements)'),
                       ('tavern', 'TAVERN (Theme-and-Variations: Beethoven + Mozart)')):
        if key not in audits:
            continue
        a = audits[key]
        md.append(f'## {name}')
        md.append('')
        md.append(f'- n test pieces: **{a["n_test_pieces"]}**')
        md.append(f'- Test corpus composers: {a["test_composers"]}')
        md.append(f'- Composer-level overlap with training pool: '
                  f'**{a["composer_overlap"]}** ({a["composer_overlap_count"]} composers)')
        md.append(f'- Piece-level (composer × opus) overlap: '
                  f'**{a["piece_level_overlap_count"]}** detected')
        if a['piece_level_overlap_examples']:
            md.append(f'  - Examples: {a["piece_level_overlap_examples"][:10]}')
        if a['beethoven_ops_in_train']:
            md.append(f'- Beethoven opus-numbers present in training pool: '
                      f'{len(a["beethoven_ops_in_train"])} '
                      f'({", ".join(a["beethoven_ops_in_train"][:12])}'
                      f'{"..." if len(a["beethoven_ops_in_train"]) > 12 else ""})')
        if a['mozart_ks_in_train']:
            md.append(f'- Mozart K-numbers present in training pool: '
                      f'{len(a["mozart_ks_in_train"])} '
                      f'({", ".join(a["mozart_ks_in_train"][:12])}'
                      f'{"..." if len(a["mozart_ks_in_train"]) > 12 else ""})')
        md.append('')
        # Required chapter framing
        if key == 'bps_fh':
            md.append('### Required chapter-prose framing for BPS-FH')
            md.append('')
            md.append('> *"Zero-shot transfer to an unseen ensemble (piano solo) and '
                      'unseen work-set (sonata first movements) by a partially-seen '
                      'composer (Beethoven, via string quartets in training)."*')
            md.append('')
            md.append('NOT *"completely zero-shot to an unseen composer."*')
            md.append('')
        elif key == 'tavern':
            md.append('### Required chapter-prose framing for TAVERN')
            md.append('')
            md.append('> *"Within-classical replication with composer overlap. Beethoven '
                      'overlap: same as BPS-FH (string quartets in training; theme-and-'
                      'variations in test). Mozart overlap: DCML training corpus includes '
                      '`mozart_piano_sonatas`; Mozart T&V is in test. Per-composer subgroup '
                      'analysis (Beethoven phrases vs Mozart phrases) is reported below."*')
            md.append('')

    md.append('---')
    md.append('')
    md.append('*Compiled by `compute_composer_overlap_audit.py` 2026-05-09. '
              'Closes R2.1 (BPS-FH) + R2.2 (TAVERN, when applicable) of '
              'POSTDOC_REVIEWER_PASS_2026-05-09.md.*')

    out_md = HERE / args.output_md
    out_md.write_text('\n'.join(md) + '\n')

    print(f'\n✓ Wrote {out_json}')
    print(f'✓ Wrote {out_md}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
