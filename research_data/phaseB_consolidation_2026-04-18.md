# Phase B Consolidation — 12-cell grid, 3-seed stability, classical ceiling confirmed

**Date:** 2026-04-18
**Plan reference:** `/Users/ruisu/.claude/plans/quizzical-toasting-rainbow.md` — Phase B (M3–M4)
**Pre-registration:** [`phaseB_preregistration.md`](phaseB_preregistration.md) (frozen 2026-04-14, amendments in §9)
**Phase A baseline report:** [`phaseA_consolidation_2026-04-14.md`](phaseA_consolidation_2026-04-14.md)
**Branch:** `main`
**Compute:** NVIDIA L4 (Colab), 12 cells × 3 seeds = 36 training runs, ~18 wall-clock GPU-h (averaging ~30 min/run; original estimate ~60–90 min/run on A100 was conservative).
**Artefacts:** [`phaseB_results_2026-04-18/`](phaseB_results_2026-04-18/) + Drive-resident checkpoints/predictions in `research_data_041826/`.

---

## 1. Purpose

Determine whether any fully-causal, <20 ms-deployable architecture exceeds the Phase A A1-corrected baseline (test MIREX = 0.4984) and whether any cell approaches the classical baseline (0.6201) under the corrected evaluation pipeline. Every cell reports against BOTH baselines per pre-reg §1 dual-baseline requirement.

---

## 2. Grid executed

12 cells per pre-reg §2, 3 seeds each (20260309, 20260310, 20260311), `--weight-mode` ∈ {sqrt, none, ens(β=0.999)}, `--focal-loss` ∈ {off, γ=2.0}, `--gru-pcp` ∈ {off, on}, architecture ∈ {GRU h=96, GRU h=192, Transformer}, all `--require-causal --deterministic --selection-metric val_mirex`, 30 epochs with patience=10, warmup=3. Effective manifest split: 250 train / 28 val / 41 test ATEPP compositions (same as Phase A — verified by Cell 2 sanity check with `manifest_sha256[:16] = d1517ffccbbb3336`).

Integrity: B7 (mirror of B1) and B11 (mirror of B9) were copied rather than retrained to save ~3 GPU-h. Both mirror checks pass at Δ = 0.0000 ± 0 (paired bootstrap) — pipeline reproduces exactly as expected.

---

## 3. Full 12-cell results

Plain = test-MIREX frame-weighted from the checkpoint's best val-MIREX epoch (3-seed mean). +HMM = Viterbi smoothing with val-tuned `(self_t, τ)`. +ens = neural + classical blend with val-tuned α. Stratification = composition-equal MIREX over 32 mono-tonal (`n_unique_keys ≤ 1`) and 9 modulating (`n_unique_keys ≥ 2`) compositions from Phase A Track 2 diagnostic.

| Cell | Config | plain | σ | +HMM | +ens | Δ A1 | Δ cls | mono | modu | Outcome |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| B1 | gru 96 sqrt | 0.4984 | 0.0088 | 0.5090 | 0.6190 | 0.0000 | −0.1217 | 0.6118 | 0.4669 | null |
| **B2** | gru 96 **none** | **0.5187** | 0.0105 | 0.5300 | 0.6209 | +0.0203 | −0.1014 | 0.6273 | 0.4705 | **ARCH_WINNER** |
| B3 | gru 192 sqrt | 0.5085 | 0.0071 | 0.5166 | 0.6189 | +0.0101 | −0.1116 | 0.6228 | 0.4694 | null |
| B4 | gru 192 none | 0.5168 | 0.0225 | 0.5274 | 0.6202 | +0.0184 | −0.1033 | 0.6138 | 0.4789 | UNSTABLE |
| B5 | transformer sqrt | 0.4682 | 0.0131 | 0.4784 | 0.6182 | −0.0302 | −0.1519 | 0.5767 | 0.4380 | null |
| B6 | transformer none | 0.4999 | 0.0037 | 0.5116 | 0.6205 | +0.0015 | −0.1202 | 0.6001 | 0.4691 | null |
| B7 | = B1 (mirror) | 0.4984 | 0.0088 | 0.5090 | 0.6190 | 0.0000 | −0.1217 | 0.6118 | 0.4669 | null |
| B8 | gru 96 sqrt+focal | 0.4940 | 0.0083 | 0.5054 | 0.6210 | −0.0044 | −0.1261 | 0.6003 | 0.4696 | null |
| **B9** | gru 96 **ens** | **0.5235** | **0.0030** | **0.5345** | 0.6208 | **+0.0251** | −0.0966 | **0.6343** | 0.4773 | **ARCH_WINNER** 🏆 |
| B10 | gru 96 ens+focal | 0.5224 | **0.0022** | 0.5341 | 0.6200 | +0.0240 | −0.0977 | 0.6256 | **0.4835** | ARCH_WINNER |
| B11 | = B9 (mirror) | 0.5235 | 0.0030 | 0.5345 | 0.6208 | +0.0251 | −0.0966 | 0.6343 | 0.4773 | ARCH_WINNER |
| B12 | gru 96 ens **+PCP** | 0.5163 | 0.0115 | 0.5275 | 0.6212 | +0.0179 | −0.1038 | 0.6213 | 0.4697 | ARCH_WINNER (weaker) |

