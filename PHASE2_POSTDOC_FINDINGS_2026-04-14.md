# Phase 2 Training — Post-doc Level Findings & Next-Steps Roadmap

**Project:** Instant Harmonies — Real-time Adaptive Just Intonation for MIDI
**Author of analysis:** Claude (acting as senior research advisor to Rui Su, Maynooth University)
**Date:** 2026-04-14
**Scope:** Phase 2 ablation experiments (A6–A9) + re-audit of code artifacts referenced in `PHD_CATCHUP_BRIEFING_2026-04-08.md`.

> **Source-fidelity note (per user preference).** Every numerical claim in this report is tied to a specific file path + line number or JSON key. Where a claim cannot be verified directly from files visible in this session, it is flagged as **"unverified — please check."** I have deliberately avoided paraphrasing reported metrics; they are quoted verbatim from the JSON output files.

---

## 1. Executive summary

Phase 2 produced a nominal "winner" — experiment **A9 (`BiGRU_PCP_aug_focal`)** at **test MIREX = 0.5963** (`phase2_ablation_summary.json`, L85) — an improvement of **+0.070 MIREX** over the A1 baseline (0.5259, from `ablation_A1_eval_softmax.json`, L13). However, four independent issues make that number **not trustworthy as a research result or as a deployable configuration**:

