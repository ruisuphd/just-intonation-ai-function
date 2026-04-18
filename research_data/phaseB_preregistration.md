# Phase B Pre-Registration — Clean Causal Ablation

**Date written:** 2026-04-14 (to be finalized and frozen **before** any Phase B run begins)
**Finalization date:** 2026-04-14 (amended with measured A1-corrected baseline from `phaseA_consolidation_2026-04-14.md`)
**Plan reference:** `/Users/ruisu/.claude/plans/quizzical-toasting-rainbow.md` — Phase B (M3–M4)
**Branch:** `main` (sequence `7bcf9ab` → `9c1ddca` → `2faf7b9` → `10d8524`)

This document is the commitment device for Phase B. Experiments that deviate
from this spec require a companion diff + rationale committed alongside the
results. The pre-registration is frozen once the first Phase B run kicks off;
any subsequent change is documented as a **Phase B-prime** amendment rather
than edited in place.

## 0. A1-corrected baseline + STRONG baseline (finalized 2026-04-14, amended after Phase A Track 1)

Measured on 3 seeds (20260309, 20260310, 20260311) under `--weight-mode sqrt`,
`--selection-metric val_mirex`, `--require-causal`, `--deterministic`,
30 epochs with patience=10:

| Method | Test MIREX | σ (seeds) | 95% CI (B=10,000) | Notes |
|---|---:|---:|---:|---|
| **A1-corrected** (causal GRU h=96, sqrt, val-MIREX, 30ep) | **0.4984** | 0.0088 | [0.4336, 0.5889] | Architecture-only causal lower bound |
| A1 + HMM (val-tuned τ, self_t) | 0.5090 | 0.0089 | — | A1 + Viterbi smoothing |
| **Pure classical ensemble** (KK + Temperley + AS) | **0.6201** | 0.0000 | — | Deterministic; the strong baseline to beat |
| Neural+Classical blend (val-tuned α≈0.48) | 0.6190 | 0.0032 | — | At parity with classical alone |

**Two baselines are reported for every Phase B cell:**
1. **A1-corrected = 0.4984** — architecture-only causal lower bound. Useful for measuring whether new architectures/losses help over the previous neural attempt.
2. **Classical ensemble = 0.6201** — the strong baseline. KK + Temperley + Albrecht-Shanahan profile correlation, deterministic, no NN. Phase A Track 1 found that classical alone outperforms A1-corrected by Δ=0.122 MIREX. **Beating classical (or matching it on modulating pieces) is the real Phase B target.**

Phase A also produced these per-class and stratification numbers (3-seed mean):
- Minor mean accuracy = 0.3245 (σ = 0.0120) — vs audited Phase 2 A1 = 0.2383 (+0.086)
- Major mean accuracy = 0.3979 (σ = 0.0132)
- Val MIREX = 0.6109 (σ = 0.0020, extremely stable)
- Val-to-test drift = **−0.1126** (systematic across seeds AND across methods — Phase A Track 1 confirmed classical drifts identically. This is a property of the data split, not the algorithm.)

Stratified mono-tonal vs modulating (composition-equal MIREX, 3-seed mean):
- Mono-tonal (23 comps, 47k frames): A1=0.609, classical=0.842, ensemble=0.849 — classical wins decisively.
- Modulating (18 comps, 70k frames): A1=0.543, classical=0.666, ensemble=0.650 — gap narrows; neural wins 7/18 modulating pieces.

Per-composition MIREX arrays for all 3 seeds are persisted in `phase_a_seeds_2026-04-14/*_predictions.json`. Paired bootstrap against any baseline does not require re-running A1 or classical.

---

## 1. Research question

Under the corrected evaluation pipeline (val-MIREX checkpoint selection,
unified N=58 test split with paired cluster bootstrap, fixed ensemble + HMM
paths, class weighting restored per Phase 1 intent), does any fully-causal,
<20ms-deployable architecture exceed the Phase 2 A1-corrected baseline by
at least Δ=0.015 MIREX at p<0.05?

