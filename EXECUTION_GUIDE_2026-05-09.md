# Execution guide — closing the 2026-05-09 reviewer-pass action items

**Author:** Rui Su
**Date:** 2026-05-09
**Purpose:** single-page operational guide to execute the eight deliverables that close the HIGH + MEDIUM-severity items of `POSTDOC_REVIEWER_PASS_2026-05-09.md`. Each deliverable has been written with a 5-pass reviewer record; this guide tells you the order to run them in and what to verify at each step.

---

## What was just delivered (8 artefacts)

### Documentation (4 files)

| File | Size | Purpose | Closes |
|---|---:|---|---|
| `CANONICAL_EVIDENCE_2026-05-09.md` | 23 KB | Single source of truth for every numerical claim in chapters 1, 4, 5, 6, 7, 8. Per-cell + per-seed FW values re-verified bit-for-bit against on-disk eval JSONs. | Foundation for R5.1 |
| `CHAPTER_EDIT_PUNCH_LIST_2026-05-09.md` | 38 KB | Find/replace edits per chapter, organised into 6 edit classes (A–F). Includes pre-edit grep checklist + 5-pass reviewer record. | R5.1 (HIGH) + R1.2 + R2.1 + R2.2 |
| `BMA_REFIT_BLUEPRINT_2026-05-09.md` | 16 KB | Trigger condition + 4-step execution + verification + chapter-prose updates triggered by the BMA refit. | R5.3 (HIGH) — queued for after POP909 retrain |
| `EXECUTION_GUIDE_2026-05-09.md` (this file) | — | One-page operational map. | — |

### Scripts (4 files)

| File | Size | Purpose | Closes |
|---|---:|---|---|
| `compute_sigma_ratio_bootstrap.py` | 22 KB | σ-ratio bootstrap CIs + cross-corpus σ-asymmetry permutation test + Levene's variance-equality test. | R1.1 (MEDIUM) |
| `compute_composer_overlap_audit.py` | 22 KB | Reconstructs the loader's actual training pool + audits BPS-FH and TAVERN for piece-level + composer-level overlap. | R2.1 + R2.2 (MEDIUM) |
| `build_pop909_manifest.py` | 8 KB | Standalone POP909 manifest builder with non-zero-val-split assertion (the val-empty bug that trapped the 2026-05-08 trainer at epoch 1 cannot recur). | R4.2 (MEDIUM) + R4.5 |
| `build_bps_fh_manifest.py` | 5 KB | Standalone BPS-FH eval-only manifest builder (no train/val splits since BPS-FH is zero-shot). | R4.2 (MEDIUM) |

---

## Execution order (in priority of leverage)

```
WHEN POP909 RETRAIN COMPLETES (≈ tomorrow morning)
│
├── 1. Drive sync — get pop909_results_2026-05-09.json + runs_pop909_v2/ to local disk
│      (Plan A or Plan B from earlier guidance)
│
├── 2. Run the 4 scripts (~30 min total, all on local CPU)
│      a. python compute_sigma_ratio_bootstrap.py   → research_data/sigma_collapse_formal_tests_2026-05-09.{json,md}
│      b. python compute_composer_overlap_audit.py → research_data/composer_overlap_audit_2026-05-09.{json,md}
│      c. python build_pop909_manifest.py           → (optional) regenerate POP909 manifest with non-zero-val assertion
│      d. python build_bps_fh_manifest.py           → research_data/bps_fh_manifest_2026-05-09.json
│
├── 3. R5.3 BMA refit (~half day) — execute BMA_REFIT_BLUEPRINT_2026-05-09.md §3
│      a. python compute_bma_ensemble.py --neural-variant T6_T1 (× 3 corpora)
│      b. Re-time §7.1.5 latency benchmark with T6_T1 in the ensemble
│
├── 4. R5.1 chapter prose pass (~1 week) — apply CHAPTER_EDIT_PUNCH_LIST_2026-05-09.md
│      a. Pre-edit grep checklist (verify nothing unexpected)
│      b. Edit Class A → Class B → Class C → Class D → Class E → Class F (in order)
│      c. Replace [VALUE] placeholders with the BMA refit numbers from Step 3
│
├── 5. Update governance docs (~1 hour)
│      a. Append 2026-05-09 entries to PHASE1_PREREGISTRATION_2026-04-25.md §6 deviations log
│      b. Append progress entries to COMPREHENSIVE_RIGOUR_PLAN_2026-04-26.md
│      c. Update RESEARCH_FINDINGS_VS_RQs_2026-04-30.md §5.1 from "unproven" to "BPS-FH replicated; POP909 in progress; TAVERN scheduled"
│
└── 6. Commit + zip — re-build phase1_month2_2026-05-10.zip with all new artefacts
```

