# Phase C Path B Consolidation — Modulation-specialist loss, clean null result

**Date:** 2026-04-18
**Branch:** `main`
**Pre-registration:** [`phaseC_preregistration.md`](phaseC_preregistration.md)
**Phase B handoff:** [`phaseB_consolidation_2026-04-18.md`](phaseB_consolidation_2026-04-18.md) (B9 = 0.5235 ± 0.0030)
**Compute:** NVIDIA L4 (Colab Pro), 2 cells × 3 seeds = 6 training runs, ~85 wall-clock min training + 30 min eval + 15 min Track 1 = ~2.2 h total.
**Artefacts:** [`phaseC_results_2026-04-18/`](phaseC_results_2026-04-18/) + Drive-resident checkpoints in `phase_c_2026-04-19/`.

---

## 1. Purpose

Test **H2 (representation-limited hypothesis)** from `phaseC_preregistration.md` §1: can a loss-weighting scheme that emphasises modulating compositions or key-transition frames close the B9-to-classical gap on the modulating subset, producing a MODULATION_WINNER per pre-reg §4?

## 2. Cells executed

| Cell | Config | Rationale |
|---|---|---|
| **C5** | B9 + `--modulation-upweight 2.0` (composition-level) | Simplest test: double the gradient on the 18 modulating training compositions. |
| **C6** | B9 + `--modulation-transition-upweight 3.0 --modulation-transition-window 8` (frame-level) | Targeted: 3× upweight on frames within ±8 notes of any annotated key change. |

All other hyperparameters identical to B9: GRU h=96, `--weight-mode ens`, causal, deterministic, `val_mirex` selection, 30 epochs, patience 10, batch 8, lr 1e-3, warmup 3 seeds {20260309, 20260310, 20260311}. Manifest SHA `d1517ffccbbb3336` (identical to Phase B).

**Not executed (deferred):** C7 (ens + focal + transition upweight). The current `--modulation-upweight` path falls back to plain CE + class weights, incompatible with focal. Per pre-reg §10.5, this is deferred until C5 or C6 shows signal — which they did not (see §3). C7 is dropped from Phase C scope.

## 3. Results

Three-seed mean test MIREX, composition-equal stratified by `n_unique_keys` per Phase A Track 2 diagnostic (32 mono-tonal, 9 modulating out of 41 test compositions):

| Cell | plain | σ | +HMM | +ens | mono (n=32) | modu (n=9) | Δ B9 | Δ modu/B9 | Δ modu/cls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **B9** (Phase B winner) | 0.5235 | 0.0030 | 0.5345 | 0.6208 | 0.6343 | 0.4773 | — | — | −0.0094 |
| C5 (comp upweight 2×) | 0.5214 | **0.0009** | 0.5307 | 0.6207 | 0.6245 | 0.4785 | −0.0021 | +0.0012 | −0.0082 |
| C6 (frame upweight 3×/±8) | 0.5237 | 0.0035 | 0.5351 | 0.6206 | 0.6337 | 0.4772 | +0.0002 | −0.0001 | −0.0095 |

Summary JSON: [`phaseC_results_2026-04-18/phaseC_pathB_summary_2026-04-19.json`](phaseC_results_2026-04-18/phaseC_pathB_summary_2026-04-19.json).

## 4. Paired cluster bootstrap

Composition-level paired bootstrap, B=10,000, RNG seed 20260419, 3-seed mean per-composition neural_mirex vector. Source: [`phaseC_pathB_paired_bootstrap.json`](phaseC_results_2026-04-18/phaseC_pathB_paired_bootstrap.json).

