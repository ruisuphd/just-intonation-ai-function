# Phase A Track 1 — HMM + Ensemble re-eval on A1-corrected (3 seeds)

**Date:** 2026-04-14
**Branch:** `main` (commits `7bcf9ab` → `9c1ddca` → `2faf7b9` → `10d8524` → `a864611` → `b959d7a` → this)
**Purpose:** Re-evaluate HMM post-processing and Neural+Classical ensemble against the consolidated A1-corrected baseline (mean test MIREX 0.4984 across 3 seeds), with all Phase A code paths and the now-fixed multi-dir label resolution. Closes Track 1 of the Phase A → Phase B handoff.

**Artefacts:**
- `research_data/phaseA_track1_results/hmm_eval_seed{20260309,10,11}.json` — per-seed HMM grid search (val-tuned, applied to test).
- `research_data/phaseA_track1_results/ensemble_eval_seed{20260309,10,11}.json` — per-seed ensemble grid search (val-tuned alpha).
- `research_data/phaseA_track1_results/aggregate_track1.py` — consolidation script.
- `research_data/phaseA_track1_results/phaseA_track1_summary_2026-04-14.json` — machine-readable aggregate.

---

## 1. Bugs found and fixed during Track 1

### 1.1 `bellman_budge` KeyError in `ensemble_key_detector.py`

**Symptom:** every ensemble call crashed with `KeyError: 'bellman_budge'` at `classical_score_distribution`.

**Cause:** commit `2fb8271` (v0.9.2 + Path 2/3) added `BELLMAN_BUDGE` and `AARDEN_ESSEN` to `evaluate_classical_baseline.PROFILES` (5 profiles total) but `ENSEMBLE_WEIGHTS` (the legacy 3-profile dict) wasn't extended. `ensemble_key_detector.py` iterated `PROFILES.items()` and looked up each name in `ENSEMBLE_WEIGHTS`, KeyErroring on the two new profiles.

**Fix:** iterate `ENSEMBLE_WEIGHTS.items()` instead, look up `PROFILES[name]`. Preserves the legacy 3-profile ensemble for backward compatibility with Phase 1/2 results.

### 1.2 Ensemble coverage bug — the *real* root of findings doc §4.2

**Symptom:** `ensemble_eval.json` evaluated only 36,096 frames across 5 compositions, vs the 230,656 frames the neural eval produced on N=41 compositions.

**Earlier diagnosis (incorrect):** Phase A commit `7bcf9ab` attributed §4.2 to label-dir resolution and added the `--label-dirs` plural flag. That fix was necessary but not sufficient — running the ensemble after the label-dir fix STILL produced 5-composition output.

**Actual cause:** `ensemble_key_detector.py:170` loaded test composition IDs from `composition_splits.json` (58 IDs, legacy non-manifest split). Predictions JSONs come from manifest-mode evaluation (41 IDs, ATEPP-only manifest split). The intersection of the two splits is 5 compositions (verified empirically: `set(splits['test']) ∩ set(predictions['compositions'])` = {1076, 1132, 1227, 1542, 670}). The ensemble silently filtered to that intersection and reported MIREX on it.

**Fix:** derive composition IDs from the predictions JSON itself. The predictions file is the source of truth for "what the neural eval was evaluated on". `splits_path` argument retained for backward compat but no longer drives composition selection — replaced with an informational note in stdout.