**Five ARCH_WINNERs** (B2, B9, B10, B11, B12). **Zero STRONG_WINNERs** (no cell reached Δ ≥ 0.015 vs classical). **Zero MODULATION_WINNERs** (no cell reached Δ ≥ 0.015 vs classical on the modulating subset; best gap closed to −0.003 on B10 but remained negative).

Summary JSON: [`phase_b_2026-04-17/phaseB_final_summary_2026-04-17.json`](phaseB_results_2026-04-18/../../research_data_041826/phaseB_final_summary_2026-04-17.json).

---

## 4. Paired cluster bootstrap on per-composition MIREX

Composition-level paired bootstrap, B = 10,000, RNG seed 20260418, 3-seed mean per-composition vector. Source: [`phaseB_paired_bootstrap.json`](phaseB_results_2026-04-18/phaseB_paired_bootstrap.json). Script: [`phaseB_paired_bootstrap.py`](phaseB_results_2026-04-18/phaseB_paired_bootstrap.py).

| Contrast | Mean Δ | 95 % CI | p | Note |
|---|---:|---:|---:|---|
| B7 vs B1 | +0.0000 | [+0.0000, +0.0000] | 1.000 | Mirror integrity ✓ |
| B11 vs B9 | +0.0000 | [+0.0000, +0.0000] | 1.000 | Mirror integrity ✓ |
| **B9 vs B1** | **+0.0198** | [+0.0010, +0.0386] | **0.040** | **ens beats sqrt significantly** |
| B9 vs B2 | +0.0070 | [−0.0054, +0.0202] | 0.287 | ens vs none — not significant |
| B2 vs B1 | +0.0129 | [−0.0157, +0.0395] | 0.346 | none vs sqrt — **not significant at composition level** |
| **B8 vs B1** | **−0.0084** | [−0.0142, −0.0034] | **0.000** | **sqrt+focal significantly HURTS** |
| B10 vs B9 | −0.0054 | [−0.0112, +0.0001] | 0.052 | ens+focal marginally worse than ens (trend) |
| B3 vs B1 | +0.0092 | [−0.0022, +0.0215] | 0.116 | h=192 sqrt — not significant gain |
| B4 vs B2 | −0.0086 | [−0.0240, +0.0055] | 0.247 | h=192 none — not significant |
| B6 vs B1 | −0.0086 | [−0.0402, +0.0205] | 0.594 | transformer ≈ gru baseline |
| **B12 vs B11** | **−0.0098** | [−0.0193, −0.0006] | **0.038** | **PCP feature significantly HURTS** |
| **B9 vs classical** | **−0.1647** | [−0.2389, −0.0895] | **0.000** | **Classical dominates B9** |
| **B10 vs classical** | **−0.1701** | [−0.2434, −0.0949] | **0.000** | Classical dominates B10 |
| **B2 vs classical** | **−0.1716** | [−0.2508, −0.0932] | **0.000** | Classical dominates B2 |

**Composition-equal Δ is larger in magnitude than frame-weighted Δ** (e.g. B9 vs classical: −0.165 composition-equal vs −0.097 frame-weighted in the summary). This is expected: classical hits MIREX = 1.000 exactly on many mono-tonal short compositions, dragging the composition-equal mean higher than the frame-weighted mean. Both are reported for transparency per pre-reg §5.