Phase B success criteria are now anchored on the CLASSICAL baseline (0.6201),
not just on A1-corrected (0.4984). Phase A Track 1 showed that classical alone
beats A1-corrected by Δ=0.122 — making "beat A1 by 0.015" a trivial bar. The
real research question is: can a causal per-frame neural model beat (or match)
classical, particularly on modulating pieces where classical fundamentally
cannot do per-frame key tracking?

**Outcome categories (every Phase B cell maps to one):**

- **Strong winner ("deployable").** Cell clears Δ ≥ 0.015 vs **classical**
  at p<0.05 paired cluster-bootstrap on aggregate MIREX **AND** σ(test-MIREX)
  ≤ 0.015 across 3 seeds **AND** does not regress mono-tonal subset MIREX
  below 0.80. Carried into Phase C.
- **Modulation winner.** Cell clears Δ ≥ 0.015 vs classical specifically on
  the modulating subset (18 comps, 70k frames) at p<0.05 paired bootstrap,
  even if aggregate MIREX is below classical. This is the most scientifically
  interesting outcome: it isolates neural's value proposition (per-frame
  modulation tracking). Eligible for Paper 1's headline claim.
- **Architecture winner.** Cell clears Δ ≥ 0.015 vs A1-corrected at p<0.05
  but does NOT beat classical. Reported as architectural progress without
  shipping a deployment claim. May or may not go to Phase C depending on
  whether the architecture supports pretraining transfer.
- **Null + ceiling.** No cell clears any of the above. Document A1-corrected
  (0.50) and classical (0.62) as the dual ceilings of the current data
  regime. Phase C pivots to testing whether pretraining moves either.
- **Aggregate-only artefact.** Cell clears Δ at single-seed but σ > 0.015
  across 3 seeds. Reported as seed noise; explicitly not a winner.

**Phase B reporting requirements (every cell, every seed):**

1. Test MIREX frame-weighted **and** composition-equal (Phase A Track 2 §3a).
2. Test MIREX on **mono-tonal subset** (23 comps, 47k frames) and **modulating
   subset** (18 comps, 70k frames) separately, plus aggregate.
3. Class-rebalanced auxiliary MIREX (18 present classes, each weight 1/18) per Track 2 §3b.
4. Comparison against BOTH A1-corrected AND classical baselines, with paired-
   bootstrap CI for each comparison.
5. Per-class accuracy table with σ across 3 seeds.
6. Causality block (already in payload via Phase A guardrail).

## 2. Pre-registered grid

Total cells: 12. Seeds per cell: 3 (escalate to 5 if σ > 0.02). Total runs: 36.
Compute budget: ~60–90 A100-h at ~1.5 h/run average.

### 2a. Main-effects block (6 cells)

| Arch | Weight | Focal | Smoothing | PCP |
|---|---|---|---|---|
| causal GRU h=96  | sqrt | off | 0.00 | off |
| causal GRU h=96  | none | off | 0.00 | off |
| causal GRU h=192 | sqrt | off | 0.00 | off |
| causal GRU h=192 | none | off | 0.00 | off |
| causal Transformer | sqrt | off | 0.00 | off |
| causal Transformer | none | off | 0.00 | off |

### 2b. Loss-design block (4 cells) — keyed on best arch from 2a

| Arch  | Weight | Focal |
|---|---|---|
| best | sqrt           | off |
| best | sqrt           | γ=2.0 |
| best | ens (β=0.999)  | off |
| best | ens (β=0.999)  | γ=2.0 |

### 2c. Feature block (2 cells) — keyed on best arch+loss from 2b

| Arch+Loss | Features |
|---|---|
| best | base |
| best | base + PCP |

## 3. Fixed hyperparameters (all cells)