---

## What runs RIGHT NOW (no waiting on POP909 retrain)

The σ-ratio bootstrap, composer-overlap audit, and BPS-FH manifest builder all run on existing data:

```bash
cd /Users/ruisu/Desktop/ruisuphd/prototype090326AI-functions

# 1. σ-ratio bootstrap (needs phase1_beat_classical/runs/*.json on disk + bps_fh_eval_2026-05-09.json from Drive)
#    If bps_fh_eval_2026-05-09.json isn't yet locally synced, copy it from
#    /content/drive/MyDrive/PhD/phase1_month2_2026-05-08/bps_fh_eval_2026-05-09.json
python compute_sigma_ratio_bootstrap.py
# Expected output: research_data/sigma_collapse_formal_tests_2026-05-09.{json,md}
# Expected verdict from §3.b table: σ_T6_T1 / σ_BASELINE on BPS-FH = 0.0069/0.0241 = 0.29
#                                   95% CI excludes 1.0; T6_T1 stabilises both corpora

# 2. Composer-overlap audit (already runs cleanly — verified 2026-05-09)
python compute_composer_overlap_audit.py
# Expected output: research_data/composer_overlap_audit_2026-05-09.{json,md}
# Verified result: 0 piece-level overlap on BPS-FH and TAVERN (when corpora present);
#                  composer-level overlap is BOTH Beethoven AND Mozart for TAVERN.

# 3. POP909 manifest (only needed if you want to regenerate the v2 manifest;
#    the existing pop909_manifest_2026-05-09.json from Cell 31 is fine)
python build_pop909_manifest.py
# Expected: research_data/pop909_manifest_2026-05-09.json with 70/15/15 split

# 4. BPS-FH eval-only manifest (eval-only, all 32 pieces, split=test)
python build_bps_fh_manifest.py
# Expected: research_data/bps_fh_manifest_2026-05-09.json with 32 entries
```

The scripts are idempotent — re-running on unchanged input data produces bit-identical outputs (modulo timestamps in the markdown).

---

## What blocks on the POP909 retrain

The BMA refit (R5.3) consumes POP909's chapter-citable per-piece predictions, which only exist after the v2 retrain. **DO NOT run the BMA refit on the epoch-1 lower bound** — that would lock in misleading numbers. The blueprint's §2 verification step explicitly fails-fast if the v2 numbers aren't on disk.

---

## Verification checklist — declare R5.1 + R1.1 + R1.2 + R2.1 + R2.2 + R4.2 closed when…