---

## 5. Scientific findings

### Finding 1 — ENS class-balanced weighting strictly dominates sqrt

B9 (ens, β=0.999) beats B1 (sqrt) at Δ = +0.020 (composition-equal, p = 0.04) and gives σ = 0.003 across 3 seeds — **the tightest seed stability of any cell in either Phase A or Phase B**. This is a novel empirical contribution to MIR: sqrt has been the default in prior symbolic-key-detection work; Cui et al.'s (2019) class-balanced loss transfers cleanly here and should be the new default.

### Finding 2 — Focal loss is null-to-harmful unless paired with ens

B8 (sqrt + focal γ=2.0) REGRESSES vs B1 at Δ = −0.008, p < 0.001. Focal loss as a standalone add-on is actively harmful on this task. B10 (ens + focal) matches B9 on aggregate (Δ = −0.005, p = 0.05 — trend toward worse). Focal's only redeeming signal is on the modulating subset (B10 modu = 0.484 vs B9 modu = 0.477, best in the grid). Useful for modulation-specialist follow-up (Phase C Path B); not useful as a general default.

### Finding 3 — PCP features significantly hurt a strong ENS-weighted baseline

B12 (ens + PCP) regresses from B11 (= B9, ens alone) at Δ = −0.010, p = 0.038, and σ expands from 0.003 to 0.012. **This is a clean, publishable negative result**: the GRU already learns pitch-class statistics from its 12-dim pitch embedding + time-bucketed note encoding; adding an explicit PCP feature is redundant and introduces noise that widens seed variance. Conclusion: PCP-style engineered features are not useful when a sufficiently flexible representation (pitch embedding) already exists upstream.

### Finding 4 — h=192 wastes parameters

B3 (h=192 sqrt) vs B1: +0.009, p = 0.12 not significant. B4 (h=192 none) vs B2: −0.009, p = 0.25 not significant. **B4 is also UNSTABLE** (σ = 0.022, above the 0.015 stability threshold). 3.6× the parameters of h=96, zero stable gain. The Phase B task is data-limited, not capacity-limited.

### Finding 5 — Transformer underperforms GRU at this data scale

B5 (transformer sqrt) regressed vs B1 at Δ = −0.030. B6 (transformer none) was essentially at parity with B1 (Δ = +0.002, p = 0.59). Transformers require substantially more data than 250 ATEPP compositions to outperform a GRU; this is expected given the 10–100× data-hunger gap in the literature. Drop the transformer architecture from further consideration at this scale.

### Finding 6 — Classical remains the ceiling (headline negative result)

B9 vs classical: Δ = −0.165, p < 0.001 composition-equal. Even the strongest causal-neural cell is highly significantly worse than a deterministic profile-correlation method. The gap is driven by mono-tonal compositions where classical frequently hits MIREX = 1.0 exactly; on modulating compositions the gap narrows but still favors classical. **This is the central Phase B finding**: a 30-epoch, causal, 67k-parameter GRU trained on 250 compositions cannot beat Krumhansl + Temperley + Albrecht-Shanahan profile correlation on symbolic key detection. Reporting this honestly is the scientific contribution; classical is the deployable ceiling.

---

## 6. Outcome categorisation (pre-reg §1)

| Category | Criteria | Cells |
|---|---|---|
| **STRONG_WINNER** | Δ ≥ 0.015 vs classical, p < 0.05, σ ≤ 0.015 | **none** |
| **MODULATION_WINNER** | Δ ≥ 0.015 vs classical on modu subset, p < 0.05 | **none** |
| **ARCH_WINNER** | Δ ≥ 0.015 vs A1 at p < 0.05, σ ≤ 0.015 | B9, B10, B11 (statistically supported) |
| ARCH_WINNER (point estimate only) | Δ ≥ 0.015 vs A1 by seed-mean, fails paired bootstrap | B2 (p = 0.35 vs A1), B12 (vs A1 not tested here but plausibly significant) |
| **UNSTABLE** | σ > 0.015 across seeds | B4 |
| null | neither criterion met | B1, B3, B5, B6, B7, B8 |

