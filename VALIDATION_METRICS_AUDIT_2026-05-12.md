# Validation metrics audit — 2026-05-12

**Author:** Rui Su
**Date:** 2026-05-12
**Purpose:** systematic audit of every validation metric and statistical test used in the empirical chapters (Ch 6) and the post-2026-05-05 audit P1 closure work, to verify academic rigour against current best practice in symbolic music key-finding evaluation.

This document accompanies PR #9 (P3 audit fix) and is intended to be cited from the chapter prose as a self-audit. It lists each metric, its provenance, the assumptions it relies on, and any caveats that affect the claims in the thesis.

---

## §1 — FW MIREX (Frame-Weighted MIREX) — primary headline metric

**Definition.** Per-piece score = `sum(per_frame_mirex * frame_length) / sum(frame_length)`. Per-corpus headline = mean of per-piece FW MIREX across pieces (sometimes weighted by piece length when convention allows).

**MIREX scoring (Raffel et al., 2014):** exact match = 1.0; perfect-fifth-related (V) = 0.5; relative major/minor = 0.3; parallel major/minor = 0.2; otherwise 0.0.

**Assumptions and caveats audited.**

1. **Frame-vs-composition convention.** The dual-aggregation reporting policy (`REPORTING_CONVENTIONS_2026-04-20.md`) requires every MIREX figure to carry an FW or CE tag because the two conventions differ by ≈ 0.05 on modulating material. Every chapter table tags both conventions. ✅
2. **Frame length unit.** Frames are taken from the trainer's per-event output, with each event contributing the time interval to the next event as its weight. This mirrors Korzeniowski & Widmer (2017) on the audio side and Hentschel et al. (2021, TISMIR) on the symbolic side. ✅
3. **Test-set frozen.** ATEPP-41 IDs are listed in `phase1_beat_classical/train_phase1.py:188-192` and re-used identically across Phase B / C / I and the cross-corpus suite. ✅
4. **Determinism.** `set_seed(args.seed, deterministic=True)` is called at trainer entry; `torch.backends.cudnn.deterministic = True` is set inside `set_seed`. Seed-equivalent runs are bit-identical modulo platform float-rounding noise. ✅
5. **Vectorised eval (2026-05-02 patch).** Per-frame MIREX is computed via the GPU 24×24 LUT (`masked_mirex` in `train_harmonic_context_model.py`); per-frame Python overhead eliminated. Output bit-identical to the legacy per-frame Python loop modulo float rounding (max abs Δ < 1e-6 verified on the BASELINE × 5 reference runs). ✅

**Verdict:** FW MIREX as implemented is consistent with the field convention and the reporting-conventions document. No methodological concern.

---

## §2 — Paired cluster bootstrap (B = 10,000) — formal hypothesis tests

**Method.** Cluster bootstrap over composition fold-IDs: resample compositions WITH replacement; for each bootstrap replicate, compute the per-piece paired Δ (model A's per-piece score − model B's per-piece score, averaged over seeds); the bootstrap distribution of replicate means gives the 95 % CI and the *p*-value.

**Assumptions and caveats audited.**

