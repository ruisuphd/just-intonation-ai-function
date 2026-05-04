# Comprehensive 11-month rigour-strengthening plan

**Cut to fit:** ~11-month runway (defence target March 2027), Colab Pro with T4/L4/A100/H100 available, supervisor feedback "good, just needs more references + more rigorous findings".

**Source audit:** `RESEARCH_RIGOUR_AUDIT_2026-04-26.md` (the postdoc-level methodology review that this plan implements).

---

## Progress log (revised 2026-05-01 — Month 1 substantially closed; formal cluster-bootstrap re-runs done; three pre-registered hypotheses ACCEPTED at Bonferroni α = 0.01)

This plan is being executed live. Section-by-section progress is logged here so the timeline remains anchored to actual completion rather than aspirational targets.

| Date | Section | Status | Notes |
|---|---|---|---|
| 2026-04-26 | Month 1 Week 1 — lit search | ✅ **complete** | 12 new APA citations added across Ch 1–8 (2026-04-26 + 2026-04-27 postdoc reviews); supervisor-feedback "more references" target exceeded. See `LITERATURE_SEARCH_OUTCOME_2026-04-26.md` and `POSTDOC_LITERATURE_REVIEW_2026-04-27.md`. |
| 2026-04-26 | Month 1 Week 1 — chapter prose updates | ✅ **complete** | Ch 1, 2, 3, 4, 6, 7, 8 updated; López → Nápoles López global rename; 3 broken cross-references fixed; 2 fake Kania placeholder citations corrected; Gotham→Arthur middle-author bug fixed in Ch 6. |
| 2026-05-01 | Audit-driven citation correction | ✅ **complete** | The Hentschel-2021-Frontiers entry conflated two distinct papers and was replaced with separate **Neuwirth, Harasim, Moss, & Rohrmeier (2018)** Frontiers entry for the Annotated Beethoven Corpus + **Hentschel, Neuwirth, & Rohrmeier (2021)** TISMIR entry for the DCML annotation standard, applied across Ch 1, 2, 3, 4, 5, 6, 7, 8 (audit citation finding). |
| 2026-04-26 | Month 1 Week 2 — Tier 1 GPU — BASELINE × 5 seeds | ✅ **complete (CPU)** | Mean test FW MIREX = **0.5844 ± 0.0196** (n=5 sample σ, ddof=1). Range 0.5645–0.6166. Supersedes the previously cited n=3 = 0.5820 ± 0.0038. The σ inflation is the expected effect of closing audit W1. |
| 2026-04-26 | Month 1 Week 2 — Tier 1 GPU — T6 seed a | ✅ **complete (T4)** | Single-seed test FW MIREX = 0.6368. Replicated at n = 5 by 2026-04-28 A100 session. |
| 2026-04-27 | Month 1 Week 2 — diagnose CPU/T4 detour | ✅ **complete** | Eval phase identified as the bottleneck on T4 (~2 h/seed); training itself was ~1.5 h/seed. The eval-bottleneck patch (disable per-epoch bootstrap) flagged for next sweep. |
| 2026-04-28 | Month 1 Week 2 — A100 session — T6 b/c/d/e + B9 restoration | ✅ **complete** | T6 cell n = 5 mean = 0.6426 ± 0.0266. B9 restoration: 5-seed restored mean = 0.5164 ± 0.0059 (closes audit W5). |
| 2026-04-28 / 29 | Month 1 Week 2 — Mixed A100 + T4 — T6_T1 × 5 | ✅ **complete** | T6_T1 cell n = 5 mean = **0.6707 ± 0.0103** (best-evaluated detector by FW mean). σ-collapse from σ_T6 = 0.0266 to σ_T6_T1 = 0.0103 (2.6×) is a methodologically novel observation. All 5 T6_T1 seeds individually exceed classical 3-profile (0.6201). |
| 2026-04-29 / 30 | Month 1 Week 2 — T4 — T6_T1_T2 seeds *a*, *b* | ✅ **complete** | n = 2 preliminary. |
| 2026-04-30 / 05-01 | Month 1 Week 2 — T4 — T6_T1_T2 seeds *c*, *d*, *e* | ✅ **complete** | T6_T1_T2 cell n = 5 mean = **0.6606 ± 0.0122**. **Closes audit weakness W2 — 20/20 cumulative-cell training runs done.** Same-seed paired Δ_FW vs T6_T1 = −0.0102 (negative direction, consistent with multi-task negative transfer). |
| 2026-04-30 | Project audit | ✅ **complete** | `phd_project_audit_report_2026-04-30.md` produced; flagged 5 critical findings (C1–C5) and 5 major findings (M1–M5). |
| 2026-05-01 | Audit C1 — pre-registration deviations log | ✅ **complete** | Retroactive consolidation entry appended to `PHASE1_PREREGISTRATION_2026-04-25.md` §6 with explicit transparency disclosure that the retroactive logging is itself a deviation from §4. No scientific element altered. |
| 2026-05-01 | Audit C2 — restore H5 to pre-registered meaning | ✅ **complete** | H5 restored to "full pre-registered stack T6_T1_T2 ≥ classical 0.6201 FW" across Ch 1, 6, 7, 8. T6_T1_T2 cell mean SATISFIES H5 by Δ_FW = +0.0405. |
| 2026-05-01 | Audit C4 — soften deployable claim | ✅ **complete** | "T6_T1 drop-in weights swap" replaced with honest "best-evaluated detector by FW mean; runtime integration of global PCP feature is a Tier-0 future-work item" across all chapters. Three causality policies for `global_pcp` documented (running PCP recommended as default). |
| 2026-05-01 | **Mac-side cluster bootstrap (formal n = 5 vs n = 5 re-runs)** | ✅ **COMPLETE** | `research_data/run_phase1_paired_bootstrap_2026-05-01.py` produced canonical output `research_data/phase1_paired_bootstrap_2026-05-01.json`. **Three of the five family-wise pre-registered hypotheses formally accepted at Bonferroni α = 0.01**: H1 (T6_T1_T2 > B9, primary outcome) at *p* < 0.0001; H2 (BASELINE > B9) at *p* = 0.0008; H3 (T6 > BASELINE) at *p* = 0.0022. H4a, H4b fail-to-reject at α = 0.01. Phase I formal evidence is closed. |
| 2026-05-01 | Audit M1, M2, M3, M4, N1, N4 — repo hygiene | ✅ **complete** | M1 + N1: Ch 5 §5.6 broken Markdown fence + §5.4.3 / §6.2.2 duplicate headings removed. M2: aggregator script fixed (BASELINE included; --input-dir/--output-md args; alias dedup). M3: root `train_phase1.py` `masked_mirex` aggregation bug fixed + deprecation header added. M4: README + Ch 5 §5.12 corrected from `start_all.sh` to `start.sh`. N4: minimal `tests/test_phase1_regression.py` (5/5 pass). |
| 2026-05-01 | Tier-0 future work — runtime integration of T6_T1 | ⏳ **scheduled** | The only remaining Tier-0 item before the Phase I empirical chapter is fully locked. Specifically: (a) load `HarmonicContextGRUPhase1` in `harmonic_context_runtime.py:61–64`; (b) compute global PCP from active note window (running causality policy as default); (c) feed as `batch['global_pcp']`; (d) latency-profile vs B9 runtime. Estimated 1–2 days engineering. |
| 2026-05-08 onward | **Month 2 (target start)** | ⏳ next | POP909 cross-corpus (T2.1) + BPS-FH within-classical secondary (T2.2) + BMA refit (T2.5) on A100 with eval-bottleneck patch applied first. |
| 2026-05-08 | **Month 2 — Tier 2.2 (BPS-FH) + Tier 2.1 (POP909) initial sweep** | 🟡 partial | T6_T1 × 5 zero-shot on BPS-FH = **0.8065 ± 0.0069 FW** (32 first movements; σ tighter than σ_T6_T1_ATEPP = 0.0103 — first cross-corpus σ-collapse replication). POP909 BASELINE × 3 + T6_T1 × 3 trained successfully but had pipeline bug: the original POP909 manifest had no val split + the trainer's hardcoded ATEPP-41 filter dropped all POP909 test records → eval JSONs reported 0.0000. See `RESEARCH_FINDINGS_2026-05-09.md` §3.1 for the full diagnosis. |
| 2026-05-09 | **Patched aggregator + corpus-agnostic regression tests** | ✅ complete | `phase1_beat_classical/aggregate_phase1_results.py` made corpus-agnostic (`--composition-id-set {atepp41|all|<path>}`, `--skip-reference-baselines`, `--variants`, `--allow-arbitrary-labels`, `--corpus-tag`); EVAL_PATTERN regex relaxed from `\d{10,}` to `\d+` (closes a latent bug where canonical 9-digit seed_int 440397851 was silently dropped); 4 new `--test-filter` regression tests + 2 new corpus-agnostic-aggregator tests added; all 28 tests passing. |
| 2026-05-09 | **Patched trainer with `--test-filter`** | ✅ complete | `phase1_beat_classical/train_phase1.py` patched with `--test-filter {atepp41|none|<json>}` argument; default `atepp41` preserves chapter back-compat. Standalone eval-from-checkpoint scripts (`eval_pop909_from_checkpoints.py`, `eval_bps_fh_from_checkpoints.py`) added to project tree for the salvage path. Re-zipped as `phase1_month2_2026-05-09.zip`. |
| 2026-05-09 | **POP909 epoch-1 LB salvage + BPS-FH BASELINE comparator** | ✅ complete | Path-A re-eval (no retraining) using saved checkpoints. POP909: BASELINE = 0.3038 ± 0.0356, T6_T1 = 0.7002 ± 0.0151, paired Δ = +0.4005 (95% CI [+0.3704, +0.4298], p ≈ 0, 176/182 pieces +ve) — **EPOCH-1 LOWER BOUND** because the original POP909 manifest had no val split (best_epoch stuck at 1). BPS-FH: BASELINE = 0.7563 ± 0.0241, T6_T1 = 0.8065 ± 0.0069, within-corpus paired Δ = +0.0499 (95% CI [+0.0363, +0.0640], p ≈ 0, 29/32 pieces +ve). **σ-collapse cross-corpus asymmetry discovered**: σ_BASELINE INCREASES under shift (0.0196→0.0241, 1.23×); σ_T6_T1 DECREASES (0.0103→0.0069, 0.67×). T6_T1 is more robust to distribution shift than BASELINE. New publishable methodological angle. |
| 2026-05-09 | **POP909 manifest v2 (70/15/15) + retrain in progress** | 🟡 in progress | New manifest `pop909_manifest_2026-05-09.json` (636 train + 136 val + 137 test). Retrain BASELINE × 3 + T6_T1 × 3 with `--test-filter none` running in fresh Colab session. Expected wall-clock ~3 GPU-h on A100. Result will replace the epoch-1 LB and produce chapter-citable POP909 numbers. |
| 2026-05-09 | **5-pass postdoc reviewer audit** | ✅ complete | `POSTDOC_REVIEWER_PASS_2026-05-09.md` (15 issues identified: 2 HIGH, 6 MEDIUM, 7 LOW). Two HIGH-severity items: chapter-prose consistency with the cross-corpus evidence (~1 week of writing) and BMA ensemble refit with T6_T1 (~half day, closes deployable-engine gap). |

