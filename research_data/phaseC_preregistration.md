# Phase C Pre-Registration — Pretraining Transfer + Modulation-Specialist Loss

**Date written:** 2026-04-18 (to be frozen **before** any Phase C run begins).
**Plan reference:** Phase C (M5–M6 of the PhD plan).
**Baseline handoff:** [`phaseB_consolidation_2026-04-18.md`](phaseB_consolidation_2026-04-18.md).
**Branch:** `main` (sequence `698520d` → Phase B artefact commit → this pre-reg).

This document commits the Phase C experimental protocol. Any deviation after kickoff gets a dated amendment entry in §10 with diff link and rationale.

---

## 1. Motivation — why Phase C exists

Phase B's "Null + ceiling" outcome (per pre-reg §1): **three statistically-supported ARCH_WINNERs** (B9, B10, B11 at plain MIREX ≈ 0.52 ± 0.003), but **zero STRONG_WINNERs** and **zero MODULATION_WINNERs**. Classical profile correlation (KK + Temperley + AS, deterministic, no NN) beats the best causal-neural cell by Δ = −0.165 composition-equal (p < 0.001).

Two hypotheses explain why neural lags classical:

**H1 — Data-limited.** 250 training compositions is too few for a 67k-parameter GRU to learn the global pitch-class distributions that classical computes analytically. **Test: pretraining transfer.** If a large-MIDI pretrained encoder improves the fine-tuned MIREX by ≥ 0.015 vs B9, H1 is supported.

**H2 — Representation-limited for modulation.** Classical fundamentally cannot track per-frame key changes — it computes ONE global key per piece. The gap on modulating pieces (B10 = 0.4835 vs classical ≈ 0.4867) is small. **Test: modulation-specialist loss.** If frame-weight upweighting on modulating compositions beats classical on the modulating subset by ≥ 0.015, H2 is supported — and this is the most scientifically distinctive outcome (a MODULATION_WINNER that classical cannot reach by design).

Phase C runs BOTH paths in parallel; they are independent and non-competing.

---

## 2. Paths and cells

### 2a. Path A — Pretraining transfer (4 cells)

All cells evaluated on the same frozen 41-composition ATEPP test split as Phase B.

| Cell | Base | Adapter | Train data | Fine-tune epochs |
|---|---|---|---|---|
| **C1** | Moonbeam 309M (frozen encoder) | LoRA r=16 on classifier head | ATEPP 250 files (same as Phase B) | 10 |
| **C2** | Moonbeam 839M (frozen encoder) | LoRA r=16 on classifier head | ATEPP 250 | 10 |
| **C3** | Moonbeam 309M (full fine-tune) | — | ATEPP 250 | 5 (lower LR) |
| **C4** | Aria-MIDI self-supervised pretrain → transformer branch of B9 family | full fine-tune | ATEPP 250 | 30 (B9 schedule) |

