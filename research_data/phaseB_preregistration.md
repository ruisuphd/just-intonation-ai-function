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

## 0. A1-corrected baseline (finalized 2026-04-14)

Measured on 3 seeds (20260309, 20260310, 20260311) under `--weight-mode sqrt`,
`--selection-metric val_mirex`, `--require-causal`, `--deterministic`,
30 epochs with patience=10:

| Aggregation | MIREX | 95% CI | σ_bootstrap |
|---|---:|---:|---:|
| **Frame-weighted (canonical)** | **0.5026** | [0.4336, 0.5889] | 0.0400 |
| Composition-equal | 0.5802 | [0.5186, 0.6390] | 0.0310 |

- σ(test-MIREX across seeds) = **0.0088** (meets Phase A target σ ≤ 0.01)
- Minor mean accuracy = **0.3245** (σ = 0.0120)
- Major mean accuracy = **0.3979** (σ = 0.0132)
- Val MIREX = **0.6109** (σ = 0.0020, extremely stable)
- Val-to-test drift = **−0.1126** (systematic across seeds, not seed noise)

**This is the baseline every Phase B cell is compared against.** Per-composition
MIREX arrays for all 3 seeds are persisted in `phase_a_seeds_2026-04-14/*_predictions.json`;
paired bootstrap against A1-corrected does not require re-running A1.

---

## 1. Research question

Under the corrected evaluation pipeline (val-MIREX checkpoint selection,
unified N=58 test split with paired cluster bootstrap, fixed ensemble + HMM
paths, class weighting restored per Phase 1 intent), does any fully-causal,
<20ms-deployable architecture exceed the Phase 2 A1-corrected baseline by
at least Δ=0.015 MIREX at p<0.05?

Three outcomes are all Phase B successes:

- **Winner.** A specific architecture + loss configuration clears Δ=0.015
  MIREX vs A1-corrected at p<0.05 paired cluster-bootstrap **AND** σ(test-MIREX)
  ≤ 0.015 across 3 seeds **AND** minor mean accuracy ≥ 0.32 (no regression vs
  A1-corrected). That configuration is carried into Phase C for pretraining.
- **Null + ceiling.** No configuration clears the bar. Ceiling ~ 0.50 MIREX
  (frame-weighted, causal, sqrt-weighted, val-MIREX-selected, 3-seed mean) is
  reported as the defensible upper bound at this data and compute scale.
  Phase C pivots to testing whether pretraining can move the ceiling.
- **Partial.** One configuration clears (1) and (2) but not (3) — i.e. higher
  aggregate MIREX with minor-class regression. Reported as a design tradeoff,
  not a win. May still go to Phase C if the minor regression is <0.02.
- **Aggregate-only.** Cell clears Δ=0.015 single-seed at p<0.05 but σ > 0.015
  across 3 seeds, i.e. seed noise inflated the single-seed number. Reported
  as "single-seed artefact" — explicitly not a winner.

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

(This section remains empty until Phase B is running. Any deviation from §2–§7
must be recorded here with date, diff link, and rationale.)