**Schedule status at 2026-05-01:** Month 1 (Tier-1 + lit-review + Phase I cumulative ablation + formal cluster bootstrap + audit remediation) is **substantially complete in 5 days vs the planned 3 weeks**. Audit-driven revisions on 2026-05-01 added one extra day to the schedule but produced material strengthening: three pre-registered hypotheses are now formally accepted at Bonferroni α = 0.01 rather than provisional, and the chapters are now examiner-defensible.

**Phase I empirical headline (final, 2026-05-01)**:
- **All four cumulative cells complete at the amended n = 5** (BASELINE, T6, T6_T1, T6_T1_T2).
- **H1 (primary outcome): T6_T1_T2 vs B9 — ACCEPTED** at Δ_CE = +0.1947, *p* < 0.0001.
- **H2: BASELINE vs B9 — ACCEPTED** at Δ_CE = +0.1068, *p* = 0.0008.
- **H3: T6 vs BASELINE — ACCEPTED** at Δ_CE = +0.0759, *p* = 0.0022.
- **H4a: T6_T1 vs T6 — fail-to-reject** at α = 0.01 (Δ_CE = +0.0147, *p* = 0.198).
- **H4b: T6_T1_T2 vs T6_T1 — fail-to-reject** at α = 0.01 (Δ_CE = −0.0027, *p* = 0.674).
- **H5 (auxiliary, threshold check): satisfied** at the formally pre-registered T6_T1_T2 cell by Δ_FW = +0.0405.
- **σ-collapse**: σ_T6_T1 = 0.0103 < σ_T6_T1_T2 = 0.0122 < σ_BASELINE = 0.0196 < σ_T6 = 0.0266 — a methodologically novel observation flagged for cross-corpus replication in Month 2 (BPS-FH).

