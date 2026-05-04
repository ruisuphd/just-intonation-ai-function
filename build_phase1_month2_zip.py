#!/usr/bin/env python3
"""Build the Drive-upload zip for the Phase I Month 2 Colab session.

Produces `phase1_month2_2026-05-02.zip` containing the project source tree
trimmed to what the Month 2 sweep actually needs:

  - Patched runtime + canonical Phase I trainer + aggregator
  - Phase I + B9 5-seed restored checkpoint archives (preserved for
    skip-if-exists + cross-corpus eval)
  - POP909 + BPS-FH ingestion adapters
  - Test suite (so Cell 1 can verify integrity end-to-end)
  - Pre-registration + audit report (for governance traceability)
  - Pre-built manifest fixtures so the Colab session doesn't need network
    access to rebuild them

Excludes:
  - Worktrees (.claude/worktrees/)
  - Output zips and large research artefacts not needed in Month 2
  - Cached PyTorch / npm / pip artefacts
  - Thesis chapters (kept on the local laptop; not needed for training)

Usage:
    python build_phase1_month2_zip.py            # writes ./phase1_month2_2026-05-02.zip
    python build_phase1_month2_zip.py --output /tmp/sweep.zip
    python build_phase1_month2_zip.py --dry-run  # print what would be included

Author: Rui Su, 2026-05-02.
"""
from __future__ import annotations

import argparse
import os
import sys
import zipfile
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent

# ─────────────────────────────────────────────────────────────────────────
# Inclusion / exclusion rules

# Include (relative to ROOT)
INCLUDE_FILES: List[str] = [
    # Top-level Python sources (training + runtime + adapters + aggregator)
    'harmonic_context_runtime.py',
    'harmonic_context_model.py',
    'evaluate_harmonic_context_model.py',
    'evaluate_classical_baseline.py',
    'train_harmonic_context_model.py',
    'parse_dcml_annotations.py',
    'parse_dcml_strategy_a.py',
    'parse_bps_fh.py',
    'parse_pop909.py',
    'parse_tavern.py',                  # 2026-05-09 Tier 2.3 ingestion
    'eval_pop909_from_checkpoints.py',  # 2026-05-09 cross-corpus salvage
    'eval_bps_fh_from_checkpoints.py',  # 2026-05-09 BPS-FH BASELINE comparator
    'eval_tavern_from_checkpoints.py',  # 2026-05-09 Tier 2.3 zero-shot eval
    'bma_refit_t6t1.py',                # 2026-05-09 Tier 2.5 BMA refit (4-corpus)
    'fix_pop909_per_piece.py',          # 2026-05-11 POP909 composition_id repair
    'sensitivity_sweep.py',             # 2026-05-09 Tier 2.4 driver
    'pretrain_aria_midi.py',            # 2026-05-09 Tier 3.2 wrapper
    'pretrain_symbolic_key.py',         # 2026-05-12 fix: S-KEY trainer (invoked by pretrain_aria_midi.py)
    'compute_sigma_ratio_bootstrap.py', # 2026-05-09 R1.1 (4-corpus permutation)
    'compute_composer_overlap_audit.py',# 2026-05-09 R2.1/R2.2 closure
    'build_pop909_manifest.py',         # 2026-05-09 R4.2 standalone
    'build_bps_fh_manifest.py',         # 2026-05-09 R4.2 standalone
    'EXECUTION_PLAYBOOK_2026-05-09.md', # 2026-05-09 master runbook
    'SENSITIVITY_ARIA_PLAYBOOK_2026-05-11.md',  # 2026-05-11 Job 4 runbook
    'CANONICAL_EVIDENCE_2026-05-09.md', # 2026-05-09 source-of-truth
    'CHAPTER_EDIT_PUNCH_LIST_2026-05-09.md',
    'BMA_REFIT_BLUEPRINT_2026-05-09.md',
    'POSTDOC_REVIEWER_PASS_2026-05-09.md',
    'RESEARCH_FINDINGS_2026-05-09.md',
    'RESEARCH_FINDINGS_2026-05-09_FINAL.md',  # 4-corpus σ-collapse story
    'PAPER_DRAFT_2026-05-09_v2.md',     # 2026-05-09 ISMIR-style 6-page draft
    'FILE_CLEANUP_PLAN_2026-05-09.md',
    'colab_phase1_beat_classical.py',
    'colab_phase1_month2_2026-05-08.py',
    'phase1_month2_2026-05-08.ipynb',

    # Pre-registration + audit governance
    'PHASE1_PREREGISTRATION_2026-04-25.md',
    'COMPREHENSIVE_RIGOUR_PLAN_2026-04-26.md',
    # phd_project_audit_report_2026-04-30.md lives outside the project root
    # (in /Users/ruisu/Desktop/ruisuphd/), so we copy it explicitly below.
]

