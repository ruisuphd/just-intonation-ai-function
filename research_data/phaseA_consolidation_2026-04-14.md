# Phase A Consolidation — A1-corrected, 3-seed stability report

**Date:** 2026-04-14
**Branch:** `main` (commits `7bcf9ab`, `9c1ddca`, `2faf7b9`, `10d8524`)
**Purpose:** Ship a defensible A1-corrected baseline with measured seed variance, so Phase B can start against honest numbers. Closes the Phase A goal in `/Users/ruisu/.claude/plans/quizzical-toasting-rainbow.md`.

---

## 1. Provenance

Three 30-epoch training runs, identical config except for `--seed`. All artefacts in `phase_a_seeds_2026-04-14/` (Google Drive backup preserved).

**Config (uniform across seeds):**

| Flag | Value |
|---|---|
| `--weight-mode` | `sqrt` |
| `--selection-metric` | `val_mirex` |
| `--require-causal` | ✅ |
| `--allow-oracle` | ❌ |
| `--deterministic` | ✅ (CUBLAS_WORKSPACE_CONFIG + cudnn.deterministic) |
| `--epochs` | 30 |
| `--warmup-epochs` | 3 |
| `--patience` | 10 |
| `--batch-size` | 8 |
| `--learning-rate` | 1e-3 |
| `--bootstrap-n` (eval) | 10,000 |
| `--causal-only` (eval) | ✅ |
| Model | `HarmonicContextGRU` (hidden=96, bidirectional=False, gru_pcp=False) |
| Label dirs | `wir_key_labels`, `dcml_key_labels`, `score_key_labels` |
| Manifest | `unified_training_manifest.json` |
| Train / val / test | 250 / 28 / 41 files (all ATEPP in manifest mode) |

**Verified checkpoint metadata is consistent** across all 3 seeds (same weight_mode, same causal flags, same hyperparameters). The only intended variance is the `--seed` argument.

**Minor bug found:** the `seed` field inside each checkpoint records `20260309` (the module-level `SEED` constant) instead of the runtime `args.seed`. Training output confirms correct seed use per run (via `Random seed: <n>` line). Fix queued — see §8.

## 2. Headline metrics per seed

| Seed | Best epoch | Train ep. | Val MIREX | Test MIREX (frame) | Test acc | Bootstrap mean | 95% CI | σ_bootstrap | Major mean acc | Minor mean acc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20260309 | 20 | 30 | 0.6098 | **0.5085** | 0.3718 | 0.5121 | [0.4431, 0.5974] | 0.0398 | 0.4048 | 0.3371 |
| 20260310 | 11 | 21 (ES) | 0.6096 | 0.4921 | 0.3576 | 0.4950 | [0.4238, 0.5826] | 0.0409 | 0.3827 | 0.3232 |
| 20260311 | 20 | 30 | 0.6132 | 0.4946 | 0.3583 | 0.4990 | [0.4293, 0.5821] | 0.0396 | 0.4063 | 0.3133 |

**Seed 20260310 early-stopped at epoch 21 (patience=10 from best at epoch 11).** The other two peaked at epoch 20 and ran to full 30 epochs. This is a training-dynamics instability worth flagging: ~1/3 of seeds peak ~halfway through, 2/3 peak at epoch 20. Not enough data to generalize.

## 3. Seed-stability summary

| Statistic | Mean | σ | Max − min | Phase A target | Status |
|---|---:|---:|---:|---:|:-:|
| Test MIREX (frame-weighted) | **0.4984** | 0.0088 | 0.0164 | σ ≤ 0.01, max−min ≤ 0.025 | ✅ |
| Val MIREX | 0.6109 | 0.0020 | 0.0036 | — | ✅ (very stable) |
| Major mean accuracy | 0.3979 | 0.0132 | 0.0236 | — | ⚠️ larger than test |
| Minor mean accuracy | 0.3245 | 0.0120 | 0.0238 | — | ⚠️ larger than test |
| Val-to-test drift | −0.1126 | 0.0095 | 0.0173 | — | systematic, not noise |

**Phase A stability criterion met:** σ(test-MIREX) = 0.0088 ≤ 0.01. No escalation to 5 seeds required.

**But val-to-test drift is systematic at −0.11 across all seeds.** Val MIREX ≈ 0.61 universally; test MIREX ≈ 0.50 universally. This is *not* a val-loss-vs-val-MIREX selection artefact; it's a real distribution shift or sampling artefact. Composer histograms from the manifest diagnostic (cell 8 of `phd_training (3).ipynb`) show overlapping composer sets between val and test, so the cause is not gross composer leakage. Candidates for Phase B investigation: class-distribution mismatch (val might underrepresent hard minor classes), composition-size bias (val compositions may be smaller/easier), or augmentation-at-val-time carryover.