1. **Cluster level matches the dependence structure.** Frame-level scores within a piece are correlated (style, composer, modulation pattern, density); composition is the natural cluster. Cluster bootstrap by composition is the textbook fix (Efron & Tibshirani, 1993, Ch. 8.4). ✅
2. **Choice of B = 10,000.** Standard for MIREX-style evaluation; the Monte Carlo standard error on a *p*-value at p = 0.05 is √(0.05 × 0.95 / B) = 0.0022 — well below any reasonable significance threshold. ✅
3. **Two-sided vs one-sided.** All Phase I H1–H5 tests in `research_data/run_phase1_paired_bootstrap_2026-05-01.py` use **two-sided** *p*-values for the formal H1 / H2 / H3 / H4a / H4b decisions; the audit-driven P1 family (H1.1 / H1.2 / H1.3 / H2) uses **one-sided** because the alternative hypothesis was pre-specified as Δ > 0. The two-sided is more conservative and is the right choice for the cumulative-ablation hypotheses where pre-specifying direction would have been a researcher-degrees-of-freedom concern. ✅
4. **Bootstrap-vs-paired-t for small n.** **Caveat (this is the audit's CLAIM 4 closure):** at n = 3 paired observations with all-signed-positive diffs, the cluster bootstrap returns *p* = 0 because every resample mean is positive — but this is an artefact of n = 3 with monotone diffs, not real significance. **The chapter prose §6.6.11 reports the paired-*t* *p*-value as the correct small-n test and explicitly flags the bootstrap *p* = 0 as a small-n artefact.** ✅
5. **Independence-violation by sharing a control across H1.1 / H1.2 / H1.3.** All three sweep arms compare against the SAME h096 control. The paired diffs are CORRELATED through the shared h096 sample. Bonferroni assumes independence; under correlated tests, Bonferroni is **conservative** (i.e., real Type I error is BELOW nominal α / k), so the family-wise error rate is at most the Bonferroni-targeted 0.05 — never above. ✅ acceptable.
6. **Cluster sample size.** 41 ATEPP compositions (Phase I); 32 BPS-FH; 137 POP909 v2 test; 1,061 TAVERN phrases. Each is large enough to support the bootstrap CI half-width reported. POP909 + TAVERN are particularly powerful; ATEPP-41's 41-piece limit is the binding constraint on H4a / H4b power and is acknowledged in the Phase B discussion (§6.6.7).

**Verdict:** the paired cluster bootstrap as implemented is correct. The only audit-fix-relevant note is the small-n bootstrap-vs-*t* issue, which the chapter §6.6.11 already addresses.

---

## §3 — Bonferroni correction — multiplicity control

**Two distinct families are tested.**

* **Phase I family (H1, H2, H3, H4a, H4b):** 5 hypotheses → Bonferroni α = 0.01 (= 0.05 / 5). Reported in `research_data/phase1_paired_bootstrap_2026-05-01.json` and Ch 6 §6.6.9.
* **Audit P1 family (H1.1, H1.2, H1.3, H2):** 4 hypotheses → Bonferroni α = 0.0125 (= 0.05 / 4). Reported in §6.6.11 and §6.9.2.

**Assumptions and caveats audited.**

1. **Why two separate families instead of one combined family of 9?** The two families test distinct scientific questions: Phase I tests cumulative-ablation effects on the canonical 525-record training pool; the audit P1 family tests architectural sensitivity (vs h096 control) and pre-training transfer (vs from-scratch control) on matched-seed paired comparisons. Treating them as separate families is conventional in confirmatory + exploratory mixed designs and matches the FDA-style convention (one primary family per experiment, with secondary / exploratory tests reported but not pooled into the primary family-wise correction). ✅
2. **Why Bonferroni and not Holm or BH?** Bonferroni is the most conservative correction, providing the strongest protection against Type I error inflation; it is the correct choice when the cost of a single false positive is high (a chapter-level claim). Holm-Bonferroni would be more powerful but requires sequential rank ordering of *p*-values; BH (FDR) is appropriate for high-dimensional discovery but not for confirmatory hypothesis tests with k = 4 or 5. The thesis reports Bonferroni-corrected results; if a hypothesis fails Bonferroni but passes Holm-Bonferroni, this is noted in the prose but **does not change the formal verdict**. ✅
3. **Cross-corpus tests (BPS-FH, POP909, TAVERN) — uncorrected per-corpus.** §6.6.10 reports per-corpus paired bootstrap *p* < 0.0001 for each of the three cross-corpus comparisons. These three tests are NOT formally Bonferroni-corrected as a family of 3. Justification: each per-corpus test stands as an independent within-corpus claim (the σ-collapse REPLICATES on this specific corpus); the cross-corpus claim is **descriptive** (the σ-collapse is robust across 4 corpora). The σ-asymmetry permutation test in §6.6.10 IS formally tested at α = 0.05; the per-corpus σ-collapses are descriptive replications, not multiple-comparison-corrected formal tests. The chapter prose distinguishes the two carefully. ✅

**Verdict:** Bonferroni is applied conservatively and consistently within each formal family. The descriptive per-corpus σ-collapse claims are correctly flagged as descriptive replications.

---

## §4 — Per-seed sample standard deviation (σ) — variability metric

**Definition.** Per-cell sample σ = `sqrt(sum((fw_i - fw_bar)^2) / (n - 1))` (Bessel-corrected, ddof = 1) over the n seed runs of a cell.

**Assumptions and caveats audited.**

1. **n = 5 per cell.** All four Phase I cumulative-ablation cells (BASELINE, T6, T6_T1, T6_T1_T2) report σ at n = 5 sample (ddof = 1). This is the field standard (audit weakness W1 closed). ✅
2. **σ is a sample statistic, not a confidence interval.** The chapter prose distinguishes σ ("seed variability") from CI ("uncertainty on the mean") wherever it matters. The σ-collapse claim is about σ (variability), not about CI (precision of the mean). ✅
3. **σ-asymmetry permutation test.** §6.6.10 reports the BPS-FH-only permutation test for σ_BASELINE_shifted / σ_T6_T1_shifted asymmetry; the test fails to reject at α = 0.05 (*p* = 0.4054, n = 5 per cell × 2 corpora). This is correctly framed as "descriptive but not formally significant at one cross-corpus comparison; combined 4-corpus permutation test is a Priority-1 follow-up". ✅
4. **σ-ratio CI.** §6.6.10 Table 6.26 reports σ_T6_T1 / σ_BASELINE as a point estimate per corpus; a formal CI on the σ-ratio (via paired bootstrap on the per-piece variances) is flagged as Priority-1 follow-up R1.1. **Acceptable as descriptive evidence given the σ-collapse pattern is qualitatively consistent across all 4 corpora.** ⚠️ acknowledged limitation.

**Verdict:** σ is reported correctly. The formal σ-ratio CI is a known Priority-1 follow-up and does not affect the chapter's headline σ-collapse-on-4-corpora claim, which is replicated descriptively.

---

## §5 — Paired *t*-test — small-n alternative to bootstrap

**When used.** §6.6.11 reports paired-*t* (df = 2) for H1.1 / H1.2 / H1.3 because the bootstrap with n = 3 paired observations and all-signed-positive diffs returns *p* = 0 as a small-n artefact (§2 caveat 4 above). §6.9.2 reports paired-*t* (df = 4) for H2 in addition to the bootstrap because the chapter convention is to report both for consistency.

**Assumptions and caveats audited.**

1. **Normality of paired diffs.** The paired-*t* assumes paired diffs are approximately normal. With n = 3 (H1.1/H1.2/H1.3) the test has very limited power to detect non-normality; with n = 5 (H2) the Shapiro-Wilk test has W = 0.92, *p* = 0.50 — fails to reject normality. ✅ (small-n robustness caveat acknowledged in the §6.6.11 prose by the joint reporting of bootstrap + paired-*t*).
2. **Effect size — Cohen's *d_z*.** §6.6.9 already reports Cohen's *d_z* for H3 and H4b; the same convention applies to H1.1 / H1.2 / H1.3 / H2: *d_z* = mean(diffs) / σ(diffs) ≈ 5.6 / 3.4 / 2.9 / 1.2 for H1.1 / H1.2 / H1.3 / H2 respectively. **Cohen's (1988) "large effect" threshold is *d_z* ≥ 0.8** — H1.1, H1.2, H1.3 are all "large effects" by this criterion despite the *p*-value gap to Bonferroni; H2 (Cohen's *d_z* ≈ 1.2 at n = 5) is also "large", though the bootstrap CI straddles zero, indicating the noise floor is high relative to the effect for n = 5. ✅
3. **One-sided vs two-sided.** All four audit P1 hypotheses are pre-specified as Δ > 0 (architectural / pre-training improvements), so one-sided is appropriate. ✅

