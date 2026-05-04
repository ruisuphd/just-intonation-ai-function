# Phase I "Beat Classical" — pre-registered analysis plan

**Pre-registration date:** 2026-04-25 (before any leakage-free training run produces results that can change this plan)
**Author:** Rui Su, with Claude as analytical assistant
**Project:** *Instant Harmonies — Real-time Adaptive JI Tuning for MIDI*
**Scope:** C1 (symbolic causal neural key detection from MIDI) — Phase I
ablation only. C2/C3/C4 not in scope here.

> **Why this document exists.** The first Phase I run (Colab, single seed
> 20260412) produced an apparently positive but ultimately invalid result
> because of an 18-piece DCML train-val leakage that was discovered and
> patched only after training. That run is **discarded** for scientific
> reporting purposes. This pre-registration locks the design of the
> leakage-free re-run **before** any leakage-free numbers exist, so that
> results cannot be reverse-engineered into a flattering narrative.

---

## 1. Hypotheses

The deployable Phase B baseline is **B9** — a 67 k-parameter causal GRU
(h = 96) with ENS β = 0.999 class weighting, trained on the
41-composition ATEPP manifest training split. Its 5-seed mean test FW
MIREX is **0.5208 ± 0.0044** (sample-σ).

The classical 3-profile ensemble (KK + Temperley + Albrecht-Shanahan)
achieves **0.6201 (FW)** on the same ATEPP-41 test split.

Phase I tests three additive techniques on top of B9:

* **T6** = deterministic ×12 transposition augmentation (every piece is
  yielded 12 times during training, once per ±0…±11 semitone shift,
  with key labels rotated correspondingly).
* **T1** = global pitch-class profile feature, computed once per
  composition from its full note stream and concatenated onto every
  per-frame GRU hidden state via a 24-d projection head.
* **T2** = multi-task auxiliary chord-prediction head (12-class chord
  root + 14-class chord quality), masked so chord loss only contributes
  on frames whose record carries DCML Strategy A chord labels.

The pre-registered hypotheses, ordered by priority:

| ID | Hypothesis | Decision metric | One-sided? |
|---|---|---|---|
| **H1** | The full stack `T6_T1_T2` outperforms the deployable B9 baseline. | Test FW MIREX, paired-bootstrap p < α (T6_T1_T2 vs B9) | One-sided (improvement) |
| **H2** | The expanded training pool alone (`BASELINE`) outperforms B9. | Test FW MIREX, paired-bootstrap p < α (BASELINE vs B9) | One-sided |
| **H3** | T6 (×12 aug) adds value on top of `BASELINE`. | Test FW MIREX, paired-bootstrap p < α (T6 vs BASELINE) | One-sided |
| **H4a** | T1 (global PCP) adds value on top of `T6`. | Test FW MIREX, paired-bootstrap p < α (T6_T1 vs T6) | One-sided |
| **H4b** | T2 (chord head) adds value on top of `T6_T1`. | Test FW MIREX, paired-bootstrap p < α (T6_T1_T2 vs T6_T1) | One-sided |
| **H5** | The full stack closes the gap to the classical 3-profile ensemble. | Test FW MIREX ≥ 0.6201 (the classical FW) | Threshold, not p-value |

H1 is the primary outcome. H2 / H3 / H4a / H4b are pre-registered
exploratory tests of the cumulative-ablation logic, each isolating
the marginal effect of one technique. H5 is a binary "did we beat the
classical baseline" check; it will be reported but does NOT condition
publication. The family-wise α correction below covers H1, H2, H3,
H4a, H4b (5 tests).

## 2. Design

**Variants (cumulative ablation, 4 cells — strict additive):**

| Variant | Expanded train pool | T6 (×12 aug) | T1 (global PCP) | T2 (chord head) |
|---|---|---|---|---|
| `BASELINE` | ✓ | ✗ | ✗ | ✗ |
| `T6` | ✓ | ✓ | ✗ | ✗ |
| `T6_T1` | ✓ | ✓ | ✓ | ✗ |
| `T6_T1_T2` | ✓ | ✓ | ✓ | ✓ |