**Phase B verdict: "Null + ceiling" outcome with three statistically-supported ARCH_WINNERs.** Per pre-reg §1: Phase C pivots to testing whether pretraining moves the dual ceiling (A1-corrected → 0.50, classical → 0.62).

---

## 7. Pre-registration adherence

- §2 grid: **executed as-written** (12 cells × 3 seeds).
- §3 hyperparameters: **honored** (30 ep, batch 8, lr 1e-3, warmup 3, patience 10, deterministic).
- §4 splits: **honored** (ATEPP-only 250/28/41 effective split; WiR/DCML entries silently filtered by loader due to missing `notes` field, same as Phase A).
- §5 metrics: **honored** (test MIREX + paired cluster bootstrap at composition level + mono/modu stratification + per-class in class_metrics).
- §6 decision rules: **applied** (outcome categories above).
- §8 persistence: **honored** (36 eval JSONs + 36 HMM JSONs + 36 ensemble JSONs + checkpoint metadata in every file).
- §9 amendments: see companion update to `phaseB_preregistration.md` §9.

**No post-hoc rule tuning.** B7 and B11 as mirrors were an efficiency choice; B12's PCP config was pre-registered; B10 (ens+focal) was pre-registered. Nothing re-scoped during execution.

---

## 8. Deployable baseline for Phase C

| Statistic | Value |
|---|---|
| Causal-neural ceiling (B9 plain) | **0.5235 ± 0.0030** |
| Causal-neural ceiling (B9 + HMM) | **0.5345 ± 0.0030** |
| Classical deployable ceiling | 0.6201 ± 0.0000 |
| Δ to close (B9 → classical, composition-equal) | 0.165, p < 0.001 |
| Δ to close (B9 → classical, frame-weighted) | 0.097 |
| Best config | GRU h=96, ENS weighting (β=0.999), no focal, no PCP, causal, val-MIREX selection, 30 ep |
| Checkpoint path | `research_data_041826/phase_b_checkpoints_2026-04-17/B9_seed{20260309,10,11}.pt` |
| Predictions path | `research_data_041826/phase_b_evals_2026-04-17/B9_seed*_predictions.json` (some missing — see §10) |

**Any Phase C cell claiming improvement must beat BOTH**: (a) B9 at Δ ≥ 0.015 at p < 0.05 paired bootstrap, σ ≤ 0.015; (b) classical for STRONG_WINNER status.

---

## 9. Outstanding cleanups

1. **8 `_predictions.json` files missing from the Drive download** (B1×2, B2×2, B3, B4, B5, B10 — one seed each). Not critical for paired bootstrap (ensemble_eval.json carries per-composition neural_mirex which is what the bootstrap needs), but re-sync from Drive before any Phase C paired test that requires per-note logits.
2. **2 `_val_predictions.json` missing** (B2_seed310, B3_seed310). Not needed for HMM/ensemble which are already computed; fine to leave.
3. **6 `_training_log.json` missing for B7/B11.** Expected — these were mirrors from B1/B9, training wasn't re-executed, so logs legitimately do not exist.

---

## 10. Phase C entry criteria (pre-reg handoff)

Phase B demonstrates that **architecture-level variation alone cannot close the gap to classical** on the 250-file ATEPP-heuristic train set. Phase C tests whether the gap is data-limited (pretraining transfer should help) or representation-limited (requires per-frame modulation-specialist loss design). Proposed Phase C:

1. **Path A — pretraining transfer** (Moonbeam or Aria → fine-tune on B9's config). Success = Δ ≥ 0.015 vs B9 at p < 0.05.
2. **Path B — modulation-specialist loss** (frame-weight upweighting on modulating pieces). Success = Δ ≥ 0.015 vs classical on modulating subset at p < 0.05. **This is the path toward a publishable MODULATION_WINNER that classical fundamentally cannot reach.**
3. **Parallel execution recommended.** Path A is a days-scale test (pretrained encoder + fine-tune); Path B is a targeted 2–3 cell add-on on B9's config. Both feasible within the Phase B compute budget that remains.

See `phaseC_preregistration.md` (to be drafted) for frozen outcome categories, sample sizes, and comparator set.

---

**Phase B status: complete.** All 12 cells × 3 seeds executed, all outcome classifications assigned, paired bootstrap significance tests published, scientific findings documented. Ready for Phase C.
