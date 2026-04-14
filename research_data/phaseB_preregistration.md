# Phase B Pre-Registration — Clean Causal Ablation

**Date written:** 2026-04-14 (to be finalized and frozen **before** any Phase B run begins)
**Plan reference:** `/Users/ruisu/.claude/plans/quizzical-toasting-rainbow.md` — Phase B (M3–M4)
**Branch:** `phase3-rigor` (to be created from `phase2-final-2026-04-14` tag)

This document is the commitment device for Phase B. Experiments that deviate
from this spec require a companion diff + rationale committed alongside the
results. The pre-registration is frozen once the first Phase B run kicks off;
any subsequent change is documented as a **Phase B-prime** amendment rather
than edited in place.

---

## 1. Research question

Under the corrected evaluation pipeline (val-MIREX checkpoint selection,
unified N=58 test split with paired cluster bootstrap, fixed ensemble + HMM
paths, class weighting restored per Phase 1 intent), does any fully-causal,
<20ms-deployable architecture exceed the Phase 2 A1-corrected baseline by
at least Δ=0.015 MIREX at p<0.05?

Three outcomes are all Phase B successes:

- **Winner.** A specific architecture + loss configuration clears Δ=0.015 at
  p<0.05 with σ(test-MIREX) ≤ 0.01 across 3 seeds. That configuration is
  carried into Phase C for pretraining.
- **Null + ceiling.** No configuration clears the bar. This is published as
  "the causal ceiling on this data at this compute scale is approximately
  <X>" — a defensible Paper 1 contribution on its own. Phase C pivots to
  testing whether pretraining can move the ceiling.
- **Partial.** One configuration clears the bar on main test (N=58) but not
  on `ext-test` (held-out ATEPP 20–40 pieces). Report both, flag as limited
  generalisation, and treat as a conditional winner.

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
- Label dirs: `all_key_labels/` + `score_key_labels/` (plural; no ATEPP-only restriction).
- Splits: `research_data/composition_splits.json` (train 217 / val 44 / test 58). Compositions verified non-overlapping.
- Ext-test: 20–40 held-out ATEPP pieces never used in train/val/test. Sampled once at Phase B entry and persisted in `research_data/ext_test_composition_ids.json`.

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