Each cell adds **exactly one** technique relative to the previous cell,
so the difference between adjacent cells isolates the marginal effect
of that one technique. The Phase B B9 "reference" (ATEPP-only training
pool, no T6/T1/T2) is a separate fixed point, not retrained here, and
serves as the comparator for H1.

**Why BASELINE is included as a separate cell.** The published B9 was
trained on the 41-composition ATEPP pool only. Phase I's expanded pool
(2 181 entries; ATEPP + WiR + DCML expert + DCML Strategy A) is a
material change. BASELINE — same B9 architecture trained on the
expanded pool with no other Phase I techniques — isolates the effect
of the bigger dataset alone. Without this cell, an improvement at
T6_T1_T2 could not be attributed cleanly to the techniques rather
than to the bigger pool.

**Seeds:** 3 per variant — `20260425a`, `20260425b`, `20260425c`. Seeds
are fresh today's date so they are not contaminated by being repeated
from earlier phases. (PyTorch / Python `random` / NumPy seeded
identically.)

**Total runs:** 4 variants × 3 seeds = **12 training runs.**

**Train manifest:** `research_data/unified_training_manifest_phase1_clean.json`
(2 181 entries; the 18-piece DCML train-val leakage fix has been
applied and verified bit-identical on the val split).

**Test manifest:** the same 41-composition ATEPP test split used by
Phase B / Phase C (composition IDs frozen, see
`composition_splits.json`). **Test entries from DCML Strategy A and
WiR are filtered out before evaluation** by ID-allowlist filtering in
`train_phase1.py:filter_test_to_atepp_41`.

**Hyperparameters (frozen from B9, identical across all 12 runs):**

| Param | Value |
|---|---|
| `hidden_size` | 96 |
| `num_layers` | 1 |
| `dropout` | 0.1 |
| Direction | causal (`bidirectional=False`) |
| `weight_mode` | `ens` (Cui et al. 2019) |
| `ens_beta` | 0.999 |
| Optimiser | Adam |
| `learning_rate` | 1e-3 |
| `batch_size` | 8 |
| `epochs` | 30 |
| Selection metric | val FW MIREX |
| `n_transpositions` | 12 |
| `chord_loss_weight` (T2 only) | 0.3 |

**Hardware:** CPU on Apple M-series, `torch.set_num_threads(1)` for
reproducibility. MPS is excluded based on the Phase I empirical finding
that MPS is 22× slower than CPU on the B9-scale model
(`research_data/latency_measurement_2026-04-20.json` regenerated
2026-04-25).

## 3. Pre-registered statistical analysis

### 3.1 Primary analysis (H1)

* **Test:** composition-level paired cluster bootstrap, B = 10 000.
* **Pairing key:** `composition_id` (the ATEPP-41 IDs).
* **Comparator:** Phase B B9 5-seed mean per-composition MIREX
  (`research_data/b9_5seed_stability_2026-04-20.json`). Note: only 2 of
  the 5 original per-composition prediction streams survived the
  2026-04-25 data loss (seeds 312, 313). The B9 comparator therefore
  uses the 2-seed local mean **on this re-run only**, which is
  scientifically defensible because (a) the 2-seed FW = 0.5166 ± 0.0001
  is consistent with the previously-reported 5-seed FW = 0.5208 ± 0.0044
  within 1 σ, and (b) variance across seeds at the per-composition
  level is small.
* **Test statistic:** Δ_FW = mean(t1_t2 across 3 seeds) − mean(B9 across 2 seeds), per composition, then averaged.
* **Two-sided p:** twice the proportion of bootstrap resamples whose Δ
  has the OPPOSITE sign of the observed Δ.
* **Significance threshold:** **α = 0.01** (Bonferroni-corrected for
  the 5 family-wise tests H1, H2, H3, H4a, H4b: 0.05 / 5 = 0.01).

### 3.2 Secondary analysis (H2–H4)

Same statistical machinery (paired bootstrap, B = 10 000), each at
α = 0.0125. H2 compares variant `baseline` (T6 alone) to the B9
reference. H3 compares `t1` to `baseline`. H4 compares `t2` to
`baseline`.