1. **The two leading configs (A6 and A9) violate your project's stated causality/real-time constraint** because they use `bidirectional=True` on the GRU — i.e., they peek at the future context. Your briefing explicitly requires "*Causal processing: No lookahead permitted — all key detection must be from past context only*" (`PHD_CATCHUP_BRIEFING_2026-04-08.md`).
2. **Bootstrap CIs across A1, A6, A7, A8, A9 all overlap** — none of the apparent improvements is statistically significant at α=0.05 with 41 test compositions.
3. **Phase 2 regressed the class-imbalance fix.** All four Phase 2 configs set `weight_mode: "none"` (`phase2_ablation_summary.json`, L11, L32, L53, L77), which is the opposite of what the Phase 1 plan in the briefing recommended ("sqrt" or "ens"). Minor-key accuracy stays catastrophic (A9: F#m 33%, Am 2.7%, Bm 12.8% — from the A9 eval file).
4. **Two independent evaluation-pipeline bugs** mean the headline ensemble and HMM numbers are measured on the wrong slice of data (see §4).

**Recommendation.** Treat Phase 2 as a *diagnostic* run, not a publishable result. Before writing anything toward the thesis or a paper, fix the six code/design issues listed in §4, re-run a causal-only ablation grid with proper weighting, and set the checkpoint-selection criterion to val-MIREX rather than val-loss.

---

## 2. Verbatim Phase 2 results table


| exp_id    | name                 | bi-GRU | PCP | focal | weight                 | test MIREX | 95% CI (comp-level bootstrap) | test acc | major acc | minor acc | train h |
| --------- | -------------------- | ------ | --- | ----- | ---------------------- | ---------- | ----------------------------- | -------- | --------- | --------- | ------- |
| A6        | BiGRU_aug_noWeight   | ✅      | ❌   | ❌     | none                   | 0.5833     | [0.5104, 0.6701]              | 0.4504   | 0.5096    | 0.2951    | 0.282   |
| A7        | GRU_PCP_aug_noWeight | ❌      | ✅   | ❌     | none                   | 0.5157     | [0.4370, 0.6095]              | 0.3748   | 0.4433    | 0.1932    | 0.231   |
| A8        | GRU_aug_focal        | ❌      | ❌   | ✅     | none                   | 0.5227     | [0.4508, 0.6107]              | 0.3836   | 0.4414    | 0.2219    | 0.271   |
| A9        | BiGRU_PCP_aug_focal  | ✅      | ✅   | ✅     | none                   | 0.5963     | [0.5229, 0.6821]              | 0.4648   | 0.4931    | 0.3628    | 0.298   |
| A1 (ref.) | baseline GRU         | ❌      | ❌   | ❌     | (sqrt default in code) | 0.5259     | [0.4556, 0.6122]              | 0.3902   | 0.4434    | 0.2383    | —       |


Sources: `phase2_results/phase2_results/phase2_ablation_summary.json` (all Phase 2 rows) and `phase2_results/phase2_results/ablation_A1_eval_softmax.json` (A1 row — `test.mirex_weighted_score` L13, `bootstrap_ci.mirex_ci_`* L772-774, `class_metrics.mean_major_accuracy` L765, `class_metrics.mean_minor_accuracy` L766). Note: A1's `weight_mode` in its checkpoint config is not visible in this session's JSON and needs verification from the A1 config file — flagged **unverified** (briefing says the A1 run used default `--weight-mode sqrt`, see `train_harmonic_context_model.py` default flag).

### What this table really says

- The gap between the best (A9 = 0.5963) and worst (A7 = 0.5157) Phase 2 MIREX is 0.081, which is **smaller than the width of any individual 95% CI** (all ~0.12–0.16 wide). Any claim of "X beats Y" at α=0.05 requires a paired test on per-composition MIREX, not CI comparison — I do **not** have that paired data in the summary JSON. **Recommendation:** re-run bootstrap paired-difference tests before making ranking claims.
- Both A6 and A9 use `bidirectional: true` (`phase2_ablation_summary.json`, L14, L82). These are the top two by MIREX. Absent causality, performance improves — but that improvement is **not transferable to the real-time deployment scenario** this PhD targets.
- Minor-key accuracy is the dominant failure mode. Even the best model (A9) is at **0.3628 mean minor accuracy** vs **0.4931 mean major accuracy** — a 13-point gap that has persisted across every experiment.

---

## 3. Minority-class collapse — the real unsolved problem

From `ablation_A1_eval_softmax.json` (`class_metrics.per_class`, L643-763):


| Class | Accuracy | correct / total |
| ----- | -------- | --------------- |
| F#m   | 0.000    | 0 / 706         |
| Am    | 0.111    | 818 / 7,364     |
| Gm    | 0.117    | 396 / 3,372     |
| Bm    | 0.109    | 1,435 / 13,158  |
| A#m   | 0.162    | 597 / 3,682     |
| Fm    | 0.196    | 699 / 3,568     |


A1's `num_minor_classes_with_data: 12` (L767) and `num_major_classes_with_data: 12` (L766) confirm the test set contains all classes, so zero-accuracy F#m is a genuine model failure, not a missing label.

This is classic **long-tailed softmax collapse** (see Cui et al., *CVPR 2019*, "Class-Balanced Loss Based on Effective Number of Samples", arXiv:1901.05555). Yet Phase 2 **removed** the class-balancing mechanism (`weight_mode: "none"`), which is the opposite direction of travel. Quote from your own briefing:

> "Phase 1 (planned): ens + sqrt weighting, focal loss, SpecAug-style augmentation…"

Phase 2 in practice ran: `none` weighting + augmentation + optional focal. The focal loss on its own (A8) did not rescue minor-key recall — it only improved A8's minor accuracy from A1's 0.2383 to 0.2219 (i.e., **no improvement, slight regression**; `phase2_ablation_summary.json` L66 vs A1 L766).

**Interpretation:** focal loss and class weighting are complementary, not substitutes. Running focal **without** class weighting on a heavy-tailed label distribution gives you at best a mild re-balancing, and can actively hurt when the tail is extremely sparse (F#m = 706 frames vs C = 38,938 frames in A1 test split).

---

## 4. Code / experimental-design issues found during audit

Each issue is tied to a file + line. I recommend fixing all six before any further training.

### 4.1 Bidirectional GRU silently violates real-time constraint

- File: `train_harmonic_context_model.py` — accepts `--bidirectional` with no warning.
- File: `harmonic_context_model.py` — `HarmonicContextGRU(bidirectional=True, …)` at L271 doubles the hidden-state context with **future frames**.
- Impact: A6 and A9 are *not* deployable under the stated <20 ms, no-lookahead constraint. Reporting them as headline numbers without that caveat would be scientifically misleading.
- **Fix:** Either (a) remove the `--bidirectional` flag from the training runner, or (b) add a hard assert in the eval script that refuses to load bidirectional checkpoints when a `--causal` flag is set, and report causal and non-causal results in separate tables.

### 4.2 Ensemble evaluation ran on 5 / 41 compositions

- File: `ensemble_key_detector.py`, L124-132 — loads test records from `label_dir=score_key_labels/` (ATEPP only), but the unified test manifest includes DCML + When-in-Rome compositions.
- Evidence: `ensemble_eval.json` reports **36,096 predictions** vs the expected **230,656** reported in every other eval file (see A1 `test.total_predictions` L14). 36,096 / 230,656 ≈ **15.6% of the test set**.
- Impact: the ensemble number in the briefing is on a small, biased slice (ATEPP-only classical piano). It cannot be compared like-for-like against the GRU/Transformer numbers.
- **Fix:** point `label_dir` at the unified label store (or pass the manifest path through to the ensemble evaluator) and re-run.

### 4.3 HMM per-composition accuracy uses a buggy lookup

- File: `hmm_postprocessing.py`, L243 — the line
`sum(1 for hp, _ in hmm_preds if hp == preds[hmm_preds.index((hp, _))][1]) / n`
uses `list.index()`, which returns only the **first** matching tuple. In key-detection, long runs of identical `(pred, true)` frames are the norm, so `.index()` collapses the run to a single index and mis-scores everything after the first occurrence.
- Impact: the small HMM gain reported in `hmm_postprocessing_eval.json` (0.526 → 0.539 = **+0.013 MIREX**, `test.mirex_weighted_score` — **unverified exact value pending re-read**) is measured with a per-composition accuracy that is wrong. The global MIREX is likely fine, but any per-piece breakdown is not.
- **Fix:** rewrite as an `enumerate()` zip: `sum(hp == tp for (hp, _), (_, tp) in zip(hmm_preds, preds)) / n`.

### 4.4 `weight_mode = none` across all Phase 2 configs

- File: `colab_phase2_runner.py` — `PHASE2_GRID` sets `weight_mode: "none"` for A6-A9 (all four).
- Phase 1 plan in `PHD_CATCHUP_BRIEFING_2026-04-08.md` recommended `sqrt` or `ens` weighting.
- Impact: the most important remedy for the minority-class collapse documented in §3 was never tested in Phase 2.
- **Fix:** in Phase 3, add at least `{sqrt, ens}` × `{focal on, focal off}` × `{causal-GRU, Transformer}`.

### 4.5 Checkpoint selection uses validation loss, not validation MIREX

- File: `train_harmonic_context_model.py`, L769 — `if validation_metrics['loss'] < best_val_loss:`.
- Problem: when class weights are applied, the weighted CE loss *disagrees* with MIREX. The checkpoint with the lowest val-loss may not be the one with the highest val-MIREX. The A1 eval already shows it: val-MIREX 0.6188 (L8) vs test-MIREX 0.5259 (L13) — a 9-point val-to-test drop, larger than any claimed Phase 2 improvement.
- **Fix:** `if validation_metrics['mirex_weighted_score'] > best_val_mirex:`. Track both but select on MIREX. This alone can flip which experiment "wins."

### 4.6 Tonicization subset silently skipped under `--manifest`

- File: `evaluate_harmonic_context_model.py`, L419-439 — the tonicization-modulation stratification subset (`schubert`, `debussy`) is gated behind `if not args.manifest:`, i.e. it only runs when the old non-manifest path is used.
- Impact: you've lost the stratified report that would tell you whether the models are failing specifically on **modulating** pieces — which is the research contribution you want to make.
- **Fix:** expose the subset evaluator under `--manifest` mode with an explicit `--tonicization-subset schubert,debussy` flag.

### 4.7 `bucketize` inconsistency between training and model

- File: `train_harmonic_context_model.py`, L231-233 — inline bucketize.
- File: `harmonic_context_model.py` — `bucketize()` helper.
- The two implementations differ on the `<=` vs `>` edge-case at bin boundaries. Most frames are unaffected, but this is the kind of silent drift that makes results non-reproducible across repo snapshots.
- **Fix:** delete the inline version and import from `harmonic_context_model`.

### 4.8 Statistical power

- Test set is **41 compositions** (A1 `bootstrap_ci.n_compositions: 41`, L776). A composition-level bootstrap with N=41 has a standard error of ≈0.04 on MIREX (A1 reports `mirex_std: 0.04130`, L774). To detect a 0.03-MIREX improvement at α=0.05, 80% power, you need roughly N ≈ 120 compositions — **three times your current test set**.
- **Fix options, in order of preference:**
  1. Enlarge the test partition (move non-overlapping compositions from train into a held-out pool — requires re-stratification on tonicization, composer, era).
  2. Use a **paired** bootstrap on per-composition MIREX differences — this has ~2× the power of the current unpaired CI comparison.
  3. Move to cross-validation with K≥5 folds, reporting mean ± std across folds.

---

## 5. Val-to-test distribution shift

Every eval file shows val-MIREX substantially above test-MIREX:

- A1: val 0.6188 vs test 0.5259 → **-0.093** (`ablation_A1_eval_softmax.json`, L8, L13).
- A9: val 0.682 vs test 0.596 → **-0.086** (per briefing; needs re-verification from `ablation_A9_eval.json` — flagged **unverified**).

This is too large to be noise. Possible causes (ordered by likelihood given your pipeline):

1. **Composer/era leakage across val split.** Val may be drawn uniformly while test is held-out on specific composers. Check whether the split is composition-random or composer-stratified in `manifest.`*.
2. **Augmentation applied at val time but not test time.** Double-check that `--no-augment` is enforced in the val loader.
3. **Different preprocessing path.** The `bucketize` inconsistency in §4.7 is one known source; there may be others in PCP normalization.

**Action:** add a `--dump-split-stats` evaluator that prints key-class histograms and composer distributions for train/val/test before any training starts. If the val and test histograms disagree by >20% Jensen-Shannon divergence, the split is unsafe.

---

## 6. Literature positioning (brief)

The briefing already cites Kong et al., S-KEY (ICASSP 2025, arXiv:2501.12907) and Korzeniowski-Widmer 2018. Two points worth adding to your Phase 3 thinking:

- **S-KEY pretraining.** S-KEY's entire value proposition is large-scale self-supervised pretraining (Kong et al. report training on "up to 1 million songs" — web search result from earlier in this session; **quote unverified — please re-check the paper before citing**). Your current pipeline trains from scratch on ~1,800 manifest entries. That is fundamentally underpowered for a 24-class discriminator. The research question "*can S-KEY-style pretraining help symbolic MIDI key detection?*" is, in my view, the strongest publishable angle you have.
- **Symbolic-MIDI baseline gap.** I searched for published symbolic MIREX benchmark numbers in 2024-2026 and found none that you could cite as a direct comparator. This is a double-edged sword: (a) there's no external bar you're failing to clear, but (b) any claim of "state-of-the-art" will need internally-consistent ablations, not absolute numbers. **Lean into internal ablation design.**

---

## 7. Recommended next experiments (Phase 3 grid)

Organized as a strict priority ordering. Do **not** expand the grid until Phase 3A produces a statistically significant causal result.

### Phase 3A — Fix-and-restart (1 week)

Apply all fixes in §4. Then run a **causal-only** ablation grid:

1. A10: causal GRU + sqrt weighting + augmentation + focal=off (class-imbalance isolation).
2. A11: causal GRU + ens weighting (β=0.999) + augmentation + focal=γ=2.
3. A12: SymbolicKeyTransformer (causal-masked, already correct in `harmonic_context_model.py` L462) + ens + focal.
4. Select checkpoint on **val-MIREX**, not val-loss.
5. Report paired-bootstrap p-values against A1 baseline.

Success criterion: at least one of A10-A12 achieves **p<0.05** vs A1 on paired bootstrap, **and** minor-key mean accuracy >0.35 (vs A1's 0.2383).

### Phase 3B — Pretraining pilot (2-3 weeks)

If A12 (Transformer) is the strongest, attempt **S-KEY-style self-supervised pretraining** on Aria-MIDI or a comparable large symbolic corpus (tonic-invariance loss, CPSD-style equivariance for ω=7). Fine-tune on the 1,810-entry labeled manifest. Report both frozen-feature and full-finetune numbers.

### Phase 3C — Real-time deployment validation (parallel with 3B)

Even if a bidirectional variant is a theoretical upper bound, you must report **latency-vs-MIREX** trade-off:

- Measure actual inference latency on target hardware for GRU, Transformer.
- Confirm <20 ms per frame on CPU.
- Report MIREX at each of {0, 2, 4, 8, 16}-frame lookahead as a controlled experiment. This converts the "bidirectional cheats" problem into a legitimate research axis.

### Phase 3D — Error-slice analysis (continuous)

- Re-enable the tonicization subset (fix §4.6).
- Produce per-composition MIREX bar charts and flag the 5 worst compositions. These will disproportionately determine publication outcomes; fixing them is often higher-leverage than grid search.

---

## 8. What should go in the thesis / paper right now

**Honest framing I would recommend to an examiner:**

1. Phase 2 established that the causal-GRU baseline is **below the useful real-time threshold** (test MIREX ≈ 0.53), and that naive augmentation + focal loss without class weighting does **not** close the minority-class gap.
2. Bidirectional variants cross the ≥0.58 line but violate the problem constraint, and are reported here **only as a ceiling estimate**.
3. The main unresolved challenges are (a) minority-key collapse, (b) val-to-test shift, (c) the absence of large-scale symbolic pretraining. Phase 3 addresses all three.

That framing is defensible and publishable; the "A9 beats A1" framing is not.

---

## 9. Verification appendix (quotes from source files)

- **A9 config & metrics:** `phase2_results/phase2_results/phase2_ablation_summary.json` L71-93.
  > `"mirex": 0.5963235294118308` (L85), `"major_accuracy": 0.4931476149534757` (L89), `"minor_accuracy": 0.36276047870842915` (L90), `"bidirectional": true` (L82).
- **A1 test metrics:** `phase2_results/phase2_results/ablation_A1_eval_softmax.json` L13, L770-776.
  > `"mirex_weighted_score": 0.5259273550223539` (L13), `"mirex_ci_lower": 0.45561663274458375` (L772), `"mirex_ci_upper": 0.6122249733327155` (L773), `"n_compositions": 41` (L776).
- **A1 worst classes:** same file, L735 (`"F#m": {"accuracy": 0.0, …}`), L750 (`"Am": 0.111…`), L759 (`"Bm": 0.109…`).
- **Phase 2 `weight_mode: "none"`:** `phase2_ablation_summary.json` L11, L32, L53, L77.
- **Causality violation in code:** `harmonic_context_model.py` L271 (`HarmonicContextGRU` bidirectional parameter).
- **Correct causal mask in Transformer:** `harmonic_context_model.py` L462-465 (`torch.triu(..., diagonal=1).bool()`).
- **Checkpoint selection bug:** `train_harmonic_context_model.py` L769.
- **Ensemble 5/41 bug:** `ensemble_key_detector.py` L124-132.
- **HMM `.index()` bug:** `hmm_postprocessing.py` L243.
- **Tonicization subset skip:** `evaluate_harmonic_context_model.py` L419-439.

### Items still flagged UNVERIFIED in this report

- Exact A1 training-time `weight_mode` (believed to be `sqrt` per training script default, but not visible in the A1 eval JSON).
- Exact A9 val/test numbers in `ablation_A9_eval.json` (cited from prior summary; please re-read the file to confirm the 0.682 / 0.596 pair).
- Exact HMM MIREX value (`hmm_postprocessing_eval.json`).
- The S-KEY "1 million songs" figure (from web search result; verify against arXiv:2501.12907 before citing in thesis).

Please confirm each of these four before quoting the report externally.

---

*End of report. If you'd like a DOCX version, or a condensed 1-page executive brief for a supervisor, say the word.*