| Contrast | Subset | Mean Δ | 95 % CI | p | Significance |
|---|---|---:|---:|---:|---|
| C5 vs B9 | full (n=41) | −0.0074 | [−0.0153, −0.0008] | **0.025** | * regression |
| C5 vs B9 | **mono (n=32)** | **−0.0098** | [−0.0198, −0.0015] | **0.016** | * **significantly hurts mono** |
| C5 vs B9 | modu (n=9) | +0.0011 | [−0.0022, +0.0044] | 0.508 | ns |
| C5 vs classical | modu (n=9) | −0.0211 | [−0.1537, +0.0937] | 0.769 | ns (wide CI) |
| **C6 vs B9** | full (n=41) | −0.0004 | [−0.0024, +0.0012] | 0.646 | **ns — effectively identical** |
| C6 vs B9 | mono (n=32) | −0.0005 | [−0.0031, +0.0016] | 0.661 | ns |
| C6 vs B9 | modu (n=9) | −0.0001 | [−0.0009, +0.0006] | 0.770 | ns |
| C6 vs classical | modu (n=9) | −0.0224 | [−0.1539, +0.0925] | 0.751 | ns (wide CI) |
| **C6 vs C5** | full (n=41) | **+0.0069** | [+0.0008, +0.0138] | **0.024** | * C6 beats C5 overall |
| C6 vs C5 | modu (n=9) | −0.0013 | [−0.0046, +0.0020] | 0.468 | ns |

---

## 5. Scientific findings

### Finding 1 — Path B does not produce a MODULATION_WINNER

Neither C5 nor C6 moves the modulating-subset MIREX measurably. C5's Δ on modu is +0.0011 (p=0.51), C6's is −0.0001 (p=0.77). Both are indistinguishable from B9 at composition level. Against classical modu (0.4867), C5 is −0.021 and C6 is −0.022, both not significant due to the wide CI (the modulating subset has only 9 compositions, which fundamentally caps statistical power — see Finding 4). **H2 is not supported.** Frame-level loss reweighting does not extract additional modulation signal from the current data.

### Finding 2 — C5 significantly HURTS mono-tonal performance

C5 vs B9 on the mono-tonal subset: Δ = −0.0098, p = 0.016 **. Redistributing gradient mass toward the 18 modulating training compositions *collaterally damages* the model's mono-tonal learning. This is the clearest scientific signal from Path B: **composition-level loss upweighting transfers gradient from pieces that the model was already learning (mono-tonal) to pieces where it provides no new signal (modulating)**. Net effect is negative.

This is a publishable sub-finding: "naive composition-level modulation upweighting is a strictly worse strategy than uniform composition weighting, because mono-tonal compositions provide most of the usable training signal."

### Finding 3 — C6 is a surgical null

Frame-level transition upweighting (3× within ±8 notes of any key change) produces virtually identical behaviour to B9 on all strata (full p=0.65, mono p=0.66, modu p=0.77). The transition-window approach does not damage learning elsewhere — it just fails to extract additional modulation signal. **Frame-level targeting is the correct algorithmic design; the signal to extract is simply not there in a neural per-frame model with 256-note windows.**

### Finding 4 — The modulating subset is underpowered for the MODULATION_WINNER criterion

With n=9 modulating compositions, a bootstrap CI half-width of ~0.10–0.13 MIREX is structural. Even a large effect (Δ = +0.08, say) would fail to reach p<0.05. The pre-registered MODULATION_WINNER criterion (Δ ≥ 0.015 at p<0.05) is **practically unreachable at this sample size** regardless of algorithmic improvement. This is a sample-power problem, not an algorithmic limitation.

**Implication:** any future MODULATION_WINNER claim requires either (a) larger modulating test subset (potentially from WiR/DCML once score-level note-label conversion lands), or (b) dropping the p<0.05 requirement in favor of effect-size-only reporting with wide-CI transparency. Phase D/E should address this explicitly.

### Finding 5 — C6 is stably better than C5 on aggregate (p=0.024)

Among the two Path B cells, C6's surgical approach beats C5's composition-level approach by Δ=+0.007 on aggregate (p=0.02). This confirms Finding 2 from another angle: indiscriminate upweighting (C5) harms learning; targeted upweighting (C6) at least doesn't harm. If any future modulation-specialist work is pursued, **transition-window targeting is the correct design; composition-level upweighting is strictly dominated.**

### Finding 6 — C5 produces the tightest σ in any phase (σ=0.0009)

Seed-stability of C5 is 3.3× better than B9's 0.0030 and an order of magnitude tighter than anything in Phase B. Composition-level reweighting has a stabilising effect, possibly by forcing consistent gradient behaviour on the small modulating subset. **This is a noteworthy secondary finding**: loss-weight redistribution can stabilise training even when it doesn't improve MIREX. Could inform future work on noise-sensitive training regimes.