Rationale:
- C1 + C2 test **frozen-encoder LoRA** — the cheapest, most-standard pretraining transfer.
- C3 tests **full fine-tune** in case LoRA is too constrained.
- C4 re-runs the prior-art transformer-with-pretraining path (`transformer_24key_pretrained.pt` showed 0.523 test MIREX on the pre-Phase-A pipeline but that number is not directly comparable; Phase A's corrections must be re-applied).

**Existing infrastructure (all in repo):**
- [`finetune_moonbeam_key_detection.py`](finetune_moonbeam_key_detection.py) — C1/C2/C3 launcher.
- [`pretrain_aria_midi.py`](pretrain_aria_midi.py) — C4 pretraining launcher.
- `Moonbeam MIDI Foundation Model/moonbeam_839M.pt` (1.7 GB), `moonbeam_309M.pt` (619 MB) — locally present.
- `aria-midi-v1-deduped-ext/data/` — ~371k MIDI files, pretraining corpus.

### 2b. Path B — Modulation-specialist loss (3 cells)

Keyed on B9's config (gru h=96, ENS weighting, causal, val-MIREX selection).

| Cell | Loss-weight schedule | Motivation |
|---|---|---|
| **C5** | ENS + composition-level upweight (w = 2.0 on `n_unique_keys ≥ 2`) | Simplest modulation upweight: double the gradient contribution from modulating training compositions. |
| **C6** | ENS + frame-level upweight (w = 3.0 on frames within ±T of any annotated key change) | Directly targets transition frames where classical fails. |
| **C7** | ENS + focal (γ=2.0) + frame-level upweight (C6) | Compound Path B approach — stacks the best of B10 (ens+focal edged modulating MIREX) with the upweight. |

Decision to enter Phase D on Path B only if C5/C6/C7 produces a MODULATION_WINNER per §4.

### 2c. Total budget

- Path A: 4 cells × 3 seeds = 12 runs. Rough wall-time: C1/C2 LoRA ~1 GPU-h each, C3 full fine-tune ~2 GPU-h, C4 (pretrain + fine-tune) ~4 GPU-h for Aria pretraining (once, shared) + 3×30min fine-tune = ~6 GPU-h. **Estimated Path A total: ~18–25 GPU-h.**
- Path B: 3 cells × 3 seeds = 9 runs. Each uses B9 training code with a loss-weight modification. **Estimated Path B total: ~14–18 GPU-h** (matches B9's wall-clock).
- **Combined: ~32–43 GPU-h.** Plausibly 3–5 Colab L4 sessions.

---

## 3. Fixed hyperparameters (all Phase C cells)

**Inherited from Phase B unless overridden explicitly in §2 tables:**

| Hyperparameter | Value | Notes |
|---|---|---|
| Manifest | `research_data/unified_training_manifest.json` | Same SHA as Phase B (`d1517ffccbbb3336`) |
| Label dirs | `wir_key_labels,dcml_key_labels,score_key_labels` | Same as Phase B (effective split = ATEPP 250/28/41) |
| Test set | 41 ATEPP compositions | Same as Phase B — frozen for paired comparison |
| Selection metric | `val_mirex` | Per pre-reg |
| Seeds | {20260309, 20260310, 20260311} | Same as Phase B |
| Causal enforcement | `--require-causal --deterministic` | Path A with full fine-tune: verify the Moonbeam encoder is causally usable (left-to-right token attention only) before claiming causal — else mark as "offline oracle" |
| Bootstrap B | 10,000 | Composition-level paired cluster bootstrap |
| Path A LoRA rank | r=16, α=32 | Per `finetune_moonbeam_key_detection.py` defaults |
| Path A LoRA learning rate | 1e-4 | Lower than B9's 1e-3 |
| Path A full-fine-tune LR | 5e-5 | Even lower |
| Path B LR / optimiser / scheduler | identical to B9 | Only the loss-weighting changes |

---

## 4. Success criteria (frozen outcome categories)

For EACH Phase C cell, a three-seed evaluation produces a verdict:

| Category | Criteria |
|---|---|
| **STRONG_WINNER** | Δ ≥ 0.015 vs **classical** (0.6201 plain) at p < 0.05 paired cluster bootstrap AND σ ≤ 0.015 |
| **MODULATION_WINNER** | Δ ≥ 0.015 vs **classical on the modulating subset** (9 comps, classical modu ≈ 0.4867 frame-weighted) at p < 0.05 paired cluster bootstrap |
| **TRANSFER_WINNER** | Δ ≥ 0.015 vs **B9 (0.5235 plain)** at p < 0.05 paired cluster bootstrap AND σ ≤ 0.015 |
| null | None of the above |

A single cell can hold multiple categories (e.g. STRONG_WINNER ∧ TRANSFER_WINNER). **B9's Phase B result (0.5235 plain) is the primary neural comparator;** classical (0.6201 aggregate, 0.4867 modulating) remains the strong baseline.

### 4.1 Go/no-go decision rules

- **If any Path A cell is a STRONG_WINNER:** H1 confirmed — pretraining closes the gap to classical. Phase C ends with deployable neural system. Proceed to Phase D (error analysis) using that cell's best seed.
- **If any Path B cell is a MODULATION_WINNER:** H2 confirmed — frame-level neural prediction beats classical on modulating pieces. This is the publishable Paper-1 claim. Proceed to Phase D using Path B's winner.
- **If any cell is TRANSFER_WINNER but not STRONG/MODULATION:** document as "architectural progress without deployment improvement"; decide in Phase D whether to ship or continue experimentation.
- **If no cell meets any category:** declare **pretraining ceiling** and **modulation ceiling** — the thesis contribution reframes as the rigorous negative-result + ENS-weighting + honest classical-dominance finding from Phase A/B.

Per pre-reg §6 of Phase B, significance threshold = two-sided p < 0.05; minimum meaningful effect = Δ = 0.015; stability σ ≤ 0.015.

---

## 5. Datasets and splits

- **Same manifest-effective split as Phase A and B: 250 train / 28 val / 41 test ATEPP compositions.**
- **Path A pretraining data** (shared, not in the 250):
  - Moonbeam: the pretrained checkpoints are already weights from external pretraining. No additional pretraining data required.
  - Aria (C4): `aria-midi-v1-deduped-ext/data/` (~371k MIDI files). Filter to classical+piano per [`pretrain_aria_midi.py`](pretrain_aria_midi.py) defaults. Pretraining runs once and produces a checkpoint reused across the 3 fine-tune seeds.
- **Leakage check before Phase C:** verify that none of the 41 test compositions are duplicated in the Aria pretraining corpus (by piece_id + composer cross-reference with ATEPP). Aria is pop-leaning so overlap is unlikely, but verify and persist the check as `research_data/phaseC_leakage_check.json`.

---

## 6. Metrics and reporting (per cell, per seed)

Identical to Phase B §5 requirements:

1. Test MIREX frame-weighted **and** composition-equal.
2. Test MIREX on **mono-tonal** (32 comps) and **modulating** (9 comps) subsets separately plus aggregate.
3. Class-rebalanced auxiliary MIREX (24 classes, weight 1/24 each).
4. Paired bootstrap CI against **B9** AND **classical**, composition-level, B=10,000.
5. Per-class accuracy with σ across 3 seeds.
6. Causality block (bidirectional flag + causal-only check).
7. **Path A cells additionally report:** effective parameter count after LoRA, wall-clock / $ cost, and whether the pretrained base is causally usable at inference.

---

## 7. Comparator set (frozen — no post-hoc addition)

| Comparator | Value | Source |
|---|---:|---|
| A1-corrected (causal GRU, sqrt) | 0.4984 | Phase A consolidation |
| **B9 (gru 96 ens)** — primary | **0.5235 plain / 0.5345 +HMM** | Phase B consolidation |
| B10 (gru 96 ens+focal) — stability alt | 0.5224 / 0.5341 | Phase B |
| Classical (KK+Temperley+AS) — strong baseline | 0.6201 aggregate / 0.4867 modu | Phase A Track 1 |
| Classical + HMM-of-neural blend | 0.6190 (ens output) | Phase A Track 1 |
| B9's predictions JSONs (for paired test) | `research_data_041826/phase_b_evals_2026-04-17/B9_seed*_predictions.json` | Drive-resident |

---

## 8. Execution order

1. **Phase C preflight (2026-04-19):** verify all 3 Moonbeam checkpoints + aria data on Drive, upload as `phase_c_delta_2026-04-19.zip` if needed, update Cell 0's overlay logic.
2. **Leakage check (M5 week 1):** cross-reference 41 test comp IDs against Aria metadata. Commit `phaseC_leakage_check.json` before any training.
3. **Path B cells C5/C6/C7 (M5 week 1–2):** fastest — reuses B9's training code with one loss-weight modification per cell. Produces first Phase C result to check pipeline.
4. **Path A cells C1/C2 LoRA (M5 week 2):** frozen-encoder LoRA on the two Moonbeam sizes.
5. **Path A cells C3 full fine-tune (M5 week 3):** if C1/C2 show any TRANSFER_WINNER trend.
6. **Path A cell C4 Aria pretrain + fine-tune (M6 week 1–2):** most expensive; run only if Paths A (LoRA) + B both fail.
7. **Phase C consolidation (M6 week 2):** `phaseC_consolidation_2026-04-XX.md`.

Paths can run in parallel if compute allows.

---

## 9. Persistence and provenance

Every Phase C run JSON must include:

- `phase_c_cell_id`, `seed`, `git_commit`, `manifest_sha256` (`d1517ffccbbb3336`), `phase_c_pre_reg_commit`, `deterministic_flag`.
- `test_metrics` (aggregate + stratified), `bootstrap_ci` vs B9 AND vs classical, `per_composition_mirex`, `class_metrics`.
- `causality` block from Phase A guardrail (bidirectional? causal_only flag? oracle?).
- For Path A: `base_checkpoint_sha256`, `lora_config`, `pretraining_corpus_sha256`.
- For Path B: `loss_schedule_specification` (exact formula + modulating composition IDs used).
- `val_metrics_per_epoch` for early-stopping provenance.

Per Phase B rule: **no headline number ships without a committed result JSON containing all of the above.**

---

## 10. Amendments log

(Empty until Phase C is running. Any deviation from §2–§9 gets a dated entry with rationale and commit link.)

---

## 11. Out-of-scope for Phase C

- Audio-domain baselines (Chordino, NNLS-Chroma) — remain in Phase E.
- Extended test set (20–40 held-out ATEPP pieces) — remain in Phase E.
- Inference-latency benchmarking — remain in Phase E.
- New datasets beyond ATEPP/WiR/DCML — remain in Phase F.
- Multi-task learning (key + chord + tonicization jointly) — remain in Phase F.

These are explicitly deferred; Phase C is scoped to pretraining transfer + modulation-specialist loss only, to keep scope managable.