```bash
cd /Users/ruisu/Desktop/ruisuphd/prototype090326AI-functions

# A. CANONICAL_EVIDENCE_2026-05-09.md per-seed values bit-match on-disk JSONs
python3 << 'EOF'
import json, statistics
canonical_per_seed = {
    'BASELINE':  {3886265411: 0.5761, 3128166492: 0.5645, 1252837625: 0.5864, 3629727882: 0.6166, 440397851: 0.5784},
    'T6':        {3886265411: 0.6368, 3128166492: 0.6591, 1252837625: 0.6011, 3629727882: 0.6455, 440397851: 0.6707},
    'T6_T1':     {3886265411: 0.6801, 3128166492: 0.6792, 1252837625: 0.6750, 3629727882: 0.6609, 440397851: 0.6585},
    'T6_T1_T2':  {3886265411: 0.6788, 3128166492: 0.6518, 1252837625: 0.6586, 3629727882: 0.6654, 440397851: 0.6483},
}
for v, expected in canonical_per_seed.items():
    for sint, exp in expected.items():
        path = f'phase1_beat_classical/runs/{v}_seed{sint}_eval.json'
        d = json.load(open(path))
        actual = round(d['test_mirex_weighted_score'], 4)
        if actual != exp:
            print(f'MISMATCH: {v} seed={sint} canonical={exp} on-disk={actual}')
            raise SystemExit(1)
print('OK: all 20 per-seed FW values bit-match between CANONICAL_EVIDENCE_2026-05-09.md and on-disk eval JSONs')
EOF

# B. The 4 scripts produce the expected output JSONs
ls research_data/sigma_collapse_formal_tests_2026-05-09.json && echo "  ✓ R1.1 σ-ratio output"
ls research_data/composer_overlap_audit_2026-05-09.json && echo "  ✓ R2.1+R2.2 composer-overlap output"
ls research_data/pop909_manifest_*.json | head -1 && echo "  ✓ R4.2 POP909 manifest builder output"
ls research_data/bps_fh_manifest_2026-05-09.json && echo "  ✓ R4.2 BPS-FH manifest builder output"

# C. The chapter-edit punch list's pre-edit grep checklist returns expected results
cd thesis-and-papers
echo "--- 'drop-in weights swap' (must be 3 occurrences in 3 chapters before edits): ---"
grep -c 'drop-in weights swap' "1. Introduction.md" "7. Discussion.md" "8. Conclusion.md"

# D. The BMA refit is documented (not yet executed; queued for post-POP909-retrain)
ls BMA_REFIT_BLUEPRINT_2026-05-09.md && echo "  ✓ R5.3 blueprint ready"
```

When (A) returns "OK: all 20 per-seed FW values bit-match" + (B) lists 4 outputs + (C) returns 3 + (D) lists the blueprint, **the foundational work for R5.1 (HIGH), R1.1, R1.2, R2.1, R2.2, R4.2 is done**. The remaining work is the chapter prose pass (4–6 hours of focused editing) + the BMA refit execution after the POP909 retrain.

---

## Reviewer-pass record — per artefact

Each of the 8 deliverables carries its own embedded 5-pass reviewer record (Pass 1 = statistician, Pass 2 = cross-corpus, Pass 3 = pre-registration governance, Pass 4 = engineering / reproducibility, Pass 5 = narrative coherence). The records are at:

| Artefact | Location of reviewer record |
|---|---|
| `CANONICAL_EVIDENCE_2026-05-09.md` | §10 |
| `CHAPTER_EDIT_PUNCH_LIST_2026-05-09.md` | "Five-pass reviewer record" |
| `compute_sigma_ratio_bootstrap.py` | docstring + per-pass smoke-test verification (one issue caught: per-seed values were re-derived against on-disk JSONs after smoke test exposed a memory error in the original canonical table — fixed before delivery) |
| `compute_composer_overlap_audit.py` | docstring + smoke-test verification (one issue caught: default splits originally included `'test'`; corrected to `('train', 'val')` after smoke-test) |
| `build_pop909_manifest.py` | docstring (R4.5 explicit empty-split assertion is the embedded reviewer fix) |
| `build_bps_fh_manifest.py` | docstring + validate_manifest function (validates eval-only contract) |
| `BMA_REFIT_BLUEPRINT_2026-05-09.md` | §7 |
| (this guide) | — meta-document; reviewer record handled by per-artefact records above |

**Total issues caught by 5-pass review across all artefacts: 17.** All fixed before delivery. Two were caught by smoke-tests (the per-seed re-derivation and the splits default), the rest by the explicit reviewer-pass discipline.

---

## How to declare the work complete

1. POP909 retrain → Drive sync → local copy
2. Run the 4 scripts; verify output JSONs exist
3. Execute the BMA refit (BMA_REFIT_BLUEPRINT_2026-05-09.md §3 Steps 1–4)
4. Apply the chapter-edit punch list (Edit Classes A → F)
5. Replace [VALUE] placeholders with BMA refit numbers
6. Verify with the §"Verification checklist" of this document
7. Append the closing entry to `COMPREHENSIVE_RIGOUR_PLAN_2026-04-26.md` progress log

When step 7 is committed, R5.1 + R1.1 + R1.2 + R2.1 + R2.2 + R4.2 + R5.3 are all closed.

---

*Compiled 2026-05-09 by the candidate. The 8 deliverables and this guide replace what would otherwise be ~1 week of unstructured chapter-revision work with ~6 hours of structured execution against a frozen evidence table. The structured approach is the deliverable; the chapter prose is the work product the structure enables.*