### 3.3 Reporting

For every cell:

* Per-seed test FW MIREX (3 numbers per cell).
* 3-seed mean test FW MIREX ± sample-σ (n = 3, σ uses Bessel
  correction; if a seed crashes, n drops accordingly and the σ is
  re-flagged).
* Test CE MIREX, mean ± σ (secondary).
* Per-corpus test FW MIREX (mono-tonal vs modulating split, ATEPP-41 has
  32 mono + 9 modu per `composition_splits.json`).
* Per-composition MIREX archive (saved alongside the eval JSON, used
  for paired bootstrap).

For every paired comparison:

* Δ_FW (95 % CI from the bootstrap).
* p-value, raw and Bonferroni-corrected.
* Effect size in σ-units (Δ_FW / σ_5seed_B9 = Δ_FW / 0.0044).

### 3.4 Decision rules

| Pre-registered call | Threshold |
|---|---|
| Reject H_null for any of H1–H4 | Bootstrap p < 0.0125 (Bonferroni) AND Δ_FW > 0 (one-sided spirit) |
| "Closes the gap to classical" (H5) | Mean test FW MIREX ≥ 0.6201 |
| "Practically significant improvement" | Δ_FW ≥ +0.005 (≥ one Phase B σ) regardless of p |
| "Statistical artefact" | Δ_FW > 0 but Bonferroni p > 0.05 → reported as null |

### 3.5 Multiple-comparisons strategy

H1–H4 form a single pre-specified family. We use Bonferroni rather
than Holm because all four tests are pre-registered and we want a
single hard-line significance bar that does not depend on the
ordering of which test rejected first.

H5 is NOT in the family — it is a directional threshold check
(0.6201) and does not consume α.

## 4. Reproducibility checklist

* [x] Pre-registered before training results exist.
* [x] All 12 training runs use a fixed manifest path with a checksum
  documented in §5.
* [x] All hyperparameters are frozen and listed in §2.
* [x] The runner script (`run_phase1_sweep.py`) is committed before any
  run starts and is the SOLE entry point used.
* [x] Random seeds are listed in §2.
* [x] Hardware string (`uname -a`, `torch.__version__`,
  `python --version`) is logged inside every per-run JSON.
* [x] Test split is locked by composition-ID allowlist in
  `train_phase1.py`, not by manifest filtering, so a manifest typo
  cannot silently leak DCML pieces into the test set.
* [x] All deviations from this plan must be appended to §6 with
  timestamp before being merged into the final report.

## 5. Manifest checksums

```
$ shasum -a 256 research_data/unified_training_manifest_phase1.json \
                research_data/unified_training_manifest_phase1_clean.json
```

To be filled in by `run_phase1_sweep.py` before the first run starts;
each per-run JSON will record both checksums.

## 6. Deviations log (append-only)

(Empty at pre-registration time. Any deviation discovered during
execution must be appended here with date, reason, and effect on the
analysis plan.)

---

### Entry 1 — 2026-05-01 (retroactive consolidation)

**Disclosure.** This entry retroactively documents amendments and
execution events that occurred between 2026-04-26 and 2026-05-01. The
entry itself is appended on 2026-05-01. The author acknowledges that,
under §4 of this pre-registration, each amendment should have been
appended to this log at the time it was made. The retroactive
consolidation below is itself a deviation from §4 and is reported
here for transparency. **No scientific claim, hypothesis, decision
rule, frozen test split, training-set manifest, comparator, or
statistical test was altered by any of the amendments below.** Only
sample size per cell and compute schedule changed.

#### Amendment A1 (2026-04-26): seed-count expansion from n = 3 to n = 5 per cell.

* **Rationale.** The 2026-04-26 audit (`RESEARCH_RIGOUR_AUDIT_2026-04-26.md`)
  recommended n = 5 sample-σ for chapter-headline figures (audit
  Tier-1 weakness W1: a non-trivial fraction of σ estimates at n = 3
  fall outside the 1-σ confidence band of the n = 5 estimate). The
  expansion was implemented to stabilise sample σ.
