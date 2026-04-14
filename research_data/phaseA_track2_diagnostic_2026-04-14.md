# Phase A Track 2 — Val/Test Diagnostic & Manifest Audit

**Date:** 2026-04-14
**Purpose:** Close the Phase B pre-registration prerequisite (§4): characterize val vs test distributions to understand the systematic −0.11 val-to-test MIREX drift measured across all 3 Phase A seeds. Audit the manifest's WiR/DCML coverage to determine whether Phase B's effective test N can be expanded beyond 41.
**Artefact:** `research_data/val_test_diagnostic_2026-04-14.json` (machine-readable numbers).

---

## 1. Headline: the val-to-test drift is a data-split artefact, not a training artefact

**Jensen-Shannon divergence between val and test class histograms: 0.2008 (log2 base).**

For a 24-class distribution over 52k / 89k frames, JS ≈ 0.20 is a moderate-to-large mismatch — large enough to explain the measured −0.11 MIREX drift on its own. Three of the 24 classes show Δp (test−val) > 0.06:

| Class | Val % | Test % | Δp (test − val) | Interpretation |
|---|---:|---:|---:|---|
| **F** | 18.45 | 4.24 | **−0.142** | Val has 4.3× more F-major frames |
| **D** | 1.12 | 12.77 | **+0.116** | Test has 11.4× more D-major frames |
| **G#m** | 12.49 | 3.43 | **−0.091** | Val has 3.6× more G♯-minor frames |
| Cm | 1.67 | 8.30 | +0.066 | Test has 5× more C-minor frames |
| E | 2.57 | 8.71 | +0.061 | Test has 3.4× more E-major frames |
| Bm | 2.52 | 7.36 | +0.048 | Test has 2.9× more B-minor frames |
| F#m | 4.45 | 0.39 | −0.041 | Val has 11× more F♯-minor (!!) |
| Am | 0.44 | 4.22 | +0.038 | Test has 9.5× more A-minor frames |

**Critical asymmetries:**
- **Dm** (D minor) is **completely absent from val** (0 frames) but present in test (1,746 frames, 2.0%). The val-MIREX selection metric cannot guide behavior on Dm.
- **C#** (C♯ major) is **completely absent from test** (0 frames) but present in val (822 frames, 1.6%). C# test accuracy reported in any eval is actually N=0 — it doesn't exist on the test side.
- **F#m** (F♯ minor) has **2,308 val frames but only 353 test frames**. The wildly unstable F#m across Phase A seeds (0.262 / 0.084 / 0.285) partly reflects the tiny test sample.

## 2. Why this matters for Phase B

1. **Val-MIREX selection systematically overestimates generalization.** Because val's distribution is not representative of test, val-MIREX = 0.61 consistently coexists with test-MIREX = 0.50. This −0.11 drift is intrinsic to the current split — it won't be fixed by any algorithm change in Phase B.

2. **A Phase B cell can "win" on val-MIREX selection but lose on test** if it happens to over-fit to the F-major / G♯-minor signal that val over-represents. Conversely, a cell that underfits val's biases but handles the broader distribution well could look worse on val but be better in practice.

3. **F#m's unstable test accuracy** (σ=0.11 across 3 seeds) is partly a sample-size issue: 353 test frames yield an SE of ~5 percentage points per seed. Interpreting F#m recovery as evidence of algorithm quality requires caution until N grows.

