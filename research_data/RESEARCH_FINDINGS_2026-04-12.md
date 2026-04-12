# Research Findings — 2026-04-12

**Project:** Instant Harmonies — Real-time Adaptive Just Intonation Tuner for MIDI
**Author's institution:** Maynooth University / Federal University of Acre (joint PhD)
**Document scope:** Contribution 1 (Harmonic Context Key Detection) — Phase 1 and Phase 2 ablation results
**Status:** Partial Phase 2 complete; several critical issues require a second Colab run before the chapter can be finalized.

---

## 1. Executive Summary

1. **Phase 2 uncovered a non-causal offline upper bound at MIREX = 0.599** (experiment A9: BiGRU + PCP + focal loss, 95% CI [0.530, 0.683]). This bound cannot be deployed in the real-time tuner — bidirectional architectures require the entire note sequence at inference time.
2. **Among deployable (causal) models, the best is A7 (GRU + PCP) at MIREX = 0.543** (95% CI [0.475, 0.619]), a modest +0.012 improvement over the A1 baseline.
3. **The 2026-04-10 Colab run did NOT apply the v0.9.2 data-leakage fixes.** The uploaded `project_colab_v092.zip` was packed from `main` branch before the worktree fixes were committed. As a consequence, HMM and ensemble post-processing results remain hyperparameter-tuned on the test set and cannot be defended.
4. **Experiments A10 and A11 (testing the new Circle-of-Fifths label smoothing and training regularization improvements) were never trained.** The novel training contribution of v0.9.2 has no empirical validation as of this document's date.
5. **The classical baseline profiles in `evaluate_classical_baseline.py` are byte-for-byte copies of values published in Nápoles (2019) `justkeydding`.** The current code cites only the original 1982/1999/2013 papers, which is a citation provenance gap that must be corrected.

---

## 2. Phase 1 Recap (2026-04-09 completion)

Phase 1 ran experiments A0–A5 on Google Colab (T4 GPU) using the v0.9.1 codebase. All experiments share the same data manifest (`unified_training_manifest.json`) and the same 51-composition balanced test set (`composition_splits.json`). Bootstrap 95% CIs are composition-level.

| ID | Model | Augmentation | Class weighting | Test MIREX | 95% CI | Notes |
|----|-------|--------------|-----------------|------------|--------|-------|
| A0 | GRU | No | none | 0.494 | — | baseline without pitch augmentation |
| **A1** | **GRU** | **Yes** | **none** | **0.531** | **[0.470, 0.604]** | **best single model, chosen as Phase 2 seed** |
| A2 | GRU | No | sqrt | 0.486 | [0.420, 0.570] | class balancing hurts w/o aug |
| A3 | GRU | Yes | sqrt | 0.514 | [0.450, 0.590] | class balancing slightly below A1 |
| A4 | GRU | Yes | effective-number-of-samples | 0.531 | [0.470, 0.600] | ties A1 but higher complexity |
| A5 | Transformer | Yes | effective-number-of-samples | 0.522 | [0.460, 0.590] | transformer underperforms GRU at this param budget |

**Selection rationale:** A1 was chosen as the Phase 2 seed because it ties A4 but has the simplest configuration (no class weighting), satisfying Occam's razor and simplifying downstream ablation interpretation.

---

## 3. Phase 2 Results (2026-04-11 completion)

### 3.1 Neural ablation (test set: 252,416 predictions across 51 compositions)

Verified from `research_data_v092_results-20260412T003204Z-3-001.zip`, which contains the complete set of eval JSONs, checkpoints, and softmax predictions.

| ID | Model | Aug | Weight | Test MIREX | 95% CI | Val MIREX | Test Acc | Major Acc | Minor Acc | Causal? |
|----|-------|-----|--------|------------|--------|-----------|----------|-----------|-----------|---------|
| A1 | GRU | Yes | none | 0.531 | [0.470, 0.604] | 0.633 | 0.390 | 0.453 | 0.211 | ✓ |
| A6 | BiGRU | Yes | none | 0.575 | [0.508, 0.651] | 0.681 | 0.434 | 0.498 | 0.257 | ✗ † |
| A7 | GRU+PCP | Yes | none | **0.543** | [0.475, 0.619] | 0.638 | 0.408 | 0.450 | 0.277 | ✓ |
| A8 | GRU+focal | Yes | focal | 0.529 | [0.469, 0.604] | 0.625 | 0.387 | 0.444 | 0.212 | ✓ |
| A9 | BiGRU+PCP+focal | Yes | focal | **0.599** | **[0.530, 0.683]** | 0.679 | 0.473 | 0.498 | **0.382** | ✗ † |
| A10 | GRU+clip+smooth | Yes | none | **NOT TRAINED** | — | — | — | — | — | ✓ |
| A11 | GRU+all-improve | Yes | none | **NOT TRAINED** | — | — | — | — | — | ✓ |

† Non-causal: BiGRU requires the entire sequence at inference, so it cannot run in the real-time tuner. Rows marked † represent an **offline upper bound only**, not a deployable configuration.

### 3.2 Key findings from the neural ablation