## 4. Combined 3-seed A1-corrected baseline (paired cluster-bootstrap, B=10,000, N=41)

Composition-level paired cluster bootstrap over all 41 test compositions, where each composition's MIREX is averaged across the 3 seeds before resampling:

| Aggregation | 3-seed combined MIREX | 95% CI | σ_bootstrap |
|---|---:|---:|---:|
| **Frame-weighted** (canonical) | **0.5026** | [0.4336, 0.5889] | 0.0400 |
| Composition-equal | 0.5802 | [0.5186, 0.6390] | 0.0310 |

**The A1-corrected baseline going forward is MIREX = 0.5026 (frame-weighted) with 95% CI [0.4336, 0.5889].** Any Phase B cell that beats A1-corrected must do so at Δ ≥ 0.015 at p < 0.05 paired bootstrap **and** σ ≤ 0.015 across 3 seeds.

## 5. Paired-bootstrap seed-vs-seed (reality check on sensitivity)

Testing whether any two seeds are statistically different at composition level:

| Comparison (frame-weighted) | mean Δ | 95% CI | p | Interpretation |
|---|---:|---:|---:|---|
| seed 309 vs 310 | +0.0158 | [−0.0087, +0.0416] | 0.228 | n.s. |
| **seed 309 vs 311** | **+0.0140** | **[+0.0036, +0.0268]** | **0.007** | ** significant |
| seed 310 vs 311 | −0.0017 | [−0.0269, +0.0221] | 0.921 | n.s. |

**Paired bootstrap detects a 0.014 MIREX difference between seeds 309 and 311 at p = 0.007** — despite their point-estimate difference being within the global bootstrap CI width. This is a *warning*: Phase B cells that beat A1 by only Δ = 0.015 at p < 0.05 could be partially seed noise rather than real architectural improvement. **Implication: Phase B success criterion should require replication across seeds, not just single-seed significance.**

## 6. Per-class accuracy across seeds

Minor-class stability is **much worse than aggregate stability**, which has implications for claim scoping:

| Class | n (test) | s309 | s310 | s311 | mean | σ per-class | Audited Phase 2 A1 | Δ vs audit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **F#m** | 706 | 0.262 | **0.084** | 0.285 | **0.210** | 0.110 | **0.000** | **+0.210** ✅ |
| Am | 7,364 | 0.064 | 0.166 | 0.098 | 0.109 | 0.052 | 0.111 | ≈0 ❌ |
| Fm | 3,568 | 0.221 | 0.032 | 0.217 | 0.157 | 0.108 | 0.196 | −0.039 |
| Gm | 3,372 | 0.344 | 0.282 | 0.383 | 0.336 | 0.051 | 0.117 | +0.219 ✅ |
| Bm | 13,158 | 0.176 | 0.050 | 0.224 | 0.150 | 0.090 | 0.109 | +0.041 |
| A#m | 3,682 | 0.186 | 0.134 | 0.175 | 0.165 | 0.027 | 0.162 | ≈0 |
| D#m | 5,458 | 0.656 | 0.293 | 0.310 | 0.420 | **0.205** | — | — |
| Cm | 14,694 | 0.349 | 0.552 | 0.330 | 0.410 | 0.123 | — | — |
| Dm | 3,322 | 0.300 | 0.500 | 0.292 | 0.364 | 0.118 | — | — |
| C#m | 552 | 0.491 | 0.685 | 0.493 | 0.556 | 0.111 | — | — |

**Interpretation:**
- **F#m is the headline win but unreliable.** 2/3 seeds recover F#m to ~0.27, 1/3 degenerate to ~0.08. Mean 0.210 is a genuine improvement over audited 0.000 but not a solid deployment-grade number.
- **Am stays collapsed** (0.109, unchanged from audited 0.111). sqrt weighting + val-MIREX selection does not rescue Am.
- **Gm went from 0.117 to 0.336** — a real and more stable win (σ=0.051).
- **D#m, Cm, Dm are extremely seed-sensitive** (σ = 0.20, 0.12, 0.12). These classes were not individually reported in the audited findings so we can't A/B them.

All 12 major classes have σ ≤ 0.053 per-class accuracy. All 12 minor classes except A#m have σ ≥ 0.05 per-class accuracy. **Minor-class variance is systematically larger**, which means even with seed stability at the aggregate level, specific minor classes flip between "recovered" and "collapsed" depending on seed. For Phase B, this means the `{ens, focal}` ablation axes need to be evaluated on per-class stability, not just aggregate MIREX.

## 7. Per-composition difficulty map

41 test compositions. Mean composition MIREX (equal-weighted across seeds) ranges from 0.12 to 0.90.