INCLUDE_TREES: List[str] = [
    'phase1_beat_classical',  # canonical trainer + aggregator + variants
    'tests',  # full test suite
]

# Selective inclusion under research_data/ — we only want a few specific files,
# not the whole 50+ GB tree.
INCLUDE_RESEARCH_DATA_FILES: List[str] = [
    'unified_training_manifest_phase1_clean.json',
    'unified_training_manifest_phase1.json',
    'unified_training_manifest.json',
    'composition_splits.json',
    'b9_5seed_stability_2026-04-20.json',
    'phase1_paired_bootstrap_2026-05-01.json',
    'run_phase1_paired_bootstrap_2026-05-01.py',
    'classical_baseline_eval.json',
    'classical_baseline_aligned.json',
    'classical_baseline_eval_5profile.json',
    'REPORTING_CONVENTIONS_2026-04-20.md',

    # 2026-05-09 cross-corpus + statistical artefacts
    'bps_fh_eval_2026-05-09.json',
    'bps_fh_manifest_2026-05-09.json',
    'bps_fh_classical_baseline_2026-05-09.json',
    'pop909_results_2026-05-09.json',
    'pop909_results_2026-05-09.md',
    'pop909_classical_baseline_2026-05-09.json',
    'tavern_eval_2026-05-09.json',
    'tavern_eval_2026-05-09.md',
    'tavern_manifest_2026-05-09.json',
    'tavern_classical_baseline_2026-05-09.json',
    'classical_baseline_atepp41_aligned_2026-05-09.json',
    'composer_overlap_audit_2026-05-09.json',
    'composer_overlap_audit_2026-05-09.md',
    'sigma_collapse_formal_tests_2026-05-09.json',
    'sigma_collapse_formal_tests_2026-05-09.md',
    'bma_refit_t6t1_2026-05-09.json',
    'bma_refit_t6t1_2026-05-09.md',
]

INCLUDE_RESEARCH_DATA_TREES: List[str] = [
    'score_key_labels',
    'wir_key_labels',
    'dcml_key_labels',
    'dcml_score_key_labels',
    'bps_fh_score_key_labels',     # 2026-05-09 BPS-FH zero-shot eval labels
    'tavern_score_key_labels',     # 2026-05-09 TAVERN zero-shot eval labels (1063)
    'phaseA_track1_results',
    'phaseB_results_2026-04-18',
    'B9_extra_seeds',
    'recovered_from_drive_2026-04-25',
]

# Month-2 datasets bundled INSIDE the zip (under research_data/) so the
# Colab session does not require a separate Drive upload of either corpus.
# Source paths are external to the project tree; they are copied at zip
# time. To keep the zip small, POP909 'versions/' subdirectories are
# excluded (they are alternative arrangements not used by the Phase I
# pipeline).
INCLUDE_EXTERNAL_DATASETS: List[Tuple[str, str, List[str]]] = [
    # (source_abs_path, archive_dir_inside_research_data, exclude_patterns)
    (
        '/Users/ruisu/Desktop/ruisuphd/prototype090326AI-functions/'
        'functional-harmony-master/BPS_FH_Dataset',
        'research_data/bps_fh',
        [],
    ),
    (
        '/Users/ruisu/Desktop/ruisuphd/prototype090326AI-functions/'
        'POP909-Dataset-master/POP909',
        'research_data/POP909',
        ['*/versions/*', '*/versions'],
    ),
]

# Skip patterns — applied AFTER include rules. Used to prune cache / large
# artefacts that snuck into included trees.
EXCLUDE_PATTERNS: List[str] = [
    '*/__pycache__/*', '*.pyc',
    '*/.DS_Store',
    '*/.pytest_cache/*',
    '*/dcml_corpora/*',          # huge — Colab clones afresh from GitHub
    '*/.git/*', '*/.gitignore',
]

# Audit report lives outside the project root; copy at zip-time.
AUDIT_REPORT_EXTERNAL = Path('/Users/ruisu/Desktop/ruisuphd/phd_project_audit_report_2026-04-30.md')


# ─────────────────────────────────────────────────────────────────────────
# Helpers