**Lessons folded into the plan:**

1. **Free-tier T4 is unreliable for sweeps > 1 h** — eval bottleneck makes per-run time ~3.5–4 h not 30 min. Budget A100 credits for all multi-run experiments going forward; **before the next sweep, implement the eval-bottleneck patch** (disable per-epoch bootstrap in `train_phase1.py`'s eval routine; recover the audit's pre-flight 5-min/run estimate).
2. **Section-by-section discipline pays off** — the CPU+T4 detour preserved BASELINE n=5 because of incremental Drive backups; without that, 16 h of compute would have been zero net progress.
3. **Skip-if-exists logic in `run_one()`** makes the runner idempotent — the patch worked end-to-end across the 2026-04-29/30 session and the 2026-04-30/05-01 session, preserving 17 already-completed seeds without retraining.
4. **Pre-registration governance is non-negotiable.** The 2026-04-26 amendment (n=3 → n=5) was made without an immediate deviations-log entry; that gap was caught by the 2026-04-30 audit and patched on 2026-05-01 with explicit retroactive disclosure. Any future amendment must be appended to the pre-registration's §6 deviations log on the same day it is made — no exceptions.
5. **The cluster-bootstrap is materially more powerful than per-seed paired-*t* on this test split.** H3 cleared Bonferroni at the cluster-bootstrap level (*p* = 0.0022) where the per-seed paired-*t* alone (one-sided *p* = 0.0114) was at the boundary — exactly the power gain the pre-registration anticipated for the per-piece dependence structure.