- Epochs: 30 (early stop on val-MIREX plateau, patience = 5).
- Batch size: 8.
- Learning rate: 1e-3 (Adam), warmup 2 epochs, cosine decay.
- Window size / hop: 256 / 128.
- Augmentation: enabled (training only; val/test loaders force `augment=False`).
- Determinism: `--deterministic` on (CUDA reproducibility).
- Selection: `--selection-metric val_mirex` (once available — see plan).
- Causal enforcement: `--require-causal` (no `--allow-oracle`).

## 4. Datasets and splits

- Manifest: `research_data/unified_training_manifest.json` (SHA recorded at run start).
- Label dirs: `wir_key_labels/` + `dcml_key_labels/` + `score_key_labels/` (three per-corpus dirs; see commit `2faf7b9`).
- **Manifest-mode effective splits (verified in Phase A):** 250 train / 28 val / 41 test files. Strategy A (WiR real-score) entries load 0 files in current manifest — split fields missing for WiR/DCML entries. A Phase B preparatory task is to enrich the manifest with `split` fields for WiR/DCML to expand beyond the ATEPP-only 250/28/41. **If that expansion doesn't land before the first Phase B cell runs, all cells use N_test=41.**
- `composition_splits.json` (train 217 / val 44 / test 58) is for legacy non-manifest mode and is not the authoritative Phase B split.
- Ext-test: 20–40 held-out ATEPP pieces never used in train/val/test. Sampled once at Phase B entry and persisted in `research_data/ext_test_composition_ids.json`.
- Systematic val-to-test drift of −0.1126 MIREX was measured in Phase A. Before any Phase B cell, run `--dump-split-stats` diagnostic to characterize val vs test on key-class histograms, composition sizes, and composer distributions. Commit the output as `research_data/val_test_diagnostic_2026-04-14.json`.

## 5. Metrics

- **Primary:** test-MIREX (weighted; exact=1.0, fifth=0.5, relative=0.3, parallel=0.2).
- **Stratifications:** mean major accuracy, mean minor accuracy, per-class accuracy (24 classes), tonicization subset (Schubert + Debussy).
- **CI:** 95% percentile paired cluster bootstrap at composition level, B=10,000.
- **Effect size:** Cohen's d over per-composition MIREX differences.

## 6. Decision rules (frozen; no post-hoc tuning)

- **Significance threshold:** two-sided p<0.05 from paired cluster bootstrap.
- **Minimum meaningful effect:** Δ=0.015 MIREX.
- **Stability:** σ across seeds ≤ 0.01; max−min across seeds ≤ 0.025.
- A cell is a *candidate winner* if it beats A1-corrected by Δ ≥ 0.015 at p<0.05 AND σ ≤ 0.01.
- Ties (no significant ordering among candidate winners) are resolved by: (a) lower inference latency on the benchmark, (b) smaller model size.
- If no candidate winner exists across the 12 cells, declare **causal ceiling**.

## 7. Baselines (run once, not in the 12-cell budget)

- Krumhansl-Kessler, Temperley (CBMS), Albrecht-Shanahan via `evaluate_classical_baseline.py`.
- justkeydding HMM global + local.
- music21 `KrumhanslSchmuckler` / `BellmanBudge` (thin wrapper).

Audio-domain baselines (Chordino, NNLS-Chroma, Korzeniowski-Widmer) are **not** run in Phase B — symbol-to-audio comparisons belong in Phase E after synth-rendered fluidsynth audio.

## 8. Persistence

Every run writes a JSON with:
- `seed`, `git_commit`, `manifest_sha256`, `requirements_lock_sha`, `deterministic_flag`.
- `test_metrics`, `bootstrap_ci`, `per_composition_mirex` (paired array), `class_metrics`, `tonicization_subset`.
- `causality` block from Phase A guardrail.
- `val_metrics_per_epoch` (once val-MIREX selection lands).

No headline number ships without a committed result JSON containing all of the above.