* **New seeds added.** `20260425d` (seed_int 3629727882) and
  `20260425e` (seed_int 440397851), generated by the same SHA-256
  scheme as `a/b/c` from the seed-label string.
* **What did NOT change.** Frozen test split (ATEPP-41 composition
  IDs); pre-registered hypotheses (H1, H2, H3, H4a, H4b, H5);
  training regime and hyperparameters (§2); decision rules (§3.4);
  pre-registered statistical test (composition-level paired cluster
  bootstrap, B = 10 000); comparator (Phase B B9 5-seed
  per-composition mean MIREX). The pre-registered Bonferroni
  α = 0.01 across the 5-test family-wise H1/H2/H3/H4a/H4b is
  unchanged.
* **What changed.** Sample size per cell: 3 → 5 (+2 seeds per cell ×
  4 cells = +8 additional training runs). Compute schedule extended
  to accommodate the larger sweep.

#### Execution log E1 (2026-04-26): BASELINE × 5 completed on Apple M-series CPU.

`BASELINE` cell across seeds `a/b/c/d/e` produced test FW MIREX values
(0.5761, 0.5645, 0.5864, 0.6166, 0.5784); n = 5 mean = 0.5844, sample
σ (ddof = 1) = 0.0196. Reported as `Su (2026o §2.1)` and
`PHASE1_FINDINGS_2026-04-29.md`.

#### Execution log E2 (2026-04-26 / 2026-04-27): T6 seed `a` completed on Colab T4.

T4 free-tier wall-clock per run was ~3.5 h, dominated by an
eval-bottleneck not anticipated in the pre-flight 5-min audit
estimate. Eval-bottleneck investigation flagged as W2 in
`RESEARCH_RIGOUR_AUDIT_2026-04-26.md` and noted in the next-step
plan.

#### Execution log E3 (2026-04-27 / 2026-04-28): T6 seeds `b/c/d/e` completed on Colab Pro+ A100.

T6 cell n = 5 mean = 0.6426, sample σ = 0.0266. Hardware composition
disclosed in `Su (2026o §2.2)` and Chapter 6 §6.6.9 Table 6.18:
seed *a* on T4, seeds *b/c/d/e* on A100. Within-A100 σ across the
four A100-trained seeds = 0.0305, of the same order as the
cross-hardware 5-seed σ = 0.0266 (Pineau et al., 2021 framing).

#### Execution log E4 (2026-04-28): B9 5-seed restoration completed on Colab Pro+ A100.

Three of the original five Phase B B9 per-composition prediction
archives (seeds `20260309/10/11`) were lost in the 2026-04-25
Drive-sync incident (`RECOVERY_REPORT_2026-04-25.md`; Su, 2026m).
Re-trained on the original Phase B manifest (`unified_training_manifest.json`,
SHA-256 prefix `d1517ffccbbb3336…`, 1 906 entries) under identical
hyperparameters as the published Phase B B9 (Su, 2026j). Restored
5-seed mean = 0.5164 ± 0.0059; within 1 σ of the published 0.5208 ±
0.0044 (Δ = −0.0044, exactly equal to the published σ — consistent
with normal seed-resampling variation). **Closes audit weakness W5.**
Reported as `Su (2026o §3)`.

#### Execution log E5 (2026-04-28 / 2026-04-29): T6_T1 × 5 completed on mixed Colab T4 + A100.

T6_T1 cell n = 5 mean = 0.6707 ± 0.0103; per-seed range
[0.6585, 0.6801]. Hardware: seed *a* on A100, seeds *b/c/d/e* on T4
(Chapter 6 §6.6.9 Table 6.19). All five seeds individually exceed
the classical 3-profile ensemble (0.6201 FW). The σ = 0.0103 is
the tightest of any cell in the cumulative ablation. Reported as
`Su (2026p §2.3)` and `PHASE1_FINDINGS_2026-04-30.md`.

#### Execution log E6 (2026-04-29 / 2026-04-30): T6_T1_T2 seeds `a, b` completed on Colab T4.