---

## 0. What this plan changes from the 4-week version

The 4-week plan in §9.1 of the audit was the *minimum* viable upgrade. With 11 months of runway and A100 access we can do **all of Tier 1 + all of Tier 2 + selected Tier 3**, plus iterate on whichever empirical results turn out to be surprising. The pacing is therefore much more relaxed than the 4-week version, and the **scope is expanded**: each major experiment is now reported at n = 5 seeds (the field standard) rather than the audit's compromise n = 3, and we have time to run a true cumulative ablation across multiple corpora rather than a single-corpus headline.

A100 access changes the wall-clock cost of every Phase I-style training run from ≈ 30 min on T4 to ≈ 5 min on A100 — a 6× speed-up that turns the original 12 GPU-h Tier-1 cumulative-cell experiment into a 2 GPU-h afternoon job. This is why the plan below can afford to ask for n = 5 seeds rather than n = 3.

---

## 1. Month 1 — Tier 1 (defence-blocking) + lit search

### Week 1 — Public registration + literature search (no GPU)

* **Mon (~30 min):** OSF registration of `PHASE1_PREREGISTRATION_2026-04-25.md` and `phaseB_preregistration.md`. Add the two `osf.io/...` URLs to the corresponding reference entries in Ch 1, 6, 7, 8.
* **Tue–Thu (~3 days):** systematic literature search for the three "first-in-the-field" claims (Ch 1 §1.4.1, Ch 3 §3.2.4, Ch 3 §3.5.3). Search ISMIR / SMC / TISMIR / NIME / ICASSP / DLfM proceedings 2018–2026; ACM DL; IEEE Xplore; Google Scholar. Record findings in a new `LITERATURE_SEARCH_2026-04-26.md` document.
* **Fri (~1 day):** revise chapter language based on the search outcome. If a "first" claim is confirmed: remove the qualifying language. If counter-evidence is found: add the prior-work citation and rewrite the contribution claim narrowly (e.g., "first to combine X, Y, and Z in a single runtime", with X / Y / Z pinned down).
* **Outcome:** OSF-registered pre-registrations + audited "first" claims. Closes audit weaknesses W4 and W6. Zero GPU spent.

### Week 2 — Tier 1 GPU experiments on A100 (one afternoon)

* **Tue afternoon (~3 GPU-h on A100):** run the three deferred Phase I cumulative cells, **at n = 5 seeds each**:
  * T6 / `20260425a/b/c/d/e` (5 seeds × 30 epochs)
  * T6_T1 / `20260425a/b/c/d/e`
  * T6_T1_T2 / `20260425a/b/c/d/e`
  * Plus 2 extra BASELINE seeds (`20260425d/e`) to bring the existing n = 3 to n = 5.
  * Plus the 3 lost B9 seeds (`20260309/10/11`) re-trained on the original `unified_training_manifest.json` to restore the published 5-seed comparator.