**Impact:** ensemble re-evaluation goes from MIREX 0.43 (5 comps) to MIREX 0.62 (41 comps). The audited Phase 2 conclusion that "the ensemble didn't help" was a coverage artefact — with proper coverage the ensemble is at parity with classical alone (~0.62, vs A1's 0.50).

### 1.3 Sanity check after fix

The aggregator's coverage check confirms the fix is correct:

```
seed 20260309: A1_test_mirex=0.5085  ens_neural_mirex=0.5085  diff=0.0000  [OK]
seed 20260310: A1_test_mirex=0.4921  ens_neural_mirex=0.4921  diff=0.0000  [OK]
seed 20260311: A1_test_mirex=0.4946  ens_neural_mirex=0.4946  diff=0.0000  [OK]
```

The ensemble's "neural_mirex" field (one-hot argmax over the predictions, no classical blending) now exactly matches the A1-corrected eval JSON's test MIREX on every seed. Coverage is identical.

## 2. HMM post-processing results

Applied `hmm_postprocessing.py --grid-search` to each A1 seed's predictions, with hyperparameters tuned on `_val_predictions.json` and applied to `_predictions.json`:

| Seed | A1 base test MIREX | HMM test MIREX | Δ | best self_t | best τ |
|---|---:|---:|---:|---:|---:|
| 20260309 | 0.5085 | **0.5193** | +0.0108 | 0.95 | 1.0 |
| 20260310 | 0.4921 | 0.5043 | +0.0122 | 0.85 | 1.0 |
| 20260311 | 0.4946 | 0.5033 | +0.0088 | 0.95 | 5.0 |
| **3-seed mean** | **0.4984** | **0.5090** | **+0.0106** | — | — |
| σ across seeds | 0.0088 | 0.0089 | 0.0017 | — | — |

**HMM gives a small but very consistent improvement** (σ_delta = 0.0017 — much tighter than the A1 base σ of 0.0088). The HMM is clamping per-frame predictions to slowly-varying paths, which catches genuine mis-classifications without over-smoothing.

The audited Phase 2 finding cited "+0.013 MIREX" from HMM (`hmm_postprocessing_eval.json`, see findings doc §4.3 footnote). Our 3-seed mean +0.011 is comparable. HMM's effect is robust to which A1 seed you start from.

## 3. Neural + Classical ensemble results

Grid-searched alpha ∈ {0.00, 0.05, …, 1.00} on `_val_predictions.json`, applied best alpha to `_predictions.json`:

| Seed | A1 base | Pure neural (test) | Pure classical (test) | Best blend | Best alpha |
|---|---:|---:|---:|---:|---:|
| 20260309 | 0.5085 | 0.5085 | **0.6201** | **0.6221** | 0.45 |
| 20260310 | 0.4921 | 0.4921 | 0.6201 | 0.6193 | 0.50 |
| 20260311 | 0.4946 | 0.4946 | 0.6201 | 0.6158 | 0.50 |
| **3-seed mean** | **0.4984** | 0.4984 | **0.6201** | **0.6190** | 0.48 |
| σ across seeds | 0.0088 | 0.0088 | 0.0000 | 0.0032 | — |

**This is the headline finding of Phase A.** The classical ensemble alone (KK + Temperley + Albrecht-Shanahan profile correlation, deterministic — no NN) achieves **0.6201 test MIREX** vs neural-alone **0.4984**. The blend doesn't meaningfully improve over classical (the +0.002 on seed 309 is single-seed noise; seeds 310 and 311 land slightly *below* classical).

**The neural model is currently underperforming a well-tuned classical baseline by 0.12 MIREX on this test set.** This was hidden in the audited Phase 2 results because the broken ensemble coverage (§1.2) reported ensemble at 0.49 — which made it look like neither neural nor blend beat the simple A1 baseline.

### 3.1 Val→test drift is symmetric across methods

Val-set sweep across the 3 seeds, alpha ∈ {0.00, 0.50, 1.00}:

| Seed | Val pure neural | Val pure classical | Val best blend |
|---|---:|---:|---:|
| 20260309 | 0.6098 | **0.7412** | 0.7645 |
| 20260310 | 0.6096 | 0.7412 | 0.7590 |
| 20260311 | 0.6132 | 0.7412 | 0.7572 |

Drift val → test:
- Neural: 0.61 → 0.50 (Δ ≈ **−0.11**)
- Classical: 0.74 → 0.62 (Δ ≈ **−0.12**)
- Blend: 0.76 → 0.62 (Δ ≈ **−0.14**)

**Both methods drift by roughly the same amount.** The val-to-test drift is a property of the data split (Track 2's class-distribution mismatch — JS-divergence 0.20), not of any one model class. This rules out "neural overfits val" as a sole explanation; the entire val set is unrepresentative of test.

## 4. Stratified analysis: where does each method win?

Stratifying the 41 test compositions by `n_unique_keys` (from `val_test_diagnostic_2026-04-14.json` per-composition detail):

| Stratum | n_comp | n_frames | Neural | Classical | Ensemble |
|---|---:|---:|---:|---:|---:|
| **Mono-tonal (1 key)** | 23 | 47,599 | 0.5692 | **0.8265** | 0.8300 |
| **Modulating (>1 key)** | 18 | 70,391 | 0.4551 | 0.4867 | 0.4826 |

Composition-equal means (each composition weight 1, regardless of size):

- Mono-tonal: neural 0.609 vs classical **0.842** vs ensemble 0.849
  - Neural wins in **4 of 23** mono-tonal compositions.
- Modulating: neural 0.543 vs classical **0.666** vs ensemble 0.650
  - Neural wins in **7 of 18** modulating compositions.

**Two facts to absorb:**

1. **Classical's dominance on mono-tonal is enormous** (0.83 vs 0.57 frame-weighted). On a piece in a single key throughout, KK/Temperley/AS profile correlation is essentially solved — many pieces score classical=1.000 exactly. Neural makes per-frame prediction noise that costs MIREX even when most frames are right.

2. **On modulating pieces the gap closes** but classical still wins on average. The modulating subset is also where ALL methods drop — even classical falls from 0.83 to 0.49. The neural model's purported value proposition (per-frame modulation tracking) is real but small at this scale.

This recasts the Phase B objective. The interesting research target is not "improve A1 by Δ=0.015" but "build a per-frame causal model that **specifically beats classical on modulating pieces**".

## 5. Updated Phase A summary table

| Method | Test MIREX (3-seed mean) | σ (seeds) | Δ vs A1-corrected | Δ vs classical |
|---|---:|---:|---:|---:|
| A1-corrected (causal GRU h=96, sqrt, val-MIREX, 30ep) | **0.4984** | 0.0088 | — | −0.122 |
| A1 + HMM (val-tuned τ, self_t) | 0.5090 | 0.0089 | +0.011 | −0.111 |
| Pure classical (KK + Temperley + AS, deterministic) | **0.6201** | 0.0000 | +0.122 | — |
| Neural+Classical blend (val-tuned alpha ≈ 0.48) | 0.6190 | 0.0032 | +0.121 | −0.001 |

## 6. Implications for Phase B

The Phase B pre-registration's success criteria (Δ ≥ 0.015 vs A1-corrected at p<0.05, σ ≤ 0.015, minor acc ≥ 0.32) are now too easy: classical alone hits Δ = 0.122 over A1 with no neural component at all. **Phase B should be reframed against classical as the strong baseline.**

Proposed amendments to `phaseB_preregistration.md`:

1. Add a **"strong baseline" comparison** alongside A1-corrected: every Phase B cell reports test MIREX vs both (a) A1-corrected and (b) classical baseline.
2. Tighten the win criterion: a Phase B cell is a **"deployable winner"** only if it beats classical by Δ ≥ 0.015 at p<0.05 paired-bootstrap **on the modulating subset** (since classical already wins mono-tonal). On the mono-tonal subset, simply not-regressing vs classical is acceptable.
3. Add a **stratified report**: every Phase B cell reports MIREX on the mono-tonal subset and modulating subset separately, in addition to the aggregate.
4. Treat A1-corrected (0.50) as "the architecture-only causal baseline before integrating any prior knowledge" — useful as a lower bound, not as the primary comparison target.

## 7. What this leaves for next research moves

**Two directions for Phase B framing:**

### Path A — close the gap to classical
Phase B grid as currently planned (causal-GRU/Transformer × {sqrt, ens} × {focal on/off}) tries to close the 0.12 gap to classical. Plausible if the gap is mostly per-frame prediction noise (HMM smoothing closes 0.01 of it; better regularisation, longer windows, ensemble distillation could close more). But classical's mono-tonal ceiling is 0.83 — to beat that on those pieces requires extracting MORE than the histogram, which is a hard ask of a per-note model.

### Path B — pivot to where neural can win
Reframe the project around modulating pieces. The neural model's value proposition is per-frame local key tracking, which classical fundamentally can't do. Build:
1. An **ensemble that uses neural confidence to gate when to override classical** (i.e., "trust classical's global key unless neural detects a modulation").
2. A **per-frame loss** that down-weights the easy mono-tonal frames (where classical already wins) and emphasises the modulating frames.
3. A **modulating-subset benchmark** that explicitly evaluates frame-level key transitions, not just argmax accuracy.

### Recommended hybrid
Run Phase B as planned (grid is small — 12 cells × 3 seeds = 36 runs ≈ 60 GPU-h) but report against BOTH baselines. Use the stratified mono/modulating breakdown as the primary evidence. If Phase B closes the global-MIREX gap to classical on modulating pieces, even by Δ=0.015, that's a publishable contribution. If it doesn't, pivot to Path B in Phase C and reframe the contribution narrative.

## 8. Outstanding cleanups

- `colab_phase2_runner.py` Parts B, C, D were written for the legacy `ablation_A1_predictions*.json` filenames. They now silently no-op against the Phase A `A1_phaseA_seed*_predictions*.json` files. Either generalize the runner or document it as deprecated; the standalone `hmm_postprocessing.py` and `ensemble_key_detector.py` CLIs (which Track 1 used directly) are the cleaner path forward.
- The unused `splits_path` argument in `evaluate_ensemble_on_compositions` should be made truly optional in a follow-up cleanup; for now it's just informational.
- Track 1 verified that `--causal-only` enforcement is working in eval. Confirm the same for the training runner before Phase B kicks off.

---

**Phase A status: complete.** Both Track 1 (HMM + ensemble) and Track 2 (val/test diagnostic + manifest audit) close cleanly. The headline numbers ship to Phase B as documented above.

**Next:** commit Track 1 results + ensemble fixes, then update `phaseB_preregistration.md` with the dual-baseline reporting requirement before launching Phase B cell 1.