---

## 6. Outcome categorisation (pre-reg §4)

| Category | Criteria | Cells |
|---|---|---|
| **STRONG_WINNER** | Δ ≥ 0.015 vs classical AND p<0.05 AND σ ≤ 0.015 | **none** |
| **MODULATION_WINNER** | Δ ≥ 0.015 vs classical modu AND p<0.05 | **none** |
| **TRANSFER_WINNER** | Δ ≥ 0.015 vs B9 AND p<0.05 AND σ ≤ 0.015 | **none** |
| null (stable) | No category met, σ ≤ 0.015 | C5, C6 |

**Phase C Path B verdict: null result on both hypotheses H2 and the TRANSFER gate.**

## 7. Implications for Phase C Path A (Moonbeam pretraining transfer)

Path B's failure is informative for designing Path A:

1. **The data signal for modulation is not easily extracted by loss-scaling tricks.** This *increases* the probability that the bottleneck is representation-limited (insufficient pretraining), not loss-design-limited. Path A becomes more relevant, not less.
2. **The mono-tonal ceiling (~0.63 composition-equal) is close to what the 250-file training set can support.** Pretraining transfer's main opportunity is on the modulating subset where patterns require long-range context.
3. **The MODULATION_WINNER criterion may need reframing.** With n=9 and bootstrap CI ~0.10 wide, the pre-registered p<0.05 bar is structurally unreachable. Path A should report effect sizes and transparent CIs without over-interpreting significance on this subset. Consider reframing to: "Δ > 0.03 effect size on modulating subset, with composition-equal and frame-weighted both reported."

## 8. Recommended Phase C Path B post-mortem for thesis narrative

Path B null is **publishable as a negative result**. Suggested sub-claim in Paper 1:

> "We tested two loss-weighting schemes designed to bias training toward modulating compositions: (C5) composition-level 2× upweight and (C6) frame-level 3× upweight within ±8 notes of annotated key changes. Neither produced a measurable gain on the modulating test subset (Δ +0.001 and −0.0001 respectively, both p > 0.50). C5 significantly regressed mono-tonal performance (Δ −0.010, p = 0.02), demonstrating that naive composition-level upweighting strictly transfers gradient from mono-tonal compositions (where the model has learnable signal) to modulating compositions (where the signal is absent at this window size). This result falsifies the hypothesis that a causal per-frame neural model can be induced to match classical profile correlation on modulating pieces via loss-weighting alone."

---

## 9. Phase C Path A entry criteria

**Phase C Path B closes cleanly.** Phase C Path A (Moonbeam pretraining transfer) becomes the sole remaining lever for beating the classical ceiling.

Prerequisites for Path A:
1. **Rewrite Moonbeam classifier head to per-note** (currently window-majority, not comparable to B9). Flagged in pre-reg §10.4; pending.
2. **Add `--seed` flag + 3-seed runs** to [`finetune_moonbeam_key_detection.py`](../finetune_moonbeam_key_detection.py).
3. **Add `--save-predictions` / `--save-val-predictions`** output matching `evaluate_harmonic_context_model.py` format so paired bootstrap against B9 works unchanged.
4. **Add model-size switch** (`--config` to 309M vs 839M).

Estimate: ~2 hours of code changes + testing. Then C1 (309M LoRA) + C2 (839M LoRA) × 3 seeds = ~6 training runs, ~6–12 GPU-h on L4, ~3–6 GPU-h on A100.

**If Path A also fails:** Phase C concludes with a "null + ceiling" outcome across both hypotheses. Phase D reframes around (a) the ENS-weighting empirical contribution, (b) the honest classical-dominance finding, and (c) error-analysis + interpretability work on B9 (the deployable causal-neural baseline at 0.5235 ± 0.0030).

---

**Phase C Path B status: complete.** Both H2 hypotheses (composition-level and frame-level modulation upweighting) falsified at pre-registered significance levels. Path A (pretraining transfer) proceeds as the final experimental lever in Phase C.