* **Total experiments:** 4 cells × 5 seeds + 2 extra BASELINE + 3 restored B9 = 25 training runs. **At ~5 min/run on A100, this is one ~2-hour Colab session.** One overnight Colab Pro session at the most.
* **Wed–Thu (~1 day):** aggregate. Refresh `phase1_summary.json` with all 4 cells × 5 seeds. Re-run the paired cluster bootstrap with the restored 5-seed B9 comparator. Update `FINAL_FINDINGS.md` → `FINAL_FINDINGS_v2.md`. Regenerate fig 5.7 with the 4-cell cumulative ablation table.
* **Outcome:** All four pre-registered hypotheses (H1, H2, H3, H4a, H4b) tested at n = 5 seeds with the canonical 5-seed B9 comparator. Closes W1, W2, W5.

### Week 3 — Chapter prose pass

* Update Ch 6 §6.6.9 with the new n = 5 numbers + the 3-cell cumulative ablation table.
* Update Ch 7 §7.3 (the central reframing) with the actual cumulative-cell outcomes — which I expect to land in one of the three scenarios I outlined in §6 of the audit; the prose structure I drafted in Ch 7 already accommodates all three.
* Update Ch 8 §8.2.3 + §8.5.1 with the matching numbers.
* Update Ch 1 §1.4.3 (Contribution 6) with the cumulative result.
* Cross-chapter consistency check (the same grep I ran in the previous round).
* **Outcome:** Tier 1 fully integrated into the thesis. End of month 1.

---

## 2. Month 2 — Tier 2.1 (POP909) + Tier 2.2 (BPS-FH) + Tier 2.3 (TAVERN promoted) + Tier 2.5 (BMA refit)

**MAJOR REVISION 2026-05-09:** Tier 2.2 (BPS-FH) substantively landed in the 2026-05-09 Path-A re-eval (T6_T1 × 5 + BASELINE × 5 zero-shot from ATEPP-canonical checkpoints; within-corpus paired bootstrap; σ-collapse cross-corpus replicated). Tier 2.1 (POP909) had a pipeline bug (epoch-1 LB), now retraining with patched trainer. **TAVERN (Tier 2.3) is PROMOTED from Month 3 weeks 10 to Month 2 weeks 6–7** because (a) σ-collapse has now replicated on ONE cross-corpus dataset (BPS-FH) and a third corpus is needed to make the generalisation claim publishable, (b) the third corpus closes the per-corpus σ-asymmetry observation into a robust pattern.

### Week 4 (current — 2026-05-09 to 2026-05-15) — POP909 retrain + BMA refit + formal σ-ratio bootstrap

* **POP909 retrain** (~3 GPU-h on A100): 5 seeds × 2 cells × 30 epochs with the new 70/15/15 manifest + `--test-filter none`. Replaces the epoch-1 lower-bound with proper-trained chapter-citable numbers. **Bump from n = 3 to n = 5 seeds to bring POP909 into line with ATEPP-41 + BPS-FH** (R1.4 in the postdoc reviewer pass).
* **POP909 vs classical 3-profile baseline** (~30 min wall-clock + 1 hour analysis): run `evaluate_classical_baseline.py --manifest pop909_manifest_2026-05-09.json --label-dirs pop909_score_key_labels`; paired bootstrap T6_T1 (POP909) vs classical (POP909). **Closes the original Tier 2.1 pre-registered hypothesis test.**
* **BMA ensemble refit** (~half day, ~0.1 GPU-h): refit the BMA weights with T6_T1 (not BASELINE) inside the §7.4 complementary ensemble. Re-evaluate on ATEPP-41 + BPS-FH + POP909. **Closes the deployable-engine gap (R5.3 in the postdoc reviewer pass — HIGH severity).**
* **Formal σ-ratio bootstrap** (~half day analysis, no new training): bootstrap 95 % CI on σ_T6_T1/σ_BASELINE for each corpus; permutation test for the cross-corpus σ-asymmetry. Adds formal CI to the σ-collapse cross-corpus claim (R1.1 in the postdoc reviewer pass).

### Week 5 (2026-05-16 to 2026-05-22) — TAVERN ingestion + zero-shot eval (PROMOTED from Month 3)