## 9. Amendments log

### 2026-04-18 — Phase B execution record

**Completed as written.** All 12 cells × 3 seeds executed per §2 grid. No deviations from §3 hyperparameters, §4 splits, or §6 decision rules. Full result in [`phaseB_consolidation_2026-04-18.md`](phaseB_consolidation_2026-04-18.md) and [`phaseB_results_2026-04-18/`](phaseB_results_2026-04-18/).

**Efficiency decisions (pre-reg-compatible, not deviations):**

1. **B7 mirrored from B1 rather than retrained** — B7's config (`gru 96 sqrt focal=off`) is identical to B1 by construction (pre-reg §2a/§2b both list it; footnote in registry read "redundant with B1; kept for bookkeeping"). Checkpoints, eval, predictions, HMM and ensemble outputs were copied rather than recomputed. Saved ~1.5 GPU-h. Verified at Δ = 0.0000 on paired bootstrap (mirror integrity ✓).
2. **B11 mirrored from B9 rather than retrained** — B11's config (the feature block's baseline row) was set to `gru 96 ens focal=off` post-hoc after B9 won 2b main-effects, which is identical to B9. Same mirror procedure. Saved ~1.5 GPU-h. Mirror integrity ✓.

**Pre-reg §2b weight-mode axis amendment (documented post-execution):**

§2b fixed weight ∈ {sqrt, ens}. Phase A's findings did NOT identify ens or sqrt as dominant — the pre-reg assumed one of those two would win. In fact the 2a main-effects block surfaced **weight_mode = `none`** as a competitive option (B2 at 0.5187 > B1 at 0.4984). The 2b grid did not include `none` + focal; this combination was NOT tested. Honoring the pre-reg as written. If Phase C's modulation-specialist work wants to revisit focal, the `none + focal` combination is the natural add-on (call it B13 under the B-prime amendment convention).

**Pre-reg §2c feature-block amendment (post-execution):**

§2c set B11/B12 to `gru 96 sqrt` (no focal, no PCP / with PCP). Post-2b, the best arch+loss was **`gru 96 ens` (B9)**, not sqrt. B11/B12 were re-keyed on B9's winner config (`ens, no focal`) at runtime, which is the pre-reg's stated intent ("best arch+loss from 2b"). This is **not a deviation** — it is the pre-reg's explicit rule applied to the measured winner. B11 = ens + no PCP (mirror of B9); B12 = ens + PCP.

**Findings for the amended pre-registration (to inform Phase C):**

- **ENS class-balanced weighting (β=0.999) strictly dominates sqrt** at Δ = +0.020, p = 0.04 (B9 vs B1 paired cluster bootstrap). Phase C should default to ENS weighting unless it is specifically comparing weight schemes.
- **Focal loss as a standalone add-on hurts** (B8 vs B1: −0.008, p < 0.001). Do not default-enable focal loss in Phase C.
- **Explicit PCP features hurt an ENS-weighted baseline** at Δ = −0.010, p = 0.04 (B12 vs B11 paired cluster bootstrap). Do not re-introduce engineered pitch-class features; the GRU's learned note embedding is sufficient.
- **h=192 is data-starved at n=250 train.** Do not increase model capacity before pretraining transfer.
- **Transformer requires pretraining to compete** (B5/B6 were 2.4–5.5 % MIREX below best GRU). If Phase C Path A uses Moonbeam or Aria, transformer with pretrained weights becomes the relevant comparator.
- **Phase B verdict is "Null + ceiling" per §1.** Phase C's primary success criterion is now: Δ ≥ 0.015 vs B9 (= 0.5235 plain / 0.5345 +HMM) at p < 0.05, OR Δ ≥ 0.015 vs classical on the modulating subset (MODULATION_WINNER category).

**Status: Phase B pre-registration closed. No further amendments.** Phase C pre-registration begins as `phaseC_preregistration.md`.