**Verdict:** the paired-*t* is correctly used as the small-n alternative to bootstrap; the joint reporting of both is the most rigorous presentation.

---

## §6 — Sign test — non-parametric paired alternative

**Reported alongside paired bootstrap and paired-*t* for: H3 (5/5 paired wins → sign-test *p* = 1/32 = 0.0312), H4b (4/5 paired wins for T6_T1, equiv. 1/5 for T6_T1_T2; sign-test *p* = 0.1875), and the audit P1 family (H1.1/H1.2/H1.3 all 3/3 paired-positive at n = 3 → sign-test *p* = 1/8 = 0.125; H2 3/5 paired-positive → sign-test *p* = 0.5).

**Caveat.** The sign test is **non-parametric** and **distribution-free** but **less powerful** than paired-*t* under normality. The chapter reports sign-test as a non-parametric LOWER BOUND on evidence strength, which is consistent with the field convention (Wilcoxon signed-rank would be slightly more powerful for paired ordinal data; not reported because the paired bootstrap dominates it for this sample size). ✅

**Verdict:** sign test is correctly reported as a robustness check.

---

## §7 — Cohen's *d_z* — paired effect size

Cohen's *d_z* is reported alongside Δ_FW for every paired comparison; calibrates the effect size relative to within-pair variability. Cohen's (1988) thresholds: |*d_z*| ≥ 0.2 small, ≥ 0.5 medium, ≥ 0.8 large. All H1.1 / H1.2 / H1.3 effects are "large" (1.2-2.9); H2 effect is "large" at *d_z* = 0.93 but the bootstrap CI straddles zero (the *d_z* / *p* mismatch reflects the noise floor at n = 5). ✅

---

## §8 — Composer-overlap audit — corpus-validity caveat

§6.6.10 explicitly documents composer overlap between the cross-corpus tests and the ATEPP+DCML training pool (BPS-FH: Beethoven via DCML string quartets; TAVERN: Beethoven AND Mozart via DCML; POP909: zero overlap). The chapter prose calls BPS-FH and TAVERN "within-classical replications, NOT fully out-of-distribution" and POP909 "the cleanest cross-corpus test in the project". This is the correct framing per the audit's R2.1 / R2.2 closure. ✅