* **TAVERN ingestion adapter** (~2–3 days engineering): write `parse_tavern.py` to convert the Humdrum **kern files (TAVERN-master/{Composer}/{Opus}/Joined/{filename}_a.krn) into the canonical per-piece JSON schema. Use `music21.converter` for the Humdrum parsing; the `**function`, `**harm`, and `**kern` streams need to be aligned per-event. TAVERN ships ~1110 phrases across 27 works (17 Beethoven theme-and-variations + 10 Mozart T&V) — roughly 30× more annotated material than BPS-FH.
* **TAVERN zero-shot eval** (~1 hour wall-clock on A100): mirror `eval_bps_fh_from_checkpoints.py` for TAVERN; BASELINE × 5 + T6_T1 × 5 from ATEPP-canonical checkpoints; within-corpus paired bootstrap; per-composer subgroup analysis (Beethoven phrases vs Mozart phrases separately, addressing R2.2 in the postdoc reviewer pass).
* **Composer-overlap audit**: TAVERN includes Mozart, which overlaps with the DCML training corpus (`dcml_corpora/mozart_piano_sonatas`). Document the overlap explicitly in the chapter; consider it a "within-classical" replication rather than "fully-out-of-distribution."
* **Predicted outcome:** σ-collapse replicates on TAVERN (σ_T6_T1 < σ_BASELINE within both Beethoven and Mozart subgroups). Modulating-subset null replicates for the third time (after ATEPP-9 and DCML-30). **Three-corpus σ-collapse + four-corpus modulating-null is a publication-grade contribution** (ISMIR 2027 submission target).

### Week 6 (2026-05-23 to 2026-05-29) — Chapter prose pass + σ-collapse paper draft

* **§6.6.10 (NEW): "Cross-corpus generalisation: POP909, BPS-FH, TAVERN"** — three-corpus table with per-corpus n, FW, σ, paired bootstrap, σ-ratio.
* **§7.3.6 (NEW): "Cross-corpus σ-collapse asymmetry"** — the BASELINE σ ↑ vs T6_T1 σ ↓ asymmetry observation with formal bootstrap CIs.
* **§8.5.2 reframing**: "Cross-corpus generalisation" promotes from "post-thesis priority" to "thesis-defended on three corpora; further corpora (Aria-MIDI, non-Western) are post-thesis priority."
* **σ-collapse paper draft** (in parallel, ~1 week of writing): 4-page short paper for ISMIR 2027 LBD or TISMIR. Title: *"Augmentation-induced robustness to distribution shift in symbolic key-finding: cross-corpus replication on Beethoven Piano Sonatas + Theme-and-Variations + POP909."* Uses existing data; no new experiments.

### Week 7 (2026-05-30 onward) — Chapter consistency pass + reproducibility hardening

* **Chapter prose consistency pass** (~1 week, R5.1 HIGH severity): grep + revise every chapter against a frozen canonical evidence table (new doc `CANONICAL_EVIDENCE_2026-05-09.md`). Particular focus on:
  - H4a fail-to-reject framing (R1.2): replace any "T6_T1 statistically beats T6" with the precise "highest cell-mean and tightest σ; H4a paired test fail-to-reject at α = 0.01"
  - σ-collapse asymmetry framing (R3.2): label as post-hoc + cross-corpus replicated
  - BPS-FH composer overlap (R2.1): "zero-shot to unseen ensemble + work-set; partially-seen composer"
  - Deployable claim: T6_T1 inside the §7.4 ensemble (not BASELINE) post-BMA-refit
  - Contribution ranking (R5.2): elevate σ-collapse cross-corpus to a top-tier methodological contribution
* **Reproducibility hardening** (~1 day):
  - Standalone manifest builders (`build_pop909_manifest.py`, `build_bps_fh_manifest.py`); R4.2
  - Manifest-validation pre-flight check (R4.5)
  - Test-suite expansion (`tests/test_parse_bps_fh.py`, `tests/test_parse_pop909.py`, `tests/test_eval_from_checkpoints.py`); R4.3
  - Lock file (`requirements_lock_2026-05-29.txt`); R4.4

* **Outcome:** Months 2 + 3 (per the original plan) are substantively complete by end of May 2026. Cross-corpus story is three-corpus solid. Deployable engine has the BMA refit. Chapter prose is consistent. End of revised Month 2 / Month 3.

---

## 3. Month 3 (2026-06) — Reserved for slippage + Tier-3 advance work

The original plan reserved Month 3 for Tier 2.2 (BPS-FH) + Tier 2.3 (TAVERN). Both are now folded into Month 2. Month 3 becomes **slippage buffer + Tier 3.1 (regime detector) advance work**:

* **Buffer** for any Month 2 work that overruns (TAVERN adapter is the most likely overrun risk; ~3 days estimated could blow out to ~7).
* **Tier 3.1 advance**: regime-detector front-end design + small-scale prototype on the existing data. Originally Months 8–9; advancing to take advantage of the cross-corpus pipeline now in place.
* **σ-collapse paper completion + submission** (target: ISMIR 2027 LBD deadline late September; finish drafting in Month 3, polish through Month 4).
* **Optional: BPS-FH-clean ablation** (R2.1, OPTIONAL): re-train T6_T1 with all DCML Beethoven content removed (~3 GPU-h on A100); verifies the cross-corpus result is not a Beethoven-overlap artefact. Run only if a reviewer presses on R2.1; otherwise the disclosure in §6.6.10 prose is sufficient.

---

## 4. Month 4 — Tier 2.4 (hyperparameter sensitivity)

### Weeks 12–13 — Hyperparameter sensitivity sweep

* Vary one hyperparameter at a time around BASELINE: hidden size *h* ∈ {48, 96, 144, 192, 256, 384}; dropout ∈ {0.0, 0.1, 0.2, 0.3}; ENS β ∈ {0.99, 0.999, 0.9999, 0.99999}; learning rate ∈ {3×10⁻⁴, 1×10⁻³, 3×10⁻³, 1×10⁻²}; batch size ∈ {4, 8, 16, 32}.
* **Specifically tests audit's W7 question**: does h = 192 help on the **expanded** 525-record pool the way it did *not* help on the 250-record pool?
* 1 seed per cell to start; expand to 3 seeds for any cell that shows a > 0.01 FW improvement.
* **GPU cost:** ~22 cells × 1 seed = ~2 GPU-h on A100.

### Week 14 — Heatmap figure + chapter prose pass

* Hyperparameter sensitivity heatmap (new figure).
* Update Ch 6 + Ch 7 with the sensitivity analysis.
* End of month 4.

---

## 5. Month 5 — Tier 2.6 (user study)

### Weeks 15–17 — N = 8 user study

* Wessel & Wright (2002) protocol. N = 8 trained pianists. Maynooth Music Department recruitment pool.
* Three latency conditions per pianist: 0 ms added, 5 ms added, 10 ms added (vs the natural 0.063 ms median full-system latency).
* 1-7 Likert: "feels alive vs delayed". Optional second metric: rate of "tuning event complaint" (the user-felt analogue of MIREX error).
* Pre-register the user-study plan on OSF before recruitment starts.
* **Predicted outcome (audit §7 T2.6):** N = 8 has limited power; detect Cohen's d ≈ 1.0 effect at α = 0.05 with ~75 % power. Likely 0 ms vs 10 ms is detectable; 0 ms vs 5 ms is not. Either result strengthens the thesis.

### Week 18 — Analysis + chapter prose pass

* Update Ch 6 §6.5 (qualitative + user study) with the empirical results.
* Replace the "PENDING EXECUTION" placeholder in §6.5.2.
* End of month 5.

---

## 6. Months 6–7 — Tier 3.2 (Aria-MIDI full-scale pre-training)

This is **the single largest empirical experiment** in the post-thesis programme. The S-KEY-Symbolic pipeline already ingests Aria-MIDI v1-deduped-ext (371 053 files; byte-level dedup against ATEPP-41 returned 0 collisions; Su, 2026e). Phase C tested mode-only fine-tuning at 5 000 files; the **full-scale** run has not been done.

### Weeks 19–22 — Pre-training execution

* `pretrain_symbolic_key.py` runs on 1 A100 for ~1 week to converge on the full 371 K corpus with the S-KEY equivariance loss.
* Fine-tune on ATEPP-41 train + DCML Strategy A train (the BASELINE pool) with the standard cross-entropy + ENS β = 0.999.
* Compare against from-scratch BASELINE.
* **Predicted outcome:** Either (a) Aria-MIDI pre-training adds Δ_FW ≈ +0.02 to +0.05 on top of BASELINE (the pre-training transfer hypothesis is supported, contradicting the small-scale Phase C null), or (b) it adds nothing or harms (the small-scale null replicates at scale). Both outcomes are strong publishable results.

### Weeks 23–26 — Analysis, chapter integration, journal-paper drafting

* Update Ch 6 §6.9 (Aria-MIDI pre-training evaluation) with the empirical result, replacing the "designed and validated on subsets" placeholder language.
* Begin drafting the post-thesis journal paper (likely TISMIR or Music Perception).
* End of month 7.

---