4. **Large-composition asymmetry** contributes to the frame-weighted vs composition-equal MIREX gap (0.5026 vs 0.5802 = 0.078 points). Test has compositions up to 16,098 frames (vs val's max 9,245). Large, low-MIREX compositions like 1495 (32k frames, MIREX 0.38) dominate frame-weighted means disproportionately.

## 3. Phase B mitigation plan

The drift is a fixed property of the current split. Redrawing the split mid-study would invalidate Phase A's baseline. Instead:

### 3a. Report both frame-weighted and composition-equal MIREX

Every Phase B cell reports two aggregation forms. Claims of "win" must clear Δ=0.015 in **at least one** aggregation; claims in only one aggregation are flagged as "aggregation-dependent". The two forms should agree on sign; sign disagreement is a red flag.

### 3b. Report a class-rebalanced auxiliary MIREX

Beyond the two primary aggregations, report an **adjusted MIREX**: re-weight test frames so each of the 18 present classes contributes with weight 1/18 (regardless of its frame count). This removes the test's class bias from the aggregate, at the cost of being incompatible with literature (since MIREX literature uses frame-weighted). Serves as an internal sanity check for Phase B, not a headline number.

### 3c. Skip per-class stability claims for C# and Dm

Don't cite C# accuracy (no test frames) or Dm val-MIREX (no val frames) in comparisons.

### 3d. F#m requires caution

Any F#m claim must be tied to ≥3 seeds with reported σ. A single seed showing "F#m=0.28" is N=353 frames / 706 × that seed's model → ~180 correct predictions. ±5pp SE. Don't cite single-seed F#m claims.

### 3e. Do NOT attempt to close the val/test drift through training

Augmentation or sampling tricks to balance val would leak into the validation protocol. Either accept the drift as a measured constant (−0.11) and subtract it mentally when reading val-MIREX, or redraw the splits as a one-time action between studies (not within Phase B).

## 4. Manifest WiR/DCML coverage audit

The unified manifest has entries for all 3 corpora with splits populated:

| Source | Train | Val | Test |
|---|---:|---:|---:|
| atepp-heuristic | 250 | 28 | **41** |
| dcml-expert | 248 | 18 | 27 |
| wir-expert | 1,021 | 140 | 133 |
| **Total** | **1,519** | **186** | **201** |

All 1,906 label files are resolvable from `research_data/{wir,dcml,score}_key_labels/`. **But only 41/201 test files load**, because WiR and DCML label files are annotation-level (per-region key changes with `annotations` + `key_regions`) rather than per-note (`notes` array). The loader at `train_harmonic_context_model.py:650` correctly filters `if 'notes' not in data: continue` — WiR/DCML labels don't have a `notes` array.

A converter script exists: `convert_dcml_wir_to_note_labels.py`. It supports two strategies:
- **Strategy A**: parse the MXL score via music21 and extract per-note labels aligned with the key regions. Requires score files. WiR has scores; DCML is mostly annotations-only (no scores in this repo).
- **Strategy B**: synthetic notes at pitch=60 with the key labels applied. The Phase 2 loader deliberately excludes Strategy B (marker in the loaded file) because "teaches the model to ignore pitch information".

### 4a. Cost of expanding corpus to include WiR per-note labels

- WiR has 1,294 label files with `annotations` + `key_regions`.
- Strategy A requires parsing each MXL score with music21 (slow, ~5–30 s/score depending on size).
- Estimated runtime for 1,294 scores: **6–10 hours single-threaded** on moderate compute.
- Scores must be in the repo; verify by checking `wir_key_labels/*.json` `file_path` fields.

### 4b. Cost of expanding to include DCML per-note labels

- DCML has 293 label files.
- DCML scores **are not in the repo** (only annotations were downloaded).
- Strategy A is not feasible without sourcing the DCML score archive.
- Strategy B is cheap but produces the synthetic garbage data the Phase 2 loader correctly excludes.
- **Recommendation: do not expand DCML in Phase B.** Revisit in Phase C if extra data is needed for pretraining.

### 4c. Recommendation for Phase B

**Do not expand the test set before Phase B launches.** Rationale:

1. The 6–10 hour music21 parse job is a material delay against a 12-month horizon that already has a finalized baseline.
2. Expanding val/test mid-study invalidates the 3-seed Phase A baseline and forces a rerun.
3. The class-distribution mismatch documented in §1–§2 is the real driver of val-to-test drift, not test-set size. Adding more test data from WiR would likely keep the drift (since WiR has its own composer/period bias vs val).
4. N=41 is sufficient for Phase B's pre-registered Δ=0.015 at paired-bootstrap power — the cumulative 3-seed paired test for seed 309 vs 311 detected a 0.014 difference at p=0.007 (see phaseA_consolidation §5).

**Revisit corpus expansion as a Phase C task** when we have a Transformer candidate and we're deciding whether pretraining needs more symbolic data. At that point, run the WiR converter once (overnight), merge into the manifest, and rerun A1-corrected on the expanded split to establish a new baseline for Phase C.

## 5. Summary recommendations for Phase B

1. Proceed with Phase B on the current N_test=41 ATEPP split. **Do not** delay for corpus expansion.
2. Accept the −0.11 val-to-test drift as a measured constant of the current split; don't try to close it with training tricks.
3. Report every Phase B cell on **both** frame-weighted and composition-equal MIREX. Flag sign-disagreement across the two forms.
4. Report the class-rebalanced auxiliary MIREX (§3b) as a secondary sanity check.
5. For minor-class claims, require ≥3 seeds and report σ. Don't cite single-seed F#m, Dm, C#, or any class with <500 test frames.
6. Commit this diagnostic as the §4 prerequisite artefact; move on to ensemble + HMM re-eval (Track 1) and Phase B cell 1.

## 6. Open questions for later follow-up (not blocking Phase B)

1. **Can composition_splits.json (train 217 / val 44 / test 58) be used instead of the manifest split?** Its 58 test compositions may have a different class distribution. Worth measuring once before any Phase C re-split decision.
2. **Should val be expanded to add Dm and reduce F#m over-representation?** Would require a re-split. Revisit with Phase C.
3. **Is there value in the DCML score archive?** If sourced, DCML adds modulation-heavy chamber music that would stress-test the tonicization subset. Low priority; possibly Phase D.
4. **What is the composer-stratified stability of Phase A?** The per-composer breakdown (1/28 val, 1/41 test, etc. for small composers) is too thin for a meaningful stratified analysis. Composer-stratified accuracy is not cited in any Phase B success criterion.

---

**Next action:** commit this document + `val_test_diagnostic_2026-04-14.json` on `main`; wait for Track 1 (HMM + ensemble re-eval) output from Colab; then launch Phase B cell 1.