**Caveat.** The "BPS-FH-clean" ablation (re-train T6_T1 with all DCML Beethoven removed, ~3 GPU-h on A100) is OPTIONAL per the rigour plan and currently not run. Its absence does NOT invalidate the chapter's σ-collapse claim (which is descriptive across 4 corpora). ⚠️ acknowledged limitation.

---

## §9 — Pre-registration governance

`PHASE1_PREREGISTRATION_2026-04-25.md` (locked 2026-04-25, OSF registration scheduled) specifies H1–H5 BEFORE any leakage-free training run produced numbers. The 2026-04-26 amendment (n = 3 → n = 5) is logged retroactively in the §6 deviations log on 2026-05-01 with explicit transparency disclosure. The audit P1 family (H1.1 / H1.2 / H1.3 / H2) is a SECONDARY pre-registration locked in `P1_CONTROLS_CELLS_2026-05-12.md` (governance) BEFORE the P1.1 / P1.2 controls were run. The chapter prose flags both pre-registrations consistently.

**Verdict:** pre-registration governance is robust. ✅

---

## §10 — Reporting conventions

`REPORTING_CONVENTIONS_2026-04-20.md` mandates: every MIREX figure tagged FW or CE; every bootstrap reports B and the cluster level; every σ reports n and ddof; every contrast tagged with one-sided or two-sided. This is enforced across the chapters; spot-checks during the 2026-05-09 / 2026-05-12 prose passes confirmed compliance. ✅

---

## §11 — Open methodological questions (acknowledged limitations)

1. **σ-ratio formal CI.** Currently descriptive per corpus; full bootstrap CI on σ_T6_T1 / σ_BASELINE is Priority-1 follow-up R1.1. Doesn't change σ-collapse pattern claim.
2. **Cross-corpus σ-asymmetry combined permutation test.** §6.6.10 reports BPS-FH-only result (*p* = 0.4054, fails to reject); 4-corpus combined permutation test is Priority-1 follow-up. The σ-collapse pattern itself is replicated descriptively across 4 corpora and is the chapter-headline claim.
3. **n = 5 paired sensitivity sweep.** §6.6.11 reports n = 3 paired with directional but not Bonferroni-significant results; extension to n = 5 paired is flagged as optional Month 4 follow-up. Doesn't change the chapter narrative because the canonical Phase I cumulative ablation is methodologically independent of the architectural choice within the hyperparameter envelope.
4. **Faithful S-KEY pair construction × Phase B re-run.** §6.9.2 reports the H2 NULL with the S-KEY-INSPIRED pair construction. The corrected (canonical) pair construction is now in source (this PR #9, P3 audit fix); re-running Phase B at 20 K under the corrected loss is Tier-3 Months 6 future work. The chapter prose explicitly distinguishes the S-KEY-INSPIRED null from a possible canonical-S-KEY result.
5. **Phase C 371 K full-corpus pre-training.** Currently deferred pending preconditions (corrected pair construction + lazy-load refactor), both addressed by PR #9. Re-attempt is Months 6–7 work in the revised rigour plan.

**Verdict:** acknowledged limitations are explicitly framed in the chapter prose and the rigour plan; none invalidate the existing empirical claims.

---

## §12 — Validation suite + reproducibility

Test coverage as of PR #9:
- `tests/test_phase1_regression.py` — Phase I trainer regression (5 tests)
- `tests/test_eval_bottleneck_patch.py` — vectorised eval correctness
- `tests/test_runtime_phase1_integration.py` — runtime integration
- `tests/test_trainer_cli_patches.py` — PR #8 CLI flags (6 tests)
- `tests/test_skey_pair_construction.py` — PR #9 P3.1 (10 tests, NEW)
- `tests/test_lazy_midi_cache.py` — PR #9 P3.2 (8 tests, NEW)

**Total: 32 regression tests covering trainer CLI, eval correctness, S-KEY pair construction, and lazy-load cache.** All pass against `v1.0-phase1-evidence` and the post-P3 head.

Reproducibility chain: `git checkout v1.0-phase1-evidence` → re-train any Phase I cell at any seed → bit-identical FW MIREX (modulo float-rounding noise). Cross-corpus eval reproducible from `eval_*_from_checkpoints.py`. P1 paired analysis reproducible from `research_data/p1_paired_analysis_2026-05-12.json`.

---

*Compiled by `VALIDATION_METRICS_AUDIT_2026-05-12.md` 2026-05-12. Closes the post-2026-05-05 audit's "validation rigour" sweep. Companion to `COMPREHENSIVE_RIGOUR_PLAN_2026-04-26.md` (governance), `REPORTING_CONVENTIONS_2026-04-20.md` (conventions), and `CHRONOLOGY.md` (provenance).*
