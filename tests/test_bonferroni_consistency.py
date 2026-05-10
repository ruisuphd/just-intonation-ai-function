"""Project-wide regression test for the Bonferroni α correction wording.

Closes the engineering follow-up flagged in REVIEWER_AUDIT_RESPONSE_v2_2026-05-14.md
P1-E and COMPREHENSIVE_REVIEW_2026-05-10.md W10.7. The 2026-05-08 fix corrected
α/2 → α/4 for the joint Option A + Option B family of 4 hypotheses (the family
size is 4 because we test: A finetune vs A scratch, A vs Phase I scratch, B vs
Phase I scratch, A vs B head-to-head). This test prevents that fix from
silently regressing.

The test scans all top-level Markdown documents and the principal source files
for the substring "α/2" or "alpha/2" near (within 200 chars of) the substring
"Bonferroni" — and asserts that no such co-location exists. The 200-char window
is wide enough to catch sentence-level co-occurrence but narrow enough to
ignore unrelated mentions in different paragraphs.

If a future PR reintroduces α/2 in a Bonferroni context, this test fails in CI
and the PR can be reviewed before the regression lands on main.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Files to scan: top-level project docs (.md) + principal source (.py).
# We do NOT scan thesis-and-papers/ Chapter 6/7/8 because those reference
# the *project-wide* family Bonferroni (α/4) and the *Phase I H1-H5 family*
# Bonferroni (α = 0.01 over 5 hypotheses, NOT α/2 either). Both are correct.
# We DO scan the project-root docs that the COMPREHENSIVE_REVIEW flagged.
DOCS_TO_SCAN = [
    'COMPREHENSIVE_RIGOUR_PLAN_2026-04-26.md',
    'OPTION_A_B_IMPLEMENTATION_PLAN_2026-05-08.md',
    'COLAB_OPTION_A_B_CELLS_2026-05-08.md',
    'REVIEWER_AUDIT_RESPONSE_2026-05-13.md',
    'REVIEWER_AUDIT_RESPONSE_v2_2026-05-14.md',
    'COLAB_RUNNING_PCP_EVAL_2026-05-10.md',
]

# Source files that may reference the joint A+B Bonferroni family in docstrings.
# Files marked optional (e.g. train_phase1_transformer.py is on the PR #10
# branch only) are scanned IF present and skipped IF absent — the test must
# work in either branch's checkout.
SOURCE_TO_SCAN = [
    'harmonic_context_model.py',                    # always present (Option B class lives here)
    'pretrain_symbolic_key.py',                     # always present
    'phase1_beat_classical/train_phase1.py',        # always present
    'tests/test_option_b_gru_pretrain.py',          # always present
    'train_phase1_transformer.py',                  # PR #10 only — optional
    'tests/test_option_a_transformer.py',           # PR #10 only — optional
]

# The forbidden pattern: "α/2" OR "alpha/2" within 200 chars of "Bonferroni".
# Both directions covered (Bonferroni first OR α/2 first).
WINDOW = 200


def _scan_for_bad_pair(text: str) -> list[tuple[int, str]]:
    """Return list of (offset, snippet) where 'α/2' or 'alpha/2' appears within
    WINDOW chars of 'Bonferroni'. Empty list = no co-location."""
    bad_pat = re.compile(r'(α\s*/\s*2|alpha\s*/\s*2)', re.IGNORECASE)
    bonf_pat = re.compile(r'Bonferroni', re.IGNORECASE)
    bad_hits = [(m.start(), m.group()) for m in bad_pat.finditer(text)]
    bonf_hits = [m.start() for m in bonf_pat.finditer(text)]
    if not bad_hits or not bonf_hits:
        return []
    flagged = []
    for bad_pos, bad_str in bad_hits:
        for bonf_pos in bonf_hits:
            if abs(bad_pos - bonf_pos) <= WINDOW:
                # Capture a 200-char snippet around the bad match
                lo = max(0, bad_pos - 100)
                hi = min(len(text), bad_pos + 100)
                snippet = text[lo:hi].replace('\n', ' ')
                flagged.append((bad_pos, f'...{snippet}...'))
                break
    return flagged


def _read_file(path: Path) -> str:
    if not path.exists():
        return ''
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return ''


def test_no_bonferroni_alpha_over_2_in_docs() -> None:
    """No project doc may contain "α/2" within 200 chars of "Bonferroni"."""
    bad = []
    for rel in DOCS_TO_SCAN:
        path = ROOT / rel
        text = _read_file(path)
        if not text:
            continue
        for pos, snip in _scan_for_bad_pair(text):
            bad.append(f'{rel}:{pos}: {snip}')
    assert not bad, (
        'Found "α/2" near "Bonferroni" in these project docs (the joint A+B '
        'family is 4 hypotheses → α/4, NOT α/2). Fix each occurrence:\n  '
        + '\n  '.join(bad)
    )


def test_no_bonferroni_alpha_over_2_in_source() -> None:
    """No principal source file may contain "α/2" within 200 chars of "Bonferroni"."""
    bad = []
    for rel in SOURCE_TO_SCAN:
        path = ROOT / rel
        text = _read_file(path)
        if not text:
            continue
        for pos, snip in _scan_for_bad_pair(text):
            bad.append(f'{rel}:{pos}: {snip}')
    assert not bad, (
        'Found "α/2" near "Bonferroni" in these source files (the joint A+B '
        'family is 4 hypotheses → α/4, NOT α/2). Fix each occurrence:\n  '
        + '\n  '.join(bad)
    )


def test_alpha_over_4_documented_in_at_least_one_artefact() -> None:
    """At least ONE project artefact (doc OR source) must contain α/4 —
    a positive coverage check confirming the corrected wording is in place,
    not merely that α/2 is absent. Scans both DOCS_TO_SCAN and SOURCE_TO_SCAN
    because some project docs live at project root (outside the PR checkout)
    but the joint-A+B α/4 wording is also documented in source docstrings
    (e.g. harmonic_context_model.py and train_phase1_transformer.py)."""
    found_count = 0
    found_locs = []
    pat = re.compile(r'(α\s*/\s*4|alpha\s*/\s*4)')
    for rel in list(DOCS_TO_SCAN) + list(SOURCE_TO_SCAN):
        path = ROOT / rel
        text = _read_file(path)
        if not text:
            continue
        if pat.search(text):
            found_count += 1
            found_locs.append(rel)
    assert found_count >= 1, (
        'No project artefact contains "α/4" — the joint A+B family '
        'Bonferroni correction wording must appear in at least one '
        'artefact (doc OR source). Scanned: '
        f'{list(DOCS_TO_SCAN) + list(SOURCE_TO_SCAN)}'
    )