## 7. Months 8–9 — Tier 3.1 (regime-detector front-end) + Tier 3.5 (class-imbalance comparison)

### Weeks 27–30 — Regime-detector front-end

* Small (h = 32) front-end model classifying piece as mono-tonal vs modulating from the first 256 events.
* Two specialised heads downstream: a mono-tonal-specialised head and a modulating-specialised head, each fine-tuned on the relevant subset.
* Evaluate the routed system against the unified BASELINE on ATEPP-41, POP909, BPS-FH, TAVERN.
* **Predicted outcome:** Closes the residual −0.10 mono-tonal gap *if* the data-side intervention has run out of room. Paper-sized contribution.

### Weeks 31–33 — Class-imbalance comparison

* Compare ENS (current BASELINE) against label smoothing, LDAM (Cao et al., 2019), and class-balanced focal on the BASELINE pool.
* ~5 GPU-h on A100. Closes audit W12.

### Week 34 — Chapter integration

---

## 8. Months 10–11 — Thesis polish + viva preparation

### Weeks 35–38 — Open-source the C4 framework (Tier 3.3)

* Extract `compute_missing_bootstraps.py`, `phase1_beat_classical/fix_val_leakage.py`, the FW/CE convention spec, the pre-registration template, and the manifest-disjointness audit into a `pip install symbkey-eval` package. Apache 2.0.
* Submit to PyPI. Cite from the thesis as "additional artefact, available at github.com/<user>/symbkey-eval".

### Weeks 39–42 — Final chapter pass + viva preparation

* End-to-end thesis read-through with the supervisor.
* Mock viva session with internal reviewer.
* Submit to defence.

---

## 9. What I (Claude) will do autonomously while you work in parallel

While the GPU experiments (T1.1, T2.1, T2.2, T2.3, T2.4, T2.6, T3.2) progress, there is non-trivial preparation work I can do that does not require waiting for results:

* **Build the literature-search starter pack from your `papers/` folder.** Map every "first" / "state-of-the-art" claim in Ch 1 / 3 to specific candidate prior-work papers in your `papers/04_key_finding/`, `papers/01_just_intonation_and_adaptive_tuning/`, `papers/03_web_audio_midi_and_browser_platform/` directories. This converts the 1-day systematic-search task to a 4-hour citation-verification task.
* **Pre-build the POP909 manifest adapter.** Write `parse_pop909_strategy_a.py` analogous to the existing `parse_dcml_strategy_a.py` so the cross-corpus evaluation in Month 2 is plug-and-play.
* **Pre-build the BPS-FH and TAVERN ingestion adapters** for Month 3.
* **Update the Colab notebook** to support A100 explicitly (`--device cuda` is already there; add a multi-cell variant for the cumulative ablation).
* **Draft the OSF registration text** ready for upload, with the specific decision rules from the pre-registration formatted as the OSF "hypothesis" field.
* **Set up the `phase1_summary.json` aggregator** so it auto-rebuilds when new eval JSONs are added.
* **Pre-write the chapter-update templates** (the prose "fill in the new numbers" patches) so each post-experiment chapter pass takes hours rather than days.

These are the tasks I'll start on in the very next conversation turn, regardless of what GPU experiment is running.

---

## 10. Cumulative deliverables at end of month 11

* **Empirical:** Phase I cumulative ablation at n = 5 seeds; cross-corpus evaluation on POP909-CL, BPS-FH, TAVERN; hyperparameter sensitivity sweep; user study; full-scale Aria-MIDI pre-training; regime-detector front-end; class-imbalance comparison.
* **Methodological:** OSF-registered pre-registrations; literature-search-validated "first" claims; reproducibility framework released as `pip install symbkey-eval`.
* **Thesis chapters:** Ch 1–8 fully refreshed; new subsections in Ch 6 for each cross-corpus + sensitivity + user study; new figures (cross-corpus bar, sensitivity heatmap, latency-perception plot, regime-detector confusion matrix).
* **Publications-in-preparation:** ≥ 1 journal paper (TISMIR / Music Perception); ≥ 1 conference short paper (NIME / SMC); the C4 framework as an open-source release.

---

*This plan is calibrated to the resources and runway you confirmed: T4/L4/A100/H100 access via Colab Pro, defence target March 2027, supervisor mandate to add references and rigour. Adjust pacing based on actual progress. The §1 (Month 1) Tier-1 work is the prerequisite for everything downstream; everything from Month 2 onward can re-order based on what the empirical results turn up.*