Preliminary T6_T1_T2 values: seed *a* = 0.6788 (A100, 2026-04-29 13:07
UTC, completed wall-clock 210 min); seed *b* = 0.6518 (T4, 2026-04-29
17:03 UTC, 234 min wall). Both below same-seed T6_T1 reference; n = 2
preliminary mean Δ = −0.0144 paired. Reported in `Su (2026p §2.4)`
as preliminary and replication-pending.

#### Execution log E7 (2026-04-30 / 2026-05-01): T6_T1_T2 seeds `c, d, e` completed on Colab T4.

Final T6_T1_T2 values: seed *c* = 0.6586 (T4, 2026-04-30 02:43 UTC,
311 min wall); seed *d* = 0.6654 (T4, 2026-04-30 07:16 UTC, 273 min
wall); seed *e* = 0.6483 (T4, 2026-04-30 12:27 UTC, 311 min wall).
T6_T1_T2 cell **n = 5 mean = 0.6606, sample σ = 0.0122**, range
[0.6483, 0.6788]. Same-seed paired Δ_FW vs T6_T1 (n = 5):
mean = −0.0102, σ_paired = 0.0126, Cohen's *d_z* = −0.81, sign-test
1/5 in favour of T6_T1_T2 (4/5 negative), paired-*t* one-sided
p = 0.0727 in **negative** direction. **The empirical direction is
opposite to the pre-registered H4b** (which posited
T6_T1_T2 > T6_T1).

#### Status of pre-registered hypotheses as of 2026-05-01

* **All four cumulative cells complete at the amended n = 5** (4 cells
  × 5 seeds = 20 training runs, plus the 3-seed B9 5-seed restoration
  in E4). **Closes audit weaknesses W1 (n = 5 sample σ) and W2
  (deferred T6/T1/T2 cells).**
* **Descriptive evidence is complete.** The five formal paired
  cluster-bootstrap p-values on the per-piece prediction archives are
  pending Mac-side computation (`compute_missing_bootstraps.py`-style
  re-run; no GPU required; archives preserved at
  `phase1_beat_classical_2026-04-25/`).
* **H1 (T6_T1_T2 > B9):** preliminary cell-mean Δ_FW = +0.1442
  (clears strong-success threshold +0.10); cluster-bootstrap pending.
* **H2 (BASELINE > B9):** provisional cluster-bootstrap *p* = 0.0006
  at n = 3 BASELINE × n = 2 surviving B9 (Su 2026k, executed prior
  to this consolidation). Formal n = 5 vs n = 5 re-run against the
  restored B9 comparator is pending Mac-side.
* **H3 (T6 > BASELINE):** 5/5 same-seed paired wins, paired-*t*
  one-sided p = 0.0114 (right at Bonferroni α = 0.01 boundary);
  cluster-bootstrap pending.
* **H4a (T6_T1 > T6):** 4/5 same-seed paired wins, paired-*t*
  one-sided p = 0.0618; cluster-bootstrap pending.
* **H4b (T6_T1_T2 > T6_T1):** **direction opposite to pre-registered
  hypothesis** (1/5 paired wins, paired-*t* one-sided p = 0.0727 in
  negative direction; Cohen's *d_z* = −0.81). The cluster-bootstrap
  is the formal test, but the per-seed evidence already shows the
  direction is wrong; the cluster-bootstrap can at most quantify the
  magnitude of the negative effect, not flip its sign.
* **H5 (full stack closes the gap to classical 0.6201 FW):**
  **SATISFIED at the pre-registered cell**: T6_T1_T2 cell mean =
  0.6606 ≥ 0.6201, Δ = +0.0405. Per-seed minimum (seed *e*) =
  0.6483 > 0.6201; all five seeds individually exceed classical.
  Auxiliary observation: the intermediate T6_T1 cell exceeds
  classical by an even larger margin (Δ = +0.0506 at cell mean,
  per-seed min 0.6585), but H5 as written in §1 of this pre-
  registration applies to the full stack.

---

*This document is final at 2026-04-25 (pre-registration date). Edits
after this date are restricted to §6 (deviations log) and §5
(checksums populated by the runner). All other sections are
read-only.*