def _walk_tree(tree_root: Path) -> Iterable[Path]:
    for dirpath, _dirnames, filenames in os.walk(tree_root):
        for name in filenames:
            yield Path(dirpath) / name


def _is_excluded(rel_path: str) -> bool:
    return any(fnmatch(rel_path, pat) for pat in EXCLUDE_PATTERNS)


def _enumerate_files() -> List[Tuple[Path, str]]:
    """Return (absolute_path, archive_name) pairs to include in the zip."""
    out: List[Tuple[Path, str]] = []

    # Files at root
    for rel in INCLUDE_FILES:
        p = ROOT / rel
        if p.exists():
            out.append((p, rel))

    # Trees at root
    for rel in INCLUDE_TREES:
        tree = ROOT / rel
        if not tree.is_dir():
            continue
        for f in _walk_tree(tree):
            arcname = str(f.relative_to(ROOT))
            if _is_excluded(arcname):
                continue
            out.append((f, arcname))

    # research_data/ — selective
    rd = ROOT / 'research_data'
    if rd.is_dir():
        for rel in INCLUDE_RESEARCH_DATA_FILES:
            p = rd / rel
            if p.exists():
                out.append((p, f'research_data/{rel}'))
        for rel in INCLUDE_RESEARCH_DATA_TREES:
            tree = rd / rel
            if not tree.is_dir():
                continue
            for f in _walk_tree(tree):
                arcname = f'research_data/{f.relative_to(rd)}'
                if _is_excluded(arcname):
                    continue
                out.append((f, arcname))

    # Audit report (external)
    if AUDIT_REPORT_EXTERNAL.exists():
        out.append((AUDIT_REPORT_EXTERNAL, 'phd_project_audit_report_2026-04-30.md'))

    # External datasets bundled into research_data/
    for src_root, archive_root, excl in INCLUDE_EXTERNAL_DATASETS:
        src_path = Path(src_root)
        if not src_path.is_dir():
            continue
        for f in _walk_tree(src_path):
            rel_inside = f.relative_to(src_path)
            arcname = f'{archive_root}/{rel_inside}'
            # Apply per-dataset excludes
            skipped = False
            for pat in excl:
                if fnmatch(arcname, pat) or fnmatch(str(rel_inside), pat) or \
                   any(fnmatch(part, pat.strip('*/')) for part in rel_inside.parts):
                    skipped = True
                    break
            if skipped:
                continue
            if _is_excluded(arcname):
                continue
            out.append((f, arcname))

    # Drop duplicates (preserve first occurrence)
    seen = set()
    deduped: List[Tuple[Path, str]] = []
    for abs_p, arcname in out:
        if arcname in seen:
            continue
        seen.add(arcname)
        deduped.append((abs_p, arcname))
    return deduped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default=str(ROOT / 'phase1_month2_2026-05-11.zip'))
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    files = _enumerate_files()
    print(f'Files to include: {len(files)}')

    if args.dry_run:
        for _abs, arcname in files:
            print(f'  {arcname}')
        return 0

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Track size + count by category
    n_total = 0
    bytes_total = 0
    cats = {'top-level': 0, 'phase1_beat_classical/': 0, 'tests/': 0,
            'research_data/': 0, 'audit/governance': 0}

    with zipfile.ZipFile(out_path, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for abs_p, arcname in files:
            try:
                size = abs_p.stat().st_size
            except OSError:
                continue
            zf.write(abs_p, arcname=arcname)
            n_total += 1
            bytes_total += size
            if arcname.startswith('research_data/'):
                cats['research_data/'] += 1
            elif arcname.startswith('phase1_beat_classical/'):
                cats['phase1_beat_classical/'] += 1
            elif arcname.startswith('tests/'):
                cats['tests/'] += 1
            elif arcname.endswith('audit_report_2026-04-30.md'):
                cats['audit/governance'] += 1
            elif arcname.startswith('PHASE1_') or arcname.startswith('COMPREHENSIVE_'):
                cats['audit/governance'] += 1
            else:
                cats['top-level'] += 1
            if args.verbose:
                print(f'  + {arcname} ({size:,} bytes)')

    print(f'\nWrote: {out_path}')
    print(f'  Total files: {n_total}')
    print(f'  Total bytes (uncompressed): {bytes_total / 1e6:.1f} MB')
    print(f'  Compressed size: {out_path.stat().st_size / 1e6:.1f} MB')
    print(f'\n  By category:')
    for k, v in cats.items():
        print(f'    {k:<25} {v} files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