**Reproducibly hardest 5 (worst across all 3 seeds — candidate error-slice targets for Phase D):**

| Composition ID | n frames | s309 | s310 | s311 | mean | σ |
|---:|---:|---:|---:|---:|---:|---:|
| 670 | 3,328 | 0.133 | 0.118 | 0.118 | **0.123** | 0.009 |
| 122 | 6,144 | 0.240 | 0.222 | 0.200 | 0.221 | 0.020 |
| 1512 | 16,896 | 0.253 | 0.277 | 0.231 | 0.254 | 0.023 |
| 1257 | 1,792 | 0.324 | 0.303 | 0.328 | 0.319 | 0.013 |
| 728 | 8,704 | 0.320 | 0.341 | 0.309 | 0.323 | 0.016 |

Composition 670 was also the worst performer in the Phase 2 audited HMM eval (~0.15 per findings doc). **Reproducible worst performers exist and should become the reference cases for Phase D error analysis.**

**Reproducibly easiest 3:**

| Composition ID | n frames | s309 | s310 | s311 | mean | σ |
|---:|---:|---:|---:|---:|---:|---:|
| 546 | 1,024 | 0.927 | 0.935 | 0.842 | **0.901** | 0.052 |
| 7 | 3,328 | 0.809 | 0.947 | 0.880 | 0.879 | 0.069 |
| 1147 | 6,912 | 0.874 | 0.863 | 0.868 | 0.869 | 0.005 |

**Highest-variance compositions (least stable across seeds — candidate for seed-sensitivity ablation):** 515, 77, 672, 547, 650 — each with σ ≥ 0.12. These are where seed noise dominates.

## 8. Outstanding issues / cleanup

1. **Checkpoint `seed` field bug** (minor, provenance-only). `train_harmonic_context_model.py` saves `'seed': SEED` (module constant) rather than the actual runtime seed. Training output prints the correct seed so this is a logging defect, not a data defect. Fix: change to `'seed': (args.seed if args.seed is not None else SEED)`. Pending commit.

2. **The `--label-dir` CLI arg still points at `score_key_labels/` as default**, and the `--label-dirs` plural arg prepends it redundantly (notebook output: `['research_data/score_key_labels', 'research_data/wir_key_labels', 'research_data/dcml_key_labels', 'research_data/score_key_labels']` has `score_key_labels` twice). Harmless (label resolution finds the first hit) but ugly. Low priority — file a follow-up cleanup.

3. **Val-to-test drift is systematic at −0.11.** Needs a deliberate investigation before Phase B finalizes. Phase B pre-registration should include a composer/era/size stratified check of val vs test.

4. **HMM cleanup test (`test_hmm_postprocessing_accuracy.py`) not yet run on Colab.** Run once and confirm it passes before the first Phase B grid cell.

5. **Ensemble + HMM eval of the new A1 checkpoint pending.** Run `colab_phase2_runner.py --parts B,C,D` on the 3-seed A1 checkpoints using their val_predictions JSONs.

## 9. Phase A verdict

**Phase A is complete and passes all its entry criteria for Phase B:**

- ✅ Seed σ ≤ 0.01 MIREX on A1-corrected (measured 0.0088)
- ✅ All 5 validated code bugs + 1 design regression fixed (7bcf9ab + 10d8524 follow-up)
- ✅ Two false-positive findings-doc claims retracted (§4.3, §4.7 in 9c1ddca)
- ✅ Manifest SHA + full config persisted in every result JSON (via Phase A causality block + checkpoint metadata)
- ✅ Paired cluster-bootstrap helper exercised with B=10,000 on 3 seed pairs (see §5)
- ✅ Per-composition MIREX arrays persisted (via `_predictions.json`) so any future experiment can re-run paired tests without re-inference

**The A1-corrected baseline for Phase B is:**

> **MIREX = 0.5026 (frame-weighted) [95% CI: 0.4336 – 0.5889]**
> **σ(test-MIREX across 3 seeds) = 0.0088**
> **Minor mean accuracy = 0.3245 (σ = 0.0120)**
> **Paired-bootstrap sensitivity: Δ = 0.014 MIREX detectable at p = 0.007**

Any Phase B cell claiming improvement must meet ALL three of:

1. Δ ≥ 0.015 MIREX vs A1-corrected at p < 0.05 paired bootstrap
2. σ across 3 seeds ≤ 0.015
3. Minor mean accuracy ≥ 0.32 (not regressive vs A1-corrected)

Claims that meet (1) and (2) but not (3) are reported as "higher aggregate MIREX with minor-class regression" and treated as a design tradeoff, not a win.

---

**Next:** update `phaseB_preregistration.md` with these numbers, then commit, then launch Phase B seed 1 of cell 1.