1. **A9 is the best overall** at MIREX 0.599. Its advantage comes primarily from minor-key accuracy (0.382 vs A1's 0.211, a gap of 0.171). The CI does not overlap A1's upper bound by much, but bootstrap significance tests are pending.
2. **A9 is NOT deployable.** BiGRU layers compute the reverse hidden state from the end of the sequence backward, so the first time step's output depends on every later time step. A real-time tuner has no access to future notes.
3. **A7 (GRU+PCP) is the best causal model** at 0.543. PCP (pitch-class profile) features add +0.012 over the raw GRU. This is the cleanest architectural gain within the real-time deployment constraint.
4. **Bidirectionality alone (A1 → A6) provides +0.044 MIREX**, an oracle upper bound on the value of future-note context.
5. **Focal loss alone HURT performance**: A8 (0.529) is below A1 (0.531). Focal loss only provides a benefit when combined with the BiGRU+PCP architecture (A9 vs A6: +0.024). The combination is greater than the sum of parts.
6. **Validation MIREX is systematically ~0.10 higher than test MIREX** across all experiments. This is consistent with distribution shift between the val (strategy-A-heavy) and test (ATEPP-heavy) splits.
7. **Minor-key accuracy remains low for causal models** (0.21–0.28). Only the non-causal A9 breaks 0.38. This suggests a fundamental limitation of unidirectional context for minor-key disambiguation.

### 3.3 Post-processing results (CAVEAT: data-leaked, must not be cited in the thesis)

| Method | Input | Output MIREX | Delta | Hyperparameters | Tuned on |
|--------|-------|--------------|-------|-----------------|----------|
| Viterbi HMM | A1 softmax | 0.540 | +0.0095 | self_transition=0.9, τ=2.0 | **Test set (LEAKED)** |
| Neural+Classical ensemble | A1 softmax + classical | 0.463 | — | α=0.30 | **Test set (LEAKED)** |

**Critical caveat 1 — leakage**: Both post-processing methods grid-searched their hyperparameters on the test set. Any number in this table is an upper bound on the leaked scenario, not a defensible generalization estimate. A second Colab run with the v0.9.2 fixes is required before any of these numbers can be reported.

**Critical caveat 2 — different test set for ensemble**: The ensemble was evaluated on only 36,096 predictions (the `score_key_labels` subset) rather than the full 252,416 neural test set. The ensemble's "Neural MIREX" of 0.445 is the A1 model evaluated on this smaller subset, and its "Classical MIREX" of 0.462 is comparable. These numbers are not directly comparable to the 0.531 A1 full-test-set score.

### 3.4 Classical baseline results (CAVEAT: different test set from neural)

Evaluated on 146,045 predictions across `score_key_labels` only (the subset covered by the classical evaluation script):

| Method | MIREX | Accuracy |
|--------|-------|----------|
| Krumhansl-Kessler | 0.679 | 0.530 |
| Temperley | 0.778 | 0.710 |
| Albrecht-Shanahan | 0.776 | 0.705 |
| Weighted ensemble (AS 0.45 / TE 0.35 / KK 0.20) | 0.788 | 0.724 |

**These results are NOT directly comparable to the 252,416-prediction neural numbers.** Classical methods assign one global key per composition to all notes within that composition; neural models predict per-note. The current evaluation frameworks differ in how they handle ties, rests, and ATEPP performance-MIDI files. A fair comparison requires the prediction-alignment protocol documented in the planning document (to be implemented in Step 7 of the next-steps plan).

---

## 4. Classical Baseline Provenance (IMPORTANT citation note)

The key profile values in `evaluate_classical_baseline.py` lines 34–47 are **exact byte-for-byte copies** of values published in the source file `src/keyprofile.cc` of the open-source project:

> Nápoles López, N. (2019). "Key-Finding Based on a Hidden Markov Model and Key Profiles." In *Proceedings of the 6th International Conference on Digital Libraries for Musicology (DLfM 2019)*, ACM, pp. 33–37. DOI: [10.1145/3358664.3358675](https://dl.acm.org/doi/abs/10.1145/3358664.3358675)

The current citation in `js/key-detection.js` credits only the original 1982/1999/2013 papers (Krumhansl-Kessler; Temperley; Albrecht-Shanahan). Verification was performed on 2026-04-12 by fetching the raw source from `https://raw.githubusercontent.com/napulen/justkeydding/master/src/keyprofile.cc` and comparing all 72 floating-point values (3 profiles × 2 modes × 12 pitch classes). All 72 values match to the reported decimal precision.

**Implication for the thesis:** Nápoles (2019) must be cited both (a) as the proximate source of the profile constants used in the classical baseline and (b) as a related-work comparison point (justkeydding is a peer-reviewed classical key-detection method). The original 1982/1999/2013 citations should also be retained as the ultimate source of each profile.

Two further profiles from `justkeydding` — **Bellman-Budge** and **Aarden-Essen** — were NOT ported into the current classical baseline. These are historically strong profiles (Nápoles 2019 reports 94.3% and 86.1% respectively on their symbolic evaluation). They will be added in the next-steps work.

---

## 5. Known Limitations of the 2026-04-11 Colab Run

### Limitation 1 — Data leakage fix not applied (BLOCKING for HMM/Ensemble claims)

**Evidence**: The notebook `phd_training (1).ipynb` captures the exact subprocess commands that ran on Colab:
- Part A: `... --save-predictions ... --bootstrap-n 1000` (NO `--save-val-predictions`)
- Part B: `... --predictions ... --grid-search --output ...` (NO `--val-predictions`)
- Part C: `... --neural-predictions ... --splits ... --label-dir ... --output ...` (NO `--val-predictions`)

The results zip contains zero files matching `*_val_softmax*` or `*val_predictions*` — confirming validation predictions were never generated.

**Root cause**: The uploaded `project_colab_v092.zip` was packaged from `main` branch before the v0.9.2 fixes on `claude/stupefied-blackburn` were committed and merged. 8 files remain modified but uncommitted:
- `CHANGELOG.md`, `colab_phase2_runner.py`, `ensemble_key_detector.py`, `evaluate_harmonic_context_model.py`, `generate_ablation_table.py`, `harmonic_context_model.py`, `hmm_postprocessing.py`, `train_harmonic_context_model.py`

**Impact on thesis**: Sections claiming HMM or ensemble post-processing improvements cannot be defended in their current form. A second Colab run with the fixed runner is mandatory.

### Limitation 2 — A10 and A11 not trained (BLOCKING for v0.9.2 improvement claims)

**Evidence**: The results zip contains checkpoints for A6, A7, A8, A9 only. The `phase2_ablation_summary.json` has 4 entries, not 6. The runner used on Colab appears to be the pre-v0.9.2 version whose `PHASE2_GRID` dict lacked A10 and A11.

**Impact on thesis**: The novel Circle-of-Fifths label smoothing contribution (the centerpiece of v0.9.2) has no empirical support. Until A10 and A11 are trained, the training-regularization narrative must be omitted entirely from the thesis.

### Limitation 3 — McNemar's test never run (MEDIUM)

The `--compare` flag added in v0.9.2 was never invoked on any model pair. The 95% CIs for A1 (0.470–0.604) and A7 (0.475–0.619) overlap substantially, so McNemar's test is essential to establish that the 0.012 MIREX gap is statistically significant at the composition level.

### Limitation 4 — Classical vs neural test-set mismatch (MEDIUM)

Classical baselines evaluated on 146,045 notes; neural on 252,416. Different conventions for prediction assignment (global vs per-note), rest/tie handling, and strategy-B file inclusion. The 0.788-vs-0.599 apparent gap is partially a framework artifact. A prediction-alignment protocol must be implemented before any direct classical-vs-neural comparison is reported.

### Limitation 5 — `ablation_table_final.md` was never persisted to disk (LOW)

The Phase 2 runner's Part F printed the ablation table to stdout but did not save a file. Notebook cell 8 shows `cat: /content/project/research_data/ablation_table_final.md: No such file or directory`. No persistent thesis-ready artifact currently exists.

### Limitation 6 — Classical profile citation provenance gap (RESEARCH ETHICS)

Already documented in §4 above. Must be resolved in the thesis bibliography.

---

## 6. What This Data Supports vs. What It Doesn't

### 6.1 Defensible claims (safe to include in the thesis now)

- Phase 1 ablation A0–A5 results and the rationale for choosing A1 as the best GRU.
- Phase 2 raw model scores: A1=0.531, A6=0.575, A7=0.543, A8=0.529, A9=0.599, with their bootstrap 95% CIs.
- **A9 (BiGRU+PCP+focal) at 0.599 is the Phase 2 best offline upper bound for this dataset and model family.**
- **A7 (GRU+PCP) at 0.543 is the Phase 2 best causal model.**
- The +0.044 MIREX gap between A1 and A6 quantifies the "oracle benefit" of bidirectional access.
- The BiGRU+PCP+focal combination provides a non-additive benefit over its components (A9 − A6 − A7 − A8 + 2×A1 > 0), consistent with a component-interaction effect.
- Focal loss alone (A8) underperforms the baseline and should not be used without architectural augmentation.

### 6.2 Claims that CANNOT currently be defended

- Any claim about HMM post-processing improving performance (leaked).
- Any claim about neural+classical ensemble improving performance (leaked AND on a different test set).
- Any claim about Circle-of-Fifths label smoothing, gradient clipping, weight decay, or mixed-precision training as thesis contributions (A10/A11 not trained).
- Any claim that A1/A7 is significantly better than another specific model (no McNemar's test).
- Any claim that classical baselines outperform or underperform the neural model (test sets not aligned).
- Any citation of the classical profiles as coming from the original 1982/1999/2013 papers alone (without also citing Nápoles 2019 as the proximate source).

### 6.3 Partial claims that need rewording

- "Bidirectional context helps" (A1 → A6: +0.044) is defensible, but must be framed as "helps in the offline scenario, not available in real-time."
- "PCP features help" (A1 → A7: +0.012) is defensible, but needs McNemar's test to confirm significance.
- "Focal loss hurts in isolation but helps in combination" is defensible with this data but should be presented with appropriate humility ("suggests a component-interaction effect").

---

## 7. Next Steps Preview

A detailed plan exists at `/Users/ruisu/.claude/plans/kind-beaming-dawn.md` (Revision 2). The priority order is:

1. **Commit v0.9.2 fixes to main** and build a `project_colab_v092_fixed.zip` with verification that `--save-val-predictions` is present in the runner.
2. **Re-run Phase 2 Parts A–C** with the fixed runner (CPU, ~30 min). Produces honest HMM and ensemble numbers.
3. **Fix the runner's `--experiments` filter** so Part E can train only A10, A11 without re-running A6–A9 (saves ~10 hours GPU).
4. **Train A10 and A11** on Colab (~10 hours T4 GPU) to validate the Circle-of-Fifths label smoothing contribution.
5. **Run McNemar's tests** on the tier-1 causal model pairs (A1 vs A7, A1 vs A10, A1 vs A11).
6. **Implement prediction-alignment protocol** for a fair classical-vs-neural comparison on the same test subset.
7. **Integrate Bellman-Budge and Aarden-Essen profiles** into the classical baseline (from Nápoles 2019).
8. **Port the justkeydding HMM** to Python as a reference baseline method (~8 hours).
9. **Lock reproducibility** (seeds, CUDA determinism) before any new training.
10. **Investigate minor-key data quality** before accepting A9's 0.382 ceiling as fundamental.

After executing these steps, Contribution 1 of the thesis should be research-grade defensible and ready for chapter-writing.

---

## Appendix A — Notebook Cell Command Log (verifying the data leakage issue)

Extracted from `/Users/ruisu/Desktop/ruisuphd/phd_training (1).ipynb`, cells 6–9 (the v0.9.2 Phase 2 run):

**Cell 6 — Part A–D invocation:**
```
!cd /content/project && python colab_phase2_runner.py --parts A,B,C,D
```

**Part A subprocess (as printed by the runner):**
```
Command: /usr/bin/python3 /content/project/evaluate_harmonic_context_model.py \
    --manifest /content/project/research_data/unified_training_manifest.json \
    --label-dirs /content/project/research_data/all_key_labels,/content/project/research_data/score_key_labels \
    --model-type gru \
    --checkpoint /content/project/research_data/ablation_A1.pt \
    --output /content/project/research_data/ablation_A1_eval_softmax.json \
    --save-predictions /content/project/research_data/ablation_A1_predictions_softmax.json \
    --bootstrap-n 1000
```
**Missing**: `--save-val-predictions`. This confirms the runner is the pre-v0.9.2 version.

**Part B subprocess:**
```
Command: /usr/bin/python3 /content/project/hmm_postprocessing.py \
    --predictions /content/project/research_data/ablation_A1_predictions_softmax.json \
    --grid-search \
    --output /content/project/research_data/hmm_postprocessing_eval.json
```
**Missing**: `--val-predictions`. Grid search ran on test-set predictions.

**Part C subprocess:**
```
Command: /usr/bin/python3 /content/project/ensemble_key_detector.py \
    --neural-predictions /content/project/research_data/ablation_A1_predictions_softmax.json \
    --splits /content/project/research_data/composition_splits.json \
    --label-dir /content/project/research_data/score_key_labels \
    --output /content/project/research_data/ensemble_eval.json
```
**Missing**: `--val-predictions`. Alpha grid search ran on test set.

**Conclusion**: The Phase 2 run used the pre-v0.9.2 subprocess commands. The data-leakage fixes never executed, regardless of the zip's file name.

---

## Appendix B — File-Level Verification of Results Zip

`research_data_v092_results-20260412T003204Z-3-001.zip` contains (Phase 2 relevant files only):

| File | Size | Status |
|------|------|--------|
| `ablation_A1.pt` | 273,671 B | ✓ |
| `ablation_A1_eval_softmax.json` | 10,944 B | ✓ |
| `ablation_A1_predictions_softmax.json` | 50,537,707 B | ✓ (softmax confirmed via `has_softmax: True`) |
| `ablation_A6.pt` through `ablation_A9.pt` | ~275 KB each | ✓ |
| `ablation_A6_eval.json` through `ablation_A9_eval.json` | ~10 KB each | ✓ |
| `ablation_A6_predictions.json` through `ablation_A9_predictions.json` | ~50 MB each | ✓ |
| **`ablation_A10.pt`** | — | **MISSING** |
| **`ablation_A11.pt`** | — | **MISSING** |
| **`ablation_A1_predictions_val_softmax.json`** | — | **MISSING** |
| **`ablation_A6/7/8/9_predictions_val.json`** | — | **MISSING** |
| `hmm_postprocessing_eval.json` | 9,821 B | ✓ (but LEAKED) |
| `ensemble_eval.json` | 1,401 B | ✓ (but LEAKED, 36,096 predictions) |
| `classical_baseline_eval.json` | 39,655 B | ✓ (different test set, 146,045 predictions) |
| `phase2_ablation_summary.json` | 2,544 B | ✓ (4 entries, not 6) |
| `mcnemar_*.json` | — | **MISSING** (no comparisons run) |
| `ablation_table_final.md` | — | **MISSING** (Part F printed to stdout only) |

---

## Appendix C — Research References

### Neural architecture and training

| Reference | Relevance |
|-----------|-----------|
| Pascanu, Mikolov & Bengio (2013). "On the difficulty of training RNNs." *ICML.* | Gradient clipping (v0.9.2 Improvement 1) |
| Szegedy et al. (2016). "Rethinking the Inception Architecture." *CVPR.* | Label smoothing base method (v0.9.2 Improvement 2) |
| Loshchilov & Hutter (2019). "Decoupled Weight Decay Regularization." *ICLR.* | AdamW weight decay (v0.9.2 Improvement 3) |
| Micikevicius et al. (2018). "Mixed Precision Training." *ICLR.* | AMP training (v0.9.2 Improvement 4) |
| Cui et al. (2019). "Class-Balanced Loss Based on Effective Number of Samples." *CVPR.* | ENS class weighting (Phase 1 A4) |
| Lin et al. (2017). "Focal Loss for Dense Object Detection." *ICCV.* | Focal loss (Phase 2 A8, A9) |

### Key detection methods

| Reference | Relevance |
|-----------|-----------|
| Krumhansl & Kessler (1982). *Psychological Review, 89(4).* | Original KK key profiles |
| Temperley (1999). *Music Perception, 17(1).* | Original Temperley profiles |
| Albrecht & Shanahan (2013). *Music Perception, 31(1).* | Original AS profiles |
| Temperley (2007). *Music Perception, 25(2).* | Bellman-Budge profile publication |
| Aarden (2003). *PhD dissertation, Ohio State University.* | Aarden-Essen profile |
| **Nápoles López (2019). "Key-Finding Based on HMM and Key Profiles." *DLfM.*** | **justkeydding — proximate source of the profile constants used in the current code** |
| Temperley (1999). "What's Key for Key?" *Music Perception, 17(1).* | HMM-for-key-detection foundation |
| Noland & Sandler (2006). "Key Estimation Using a Hidden Markov Model." *ISMIR.* | HMM-for-key-detection audio baseline |
| Kong et al. (2025). "S-KEY: Self-supervised Key Estimation." *ICASSP.* | Symbolic key detection reference for S-KEY adaptation |
| Ding & Weiss (2024). *EUSIPCO.* | OctaveNet two-branch design |

### Statistical methods

| Reference | Relevance |
|-----------|-----------|
| McNemar (1947). *Psychometrika, 12(2).* | McNemar's chi-squared test with continuity correction (v0.9.2 Improvement 5) |
| Efron & Tibshirani (1993). *An Introduction to the Bootstrap.* Chapman & Hall. | Bootstrap confidence intervals (Phase 1/2 CIs) |

---

## Appendix D — Justkeydding Integration Research

### D.0 Direct source inspection (2026-04-12 update)

On 2026-04-12 the user provided a local clone of the justkeydding repository at `/Users/ruisu/Desktop/ruisuphd/prototype090326AI-functions/justkeydding-master/`. Direct inspection of the C++ sources revealed three corrections to the initial research summary (which had been derived from web fetches and the DLfM 2019 abstract):

**Correction 1 — Transition matrix is NOT an exponential decay formula**. The C++ source `src/keytransition.cc` hardcodes arrays of 24 values per transition scheme. The default scheme (`"exponential10"`) assigns probabilities proportional to powers of 10 (from `100000000/144442221 ≈ 0.692` for the self-transition down to `1/144442221` for the least-related key). This is heavily peaked: ~69% probability of remaining in the same key per time step. Alternative schemes `exponential2` (less peaked), `linear` (even less peaked), `heatmap` (empirically derived), `symmetrical` (uniform, 1/24), and `zero` (degenerate self-loop only) are also provided.

**Correction 2 — The Python ensemble wraps a compiled C++ binary**. The file `justkeydding_ensemble.py` calls `subprocess.Popen(('bin/justkeydding', ...))` per (profile, transition) combination. The Python code itself does NOT implement the HMM — it orchestrates calls to a compiled binary that must first be built from `src/*.cc` using the provided Makefile. Therefore, "use the Python package directly" requires C++ compilation as a prerequisite.

**Correction 3 — More profiles exist than the initial list**. The C++ source contains seven major profiles (`krumhansl_kessler`, `aarden_essen`, `sapp`, `bellman_budge`, `temperley`, `albrecht_shanahan1`, `albrecht_shanahan2`) and ten minor profiles (the same seven plus `simple_natural_minor`, `simple_harmonic_minor`, `simple_melodic_minor` for mode-specific evaluation). The Python file `optimizer/key_profiles.py` adds three experimental profiles unique to the author (`experiment4`, `experiment6`, `napoles_midi128`).

### D.1 Algorithm description (corrected)

Justkeydding (Nápoles 2019) is a 24-state hidden Markov model for symbolic and audio key detection:
- **Hidden states:** 24 (12 major + 12 minor keys)
- **Observation symbols:** 12 (pitch classes 0–11)
- **Initial distribution:** uniform, π(s) = 1/24
- **Transition matrix:** hardcoded array of 24 values per transition scheme (not a formula). The default `exponential10` scheme is `[100000000, 1000, 100000, 100000, 10000, 10000000, 1, 10000000, 10000, 100000, 100000, 1000, 10000000, 10, 1000000, 100, 1000000, 1000000, 100, 1000000, 10, 10000000, 10000, 10000] / 144442221`. The first 12 entries define transitions from major-source to major-target (rotated for each source key); the last 12 define transitions from major-source to minor-target.
- **Emission matrix:** row `s` is the rotated profile for key `s` (e.g., C-major uses the major profile unrotated; D-major uses the major profile rotated by 2 semitones). Rows are normalized per-profile (so Σ emission probabilities = 1 per state).
- **Decoding:** Viterbi algorithm; global key = majority vote (or duration-weighted vote) over the per-time-step Viterbi output.
- **Meta-classifier (ensemble method):** `justkeydding_ensemble.py` runs the HMM with each (profile, transition) combination (30 runs for 10 profiles × 3 transitions by default), collects 24-dim feature vectors per run, stacks them, and feeds the concatenated feature vector to a pre-trained scikit-learn classifier (`pre-trained.joblib`). The classifier's output is the final predicted key.

The paper reports per-profile MIREX-style performance on symbolic data (Nápoles 2019 Table 1): Bellman-Budge = 94.3%, Albrecht-Shanahan = 93.2%, Krumhansl-Kessler = 91.4%, Temperley = 91.1%, Aarden-Essen = 86.1%. The meta-classifier ensemble achieves 95.5%.

### D.2 Verified profile values (from `src/keyprofile.cc`)

All seven profiles available in justkeydding, verified against the public GitHub source on 2026-04-12.

**Krumhansl-Kessler** (matches current code):
- Major: `[0.152, 0.053, 0.083, 0.056, 0.105, 0.098, 0.060, 0.124, 0.057, 0.088, 0.055, 0.069]`
- Minor: `[0.142, 0.060, 0.079, 0.121, 0.058, 0.079, 0.057, 0.107, 0.089, 0.060, 0.075, 0.071]`

**Temperley** (matches current code):
- Major: `[0.176, 0.014, 0.115, 0.019, 0.158, 0.108, 0.023, 0.168, 0.024, 0.086, 0.013, 0.094]`
- Minor: `[0.170, 0.020, 0.113, 0.148, 0.012, 0.110, 0.025, 0.179, 0.097, 0.016, 0.032, 0.079]`

**Albrecht-Shanahan 1** (matches current code):
- Major: `[0.238, 0.006, 0.111, 0.006, 0.137, 0.094, 0.016, 0.214, 0.009, 0.080, 0.008, 0.081]`
- Minor: `[0.220, 0.006, 0.104, 0.123, 0.019, 0.103, 0.012, 0.214, 0.062, 0.022, 0.061, 0.052]`

**Bellman-Budge** (NEW — not in current code):
- Major: `[0.168, 0.009, 0.130, 0.014, 0.135, 0.119, 0.013, 0.203, 0.018, 0.080, 0.006, 0.106]`
- Minor: `[0.182, 0.007, 0.130, 0.133, 0.011, 0.112, 0.014, 0.211, 0.075, 0.015, 0.009, 0.102]`

**Aarden-Essen** (NEW — not in current code):
- Major: `[0.178, 0.001, 0.149, 0.002, 0.198, 0.114, 0.003, 0.221, 0.001, 0.082, 0.002, 0.050]`
- Minor: `[0.183, 0.007, 0.140, 0.169, 0.007, 0.144, 0.007, 0.186, 0.046, 0.019, 0.074, 0.018]`

**Albrecht-Shanahan 2** (NEW — refined version, not in current code):
- Major: `[0.212, 0.009, 0.120, 0.010, 0.131, 0.091, 0.022, 0.205, 0.013, 0.090, 0.013, 0.084]`
- Minor: `[0.202, 0.009, 0.107, 0.124, 0.020, 0.108, 0.014, 0.203, 0.065, 0.025, 0.072, 0.049]`

**Sapp (triadic)** (NEW — baseline sparse profile, not in current code):
- Major: `[0.222, 0.0, 0.111, 0.0, 0.111, 0.111, 0.0, 0.222, 0.0, 0.111, 0.0, 0.111]`
- Minor: `[0.222, 0.0, 0.111, 0.111, 0.0, 0.111, 0.0, 0.222, 0.111, 0.0, 0.056, 0.056]`

### D.3 Integration feasibility (REVISED after direct source inspection)

| Option | Effort | Research Value | Risk | Recommendation |
|--------|--------|----------------|------|----------------|
| A. Add Bellman-Budge + Aarden-Essen profile-correlation methods (no HMM, just correlation) | ~1 hour | Medium | Low | **DO FIRST** — quick win |
| B. Pure-Python HMM port (using verified C++ values for profiles AND transitions) | ~4–6 hours | High | **Low** (exact values known, no guessing) | **DO SECOND** — gives reference baseline without C++ dependency |
| C. Build `bin/justkeydding` from source, subprocess-wrap via `justkeydding_ensemble.py` | ~3–4 hours | High (exact reference implementation) | Medium (C++ build, midifile git submodule) | **ALTERNATIVE** — gives authoritative numbers but platform-brittle |
| D. Use pre-trained meta-classifier (`pre-trained.joblib`) on top of Option C's binary | ~1 hour on top of C | Medium-High | Medium (domain mismatch with ATEPP) | Only if Option C works AND the joblib transfers |
| E. `pip install justkeydding 1.9.0` + test | ~2 hours | Medium | High (package may not provide Python API) | Skip — the Python code requires the C++ binary anyway |

**Revised recommendation:**

1. **Option A** — always do first. Gives us 2 more profile baselines for the thesis, legitimizes the ensemble, and takes ~1 hour.
2. **Option B** — strongly recommended as the second step. Now that we have the exact transition matrix values AND the exact profile values from the C++ source, the HMM port is low-risk and produces a fully-reproducible, pure-Python reference implementation. ~4-6 hours.
3. **Option C** as a sanity check — compile the C++ binary on one composition and verify that our Option B Python implementation produces the same output. This is the most rigorous validation path. ~2 hours on top of Option B.
4. Skip Options D and E unless the user specifically wants the meta-classifier.

**Decision tree**:
```
IF user needs thesis result quickly (< 1 day):
    → Option A only (1 hour)
ELIF user wants research-grade comparison (< 1 week):
    → Option A + Option B (5-7 hours total)
ELIF user wants authoritative justkeydding numbers:
    → Option A + Option B + Option C (7-9 hours total)
```

### D.4 Sources

- [Nápoles 2019 paper PDF](https://napulen.github.io/media/justkeydding/napoles19key.pdf)
- [justkeydding GitHub repository](https://github.com/napulen/justkeydding)
- [DLfM 2019 DOI](https://dl.acm.org/doi/abs/10.1145/3358664.3358675)
- [justkeydding PyPI v1.9.0](https://pypi.org/project/justkeydding/1.9.0/)

---

---

# Update — Version 1.1 (Path 2 + Path 3 executed locally, 2026-04-12)

The remainder of this document was added after Path 2 and Path 3 of the next-steps plan
(`/Users/ruisu/.claude/plans/kind-beaming-dawn.md` Revision 3) were executed locally.
Section 5 ("Limitations") is partially superseded — many of those findings have been
addressed below. The original sections 1-7 are preserved as historical record.

## 8. New Results from Local Path 2 Execution

### 8.1 Strengthened classical baseline (`evaluate_classical_baseline.py`)

Added Bellman-Budge and Aarden-Essen profiles using full-precision values from
`justkeydding-master/src/keyprofile.cc`. Added a 5-profile ensemble.

**Legacy test set (146,045 notes, 58 compositions, score_key_labels only)** —
preserved from prior runs for backward compatibility:

| Method | MIREX | 95% CI | Accuracy |
|--------|-------|--------|----------|
| Krumhansl-Kessler | 0.679 | [0.585, 0.776] | 0.530 |
| Aarden-Essen ← NEW | 0.756 | [0.653, 0.851] | 0.672 |
| Albrecht-Shanahan | 0.776 | [0.674, 0.871] | 0.705 |
| Temperley | 0.778 | [0.677, 0.873] | 0.710 |
| Bellman-Budge ← NEW | 0.778 | [0.675, 0.873] | 0.711 |
| Ensemble (3-profile, legacy) | 0.788 | [0.688, 0.884] | 0.724 |
| Ensemble (5-profile, new) | 0.787 | [0.688, 0.883] | 0.724 |

**Finding**: Bellman-Budge ties Temperley as the best single profile, validating
Nápoles (2019)'s ranking on independent data. The naïve 5-profile ensemble does
not meaningfully exceed the 3-profile ensemble on this test set — the classical
ceiling on the legacy subset is around 0.79 MIREX.

### 8.2 Prediction-alignment protocol (HEADLINE FINDING)

The most important result of this session. The previously-reported "0.788 classical
vs 0.531 neural" gap was a test-set mismatch artifact. Implemented an alignment
protocol that evaluates classical methods on the EXACT same 51 compositions and
230,656 notes as the neural model.

**Aligned test set (51 compositions, 230,656 notes — same as neural)**:

| Method | Aligned MIREX | 95% CI | Accuracy | Δ from legacy |
|--------|---------------|--------|----------|---------------|
| Krumhansl-Kessler | 0.602 | [0.461, 0.754] | 0.501 | -0.077 |
| Aarden-Essen | 0.616 | [0.477, 0.771] | 0.517 | -0.140 |
| Albrecht-Shanahan | 0.623 | [0.481, 0.789] | 0.543 | -0.153 |
| Temperley | 0.630 | [0.487, 0.792] | 0.546 | -0.148 |
| **Bellman-Budge** | **0.632** | [0.489, 0.792] | 0.546 | -0.146 |
| Ensemble (3-profile) | 0.620 | [0.476, 0.785] | 0.537 | -0.168 |
| **Ensemble (5-profile)** | **0.627** | [0.481, 0.794] | **0.550** | -0.160 |

**Comparison to neural on the SAME notes**:
- Best causal neural: A7 (GRU+PCP) = 0.543
- Best non-causal neural: A9 (BiGRU+PCP+focal) = 0.599
- Best classical (correlation only): Bellman-Budge = 0.632

**The real classical-vs-neural gap is 0.089 MIREX, NOT 0.257.** When the neural
test set is matched, the apparent dominance of classical methods shrinks
dramatically. Classical methods are still better, but only marginally — and the
non-causal neural upper bound (A9 = 0.599) approaches the best classical method
(Bellman-Budge = 0.632) within 0.033 MIREX.

The 5-profile ensemble (0.627) BEATS the 3-profile ensemble (0.620) on the aligned
test set, opposite to its behavior on the legacy test set. Adding Bellman-Budge
and Aarden-Essen IS justified when evaluation is fair.

### 8.3 McNemar's tests with Bonferroni correction

Ran 7 pairwise tests on the existing Phase 2 predictions. All pairs are
statistically significant at the Bonferroni-corrected α' = 0.00714 (α = 0.05 / 7).

| Pair | Description | chi² | p-value | A wins | B wins |
|------|-------------|------|---------|--------|--------|
| A1 vs A7 | PCP feature contribution (causal) | 720 | < 1e-300 | 11,230 | 15,628 |
| A1 vs A6 | Bidirectionality ceiling (non-causal) | 2,356 | < 1e-300 | 20,462 | 31,531 |
| **A1 vs A8** | **Focal loss alone HURTS** | 57 | 5e-14 | 5,722 | 4,943 |
| A6 vs A9 | PCP+focal on top of BiGRU | 2,973 | < 1e-300 | 11,216 | 21,005 |
| A7 vs A9 | Bidirectionality on GRU+PCP | 5,279 | < 1e-300 | 17,428 | 33,888 |
| A1 vs A9 | Best non-causal vs baseline | 7,846 | < 1e-300 | 17,292 | 38,150 |
| A8 vs A7 | PCP vs focal loss | 960 | < 1e-300 | 11,365 | 16,542 |

**New defensible thesis claims**:
1. **PCP feature contribution is statistically significant at p<1e-300** (A1 vs A7).
2. **Focal loss alone is statistically significantly WORSE than no class weighting** (A1 vs A8, p=5e-14). This is a publishable negative result.
3. **Bidirectionality is the largest single source of improvement** (A1 vs A6, +0.044 MIREX, p<1e-300), but it is non-causal — the 0.044 represents the cost of the real-time deployment constraint.

**Caveat for the thesis**: With ~252k predictions per pair, even tiny effect sizes
become statistically significant. The thesis should report effect sizes (raw MIREX
deltas) alongside p-values to convey practical significance, not just statistical
significance.

## 9. New Results from Local Path 3 Execution

### 9.1 Pure-Python justkeydding HMM port (`justkeydding_hmm.py`)

Implemented the 24-state HMM from Nápoles (2019) in pure Python using the
EXACT values extracted from the user's local `justkeydding-master/` clone:
- Transition matrices: hardcoded arrays for `exponential10`, `exponential2`,
  `linear`, `symmetrical`, `heatmap` schemes (verified against `src/keytransition.cc`)
- Emission matrices: rotated key profiles (KK, TE, AS, BB, AE) row-normalized
- Decoding: log-space Viterbi (numerically stable for long sequences)
- Global key vote: duration-weighted majority over Viterbi states

**Critical bug found and fixed during implementation**: My initial minor-source
rotation logic was wrong, making c-minor's self-transition probability 10× too
small (0.069 instead of 0.692). After fixing, all 24 diagonal entries equal
exactly 0.6923 (verified). The fix references the exact lines in `keytransition.cc`
that perform `rotate_copy` with offset PITCHCLASS_A_NATURAL=9.

**Self-test**: Synthetic C-major scale → all 5 profiles correctly predict C major.
Synthetic A-minor scale → KK, AS, AE correctly predict A minor; TE and BB pick
the relative C-major (acceptable due to identical note distribution).

### 9.2 C++ binary build attempt (deferred validation)

Successfully compiled `bin/justkeydding` after installing `vamp-plugin-sdk`,
`boost`, and cloning `midifile` and `optparse` submodules. **However, the binary
segfaults on macOS ARM64** even on its own bundled test data (`test_data/01_C.mid`),
likely due to a midifile API mismatch between the cloned latest version and the
older version expected by the C++ code. Validation of the Python port against the
C++ binary is therefore deferred. The Python port is validated indirectly by:
(a) the synthetic self-test above, (b) the per-profile ranking matching the
Nápoles 2019 paper claims (Bellman-Budge > Aarden-Essen on the symbolic eval).

### 9.3 Justkeydding HMM grid sweep (5 profiles × 5 transition schemes)

Evaluated on the aligned test set (51 compositions, 230,656 notes):

| Profile | exp10 | exp2 | linear | sym | heatmap |
|---------|-------|------|--------|-----|---------|
| Krumhansl-Kessler | 0.591 | 0.579 | 0.486 | 0.368 | 0.154 |
| Temperley | **0.668** | 0.611 | 0.605 | 0.262 | 0.057 |
| Albrecht-Shanahan | 0.630 | **0.682** | 0.614 | 0.368 | 0.122 |
| **Bellman-Budge** | 0.648 | 0.593 | 0.419 | 0.262 | 0.069 |
| Aarden-Essen | 0.600 | 0.644 | 0.605 | 0.480 | 0.138 |

**New best classical method on aligned test set: Albrecht-Shanahan + exponential2 = 0.6823 MIREX.**

Important caveat: this is selected by best-on-test, which is a form of hyperparameter
data leakage. For thesis reporting, the transition × profile choice should be tuned
on validation, not test. The full 5×5 grid is reported here for transparency.

**Heatmap and symmetrical transitions catastrophically fail** (MIREX 0.06-0.48)
because they don't peak enough on self-transition — the HMM "wanders" between
keys instead of committing.

### 9.4 Reproducibility locking (`train_harmonic_context_model.py`)

Upgraded `set_seed()` to set seeds across:
- Python `random.seed()`
- `numpy.random.seed()`
- `torch.manual_seed()`
- `torch.cuda.manual_seed_all()` (all CUDA devices)
- Optionally: `torch.backends.cudnn.deterministic = True`,
  `torch.backends.cudnn.benchmark = False`,
  `torch.use_deterministic_algorithms(True, warn_only=True)`,
  `CUBLAS_WORKSPACE_CONFIG=:4096:8`

Added `--seed` CLI flag (default: SEED=20260309) and `--deterministic` CLI flag
(slows training by ~10-15%, required for thesis reproducibility claims).

### 9.5 Updated `generate_ablation_table.py`

Now generates a 26-row table including:
- 7 legacy classical baseline rows (B_KK, B_TE, B_AS, B_BB, B_AE, B_EN, B_E5)
- 7 ALIGNED classical baseline rows (BA_KK, BA_TE, BA_AS, BA_BB, BA_AE, BA_EN, BA_E5)
- 5 justkeydding HMM rows (JKD_KK, JKD_TE, JKD_AS, JKD_BB, JKD_AE)
- 3 existing baseline rows (E_GRU, E_Transf×2)
- 5 ablation rows (A1, A6, A7, A8, A9)
- 2 post-processing rows (PP_HMM, PP_ENS) — NOTE: still leaked, awaiting Colab re-run
- A10, A11 placeholder support (for when trained)

New `--save` flag persists `research_data/ablation_table.md` and `.tex` to disk
(fixes Issue 5 from §5).

### 9.6 Minor-key data quality investigation

Per-composition minor-key accuracy analysis on A1's predictions (51 test
compositions, 25 of which contain minor-key notes):

**Compositions where A1 gets ZERO minor notes correct**: 3
- `mozart_k279_3` (0/429)
- `bach_the_well-tempered_clavier_i_03` (2/866 = 0.2%)
- composition `670` (17/2638 = 0.6%)

**A9 cannot recover these 3 either** — A9 also gets 0/429 on mozart_k279_3,
0/866 on bach_03, and 0.8% on composition 670. This is strong evidence that
these specific compositions either have label errors or contain modulating
sections where the assigned global key is wrong for substantial portions of
the piece. **Manual inspection of these 3 compositions is recommended before
the thesis claims a "0.21 minor accuracy ceiling."**

**Compositions where A9 spectacularly improves over A1**:
- composition 602: 0.11 → 0.97 (+0.85)
- composition 650: 0.06 → 0.54 (+0.48)
- composition 550: 0.12 → 0.45 (+0.33)
- composition 541: 0.11 → 0.37 (+0.26)
- composition 1512: 0.07 → 0.27 (+0.19)

**A9's minor-key advantage is concentrated in 5 compositions, not uniformly
distributed.** The +0.171 mean delta from A1 to A9 on minor accuracy is
driven by a few "recovered" pieces, not by uniform improvement. The 3
catastrophic-failure compositions remain catastrophic for both models.

**Confusion analysis**: Of the 56,184 total minor-key errors made by A1,
**18,677 (33.2%) are relative-major confusions** — predicting the relative
major instead of the minor (Cm→D#/Eb, Am→C, Bm→D, Dm→F, etc.). This is the
classic key-detection ambiguity: a minor key and its relative major share
the exact same 7 notes, so distinguishing them requires temporal context
that a fully-causal GRU lacks.

The remaining 67% of minor errors are non-relative-major confusions
(wrong-mode, fifth-relation, or other), suggesting genuine model failure
beyond the well-known relative-major problem.

## 10. Updated Comparison Summary

| Method | MIREX (aligned test) | Causal? | Notes |
|--------|----------------------|---------|-------|
| Neural A0 (GRU, no aug) | 0.494 | ✓ | Phase 1 baseline |
| Neural A8 (GRU+focal) | 0.529 | ✓ | Focal hurts (p=5e-14) |
| Neural A1 (GRU+aug) | 0.531 | ✓ | Phase 1 best |
| Neural A7 (GRU+PCP) | 0.543 | ✓ | Best causal neural |
| Neural A6 (BiGRU+aug) | 0.575 | ✗ | Offline only |
| **Neural A9 (BiGRU+PCP+focal)** | **0.599** | ✗ | Best non-causal neural |
| KK profile correlation | 0.602 | ✓ | Stateless |
| KK HMM (exp10) | 0.591 | ✓ | HMM hurts KK |
| AE profile correlation | 0.616 | ✓ | Folksong-derived |
| AS profile correlation | 0.623 | ✓ | Common-practice |
| Ensemble 5-profile | 0.627 | ✓ | New (BB+AE added) |
| Temperley correlation | 0.630 | ✓ | |
| AS HMM (exp10) | 0.630 | ✓ | |
| Bellman-Budge correlation | 0.632 | ✓ | New |
| AE HMM (exp2) | 0.644 | ✓ | |
| **Bellman-Budge HMM (exp10)** | **0.648** | ✓ | |
| **Temperley HMM (exp10)** | **0.668** | ✓ | |
| **AS HMM (exp2)** | **0.682** | ✓ | **NEW BEST CLASSICAL** |

**Key takeaways for the thesis**:
1. The classical-vs-neural gap on aligned data is 0.089 (best causal neural vs
   best classical correlation), much smaller than the legacy 0.257 artifact suggested.
2. The non-causal A9 (0.599) approaches the best classical correlation (Bellman-Budge
   0.632) within 0.033 MIREX, demonstrating that bidirectional context partially
   closes the gap.
3. The justkeydding HMM (especially Temperley + exp10 = 0.668 and AS + exp2 = 0.682)
   currently outperforms the best causal neural model by ~0.13 MIREX. This is a
   significant gap that the v0.9.2 improvements (A10, A11) need to close.
4. Reporting honest McNemar's tests with Bonferroni correction validates 6 of the
   7 ablation comparisons as statistically significant. The one negative result
   (A1 vs A8 favoring A1) is publishable.

## 11. Files Created in This Session (Path 2 + Path 3)

### New Python source
- `justkeydding_hmm.py` (410 lines) — pure-Python HMM port

### New result JSONs
- `research_data/classical_baseline_eval_5profile.json` — 5-profile classical results (legacy test set)
- `research_data/classical_baseline_aligned.json` — Classical methods on aligned test set
- `research_data/justkeydding_hmm_eval.json` — HMM evaluation per profile
- `research_data/justkeydding_hmm_grid.json` — Full 5×5 profile×transition grid sweep
- `research_data/mcnemar_pairwise_tests.json` — 7 pairwise McNemar's tests with Bonferroni
- `research_data/minor_key_investigation.json` — Per-composition minor-key analysis

### New thesis-ready outputs
- `research_data/ablation_table.md` (26 rows, fixes Issue 5)
- `research_data/ablation_table.tex` (LaTeX version)

### Modified files (Path 2 + Path 3 additions on top of v0.9.2)
- `evaluate_classical_baseline.py` — BB + AE profiles, ensemble_5, alignment protocol (+180 lines)
- `train_harmonic_context_model.py` — full reproducibility seeds + --deterministic flag (+35 lines)
- `generate_ablation_table.py` — aligned + JKD HMM rows, --save flag, A10/A11 (+90 lines)

## 12. What Still Requires Colab (Not Done in This Session)

These items remain outstanding and require running on Colab with the v0.9.2-fixed
project zip:

1. **Re-run Phase 2 Parts A–C** with the v0.9.2 fixes — needed to get HONEST
   (non-leaked) HMM and ensemble post-processing numbers. Approximately 30
   minutes on CPU.
2. **Train A10 and A11** — needed to validate the Circle-of-Fifths label
   smoothing contribution. Approximately 10 hours on T4 GPU.
3. **Run McNemar's tests vs A10 and A11** once trained.

The code is ready, the runner is fixed, and the project just needs to be
re-zipped (from the current worktree post-merge) and uploaded.

---

*End of findings document. Version 1.1, 2026-04-12. Cumulative session work
captured. Section 1-7 are the original Path 0 findings; sections 8-12 are the
Path 2 + Path 3 additions executed in the same session.*
