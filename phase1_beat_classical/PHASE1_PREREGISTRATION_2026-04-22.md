# Phase I — "Beat Classical" Pre-registration & Progress Report

**Date:** 2026-04-22
**Scope:** Cumulative ablation of three techniques from
`BEAT_CLASSICAL_RESEARCH_PLAN_2026-04-22.md` §10 (Phase I): #6 deterministic
×12 transposition augmentation, #1 global pitch-class histogram feature,
and #2 multi-task joint key + chord head.
**Status as of this document:** **Scaffolding complete; not yet trained.**
Ready-to-run Colab pipeline committed. Training itself (~6 GPU-h on an L4)
is the user's next step.

---

## 1. Direct answer to the question "do we already have results?"

**No.** `BEAT_CLASSICAL_RESEARCH_PLAN_2026-04-22.md` is a *research plan*
— 12 candidate techniques ranked by expected lift, compute cost, and
risk. None of the 12 has been executed against the B9 codebase yet;
the expected-lift ranges quoted there are informed estimates, not
measurements. The only experimental results on "beat-classical" so far
are the Phase A / B / C experiments already in the thesis, which tested
a different set of interventions (architecture grid, loss design,
S-KEY pretraining) — all produced statistically null results.

This document initiates Phase I, the first cumulative ablation on
candidate techniques.

---

## 2. Hypotheses (pre-registered)

For each cumulative cell, H0 is "no change vs B9 5-seed baseline" and
H1 is "positive shift." The primary test is a paired cluster bootstrap
against B9 at the composition level (B = 10,000, CE convention). The
decision threshold is p < 0.05 with Δ ≥ +0.015 — the same criterion
used for the Phase C TRANSFER_WINNER category.

| Cell | Name | Hypothesised Δ vs B9 5-seed (FW) | Primary contrast |
|---|---|---|---|
| T6 | ×12 deterministic transposition | +0.02 to +0.05 | T6 − B9_5seed (CE paired) |
| T6 + T1 | + global PCP feature | cumulative +0.05 to +0.15 | T6_T1 − B9_5seed (CE paired) |
| T6 + T1 + T2 | + multi-task chord head | cumulative +0.07 to +0.20 | T6_T1_T2 − B9_5seed (CE paired) |

The secondary contrast is against the classical 3-profile baseline
(FW = 0.6201), with the pre-registered publication threshold being a
positive CE Δ with p < 0.05. Meeting this threshold would be the first
symbolic-MIDI causal-neural result to beat the classical ensemble on
ATEPP-41.

## 3. Experimental design

### 3.1 Variants

Every Phase I variant is a minimal extension of the Phase B B9
architecture (HarmonicContextGRU, hidden = 96, causal, ENS β = 0.999,
val-MIREX selection, 30 epochs). Only the listed extensions are added.

| Variant | n_transpositions | use_global_pcp | use_chord_heads | Param count |
|---|---:|:-:|:-:|---:|
| BASELINE (for control) | 1 | False | False | 67,016 |
| T6 | 12 | False | False | 67,016 |
| T6 + T1 | 12 | True | False | 70,376 |
| T6 + T1 + T2 | 12 | True | True | 71,650 |

The BASELINE row exists as a sanity check — if it reproduces the
B9 5-seed headline (0.5208 ± 0.0044) then the Phase I pipeline is
consistent with the Phase B training surface. Optional in the first
run.

### 3.2 Data

* **Training**: the Phase I extended manifest
  `research_data/unified_training_manifest_phase1.json` (built by
  `prepare_phase1_manifest.py`), which appends the 141 Block-B.3
  DCML Strategy A pieces (with chord labels) as additional `train`
  entries.  **The 41-composition ATEPP test split is unchanged.**
* **Validation**: identical to B9 (28 ATEPP pieces, manifest-frozen).
* **Test**: identical to B9 (41-composition ATEPP manifest test).

### 3.3 Hyperparameters (frozen)

Identical to B9 unless listed otherwise:

| Hyperparameter | Value |
|---|---|
| hidden_size | 96 |
| batch_size | 8 |
| learning_rate | 1e-3 |
| epochs | 30 |
| warmup_epochs | 3 |
| patience | 10 |
| weight_decay | 0.01 |
| grad_clip | 1.0 |
| deterministic | True |
| seeds | {20260412, 20260413, 20260414} |

**Chord-loss weight** (T2): λ = 0.3 per chord head (root + quality),
making the chord contribution equal to 0.15 × key-loss magnitude at
equal CE-magnitude. A sensitivity sweep on λ is deferred unless the
primary T2 result is null.

### 3.4 Seeds

Fresh seeds {20260412, 20260413, 20260414} avoid collision with the
Phase B / B.1 seeds {20260309–20260313}. Three seeds per cell is a
pragmatic baseline; if any cell's σ exceeds 0.015 we extend to five.

### 3.5 Protocol

* Per-seed eval JSON is written to `phase1_beat_classical/runs/`.
* After all 9 runs complete (3 cells × 3 seeds), the aggregator
  (`aggregate_phase1_results.py`) produces the headline table and
  paired bootstraps.
* No intermediate numbers are quoted before the full sweep completes.
* Colab wall-clock budget: ~30 min per run on L4 → ~4.5 GPU-h total.
  (Plus ~30 min × 3 seeds = 1.5 GPU-h for the optional BASELINE
  control row if the user elects to run it.)

## 4. Success criteria

| Outcome category | Criterion | Action |
|---|---|---|
| **CLASSICAL_BEATEN** | Any variant achieves Δ ≥ +0.005 vs classical CE at *p* < 0.05 | Draft first post-thesis paper immediately |
| **CLASSICAL_MATCHED** | Best variant's CE point estimate ≥ classical's, but p ≥ 0.05 | Add 2 more seeds (n=5) to tighten CIs; then repeat |
| **PARTIAL** | Positive Δ vs B9 5-seed (p < 0.05) but Δ vs classical still negative | Publish as TRANSFER_WINNER-grade incremental paper |
| **NULL** | No cell clears either threshold | Proceed to Phase II (Technique #4 Aria pretrain) |

## 5. Infrastructure inventory (ready to run)

| File | Purpose | Status |
|---|---|---|
| `phase1_beat_classical/phase1_variants.py` | HarmonicContextGRUPhase1 (B9 backbone + gated PCP + chord heads); DCML-to-ATEPP key normaliser; chord-label extractor | ✓ smoke-tested (forward pass with dummy DCML piece produces correct-shape logits for key + chord_root + chord_quality) |
| `phase1_beat_classical/phase1_dataset.py` | Phase1Dataset (×12 deterministic expansion); collate_phase1_batch (adds global_pcp + chord labels + chord_mask) | ✓ smoke-tested |
| `phase1_beat_classical/train_phase1.py` | Single-variant training driver with CLI flags (--variant, --seed, …) | ✓ syntax-validated; not yet trained end-to-end |
| `phase1_beat_classical/prepare_phase1_manifest.py` | Build `unified_training_manifest_phase1.json` (base + 141 DCML entries) | ✓ executed; manifest has 2,047 entries (1,906 base + 141 DCML Strategy A) |
| `phase1_beat_classical/aggregate_phase1_results.py` | Aggregator; consumes eval JSONs; computes paired cluster bootstraps; writes markdown table + JSON | ✓ syntax-validated |
| `colab_phase1_beat_classical.py` | Colab runner; 3 variants × 3 seeds = 9 runs; auto-backup to Drive | ✓ ready to upload |

## 6. Reproducibility

Every script is deterministic under the listed seeds. The expected-
identical-from-both-ends guarantee is:

1. Re-running `prepare_phase1_manifest.py` produces an identical
   manifest (DCML corpus order is alphabetical, file enumeration is
   deterministic).
2. Re-running `train_phase1.py --variant X --seed S` yields the same
   checkpoint file and eval JSON (`--deterministic` flag sets CUDA
   backend).
3. Re-running `aggregate_phase1_results.py` on the same runs folder
   yields the identical output JSON and markdown.

Post-execution, commit the eval JSONs under version control so the
paper can cite the specific computation.

## 7. Colab execution plan (user-facing)

```bash
# 1. Pack and upload the project (same zip layout as the B9 5-seed extension)
cd /Users/ruisu/Desktop/ruisuphd/prototype090326AI-functions
zip -r phase1_2026-04-22.zip . \
    -x '.venv/*' 'ATEPP-1.2/*' '*.pyc' '__pycache__/*' \
       'research_data_041826/*' 'Moonbeam*' 'aria-midi-v1-deduped-ext/*' \
       'PianoBart-main/*' 'BACHI*' 'justkeydding-master/*' \
       '*.mp3' '*.zip' '*.ipynb' \
       'phase_a_seeds_2026-04-14/*' 'phase_b_*/*' 'phase_c_*/*' \
       'phase1_beat_classical/runs/*'
# Upload to Drive → My Drive/PhD/phase1_2026-04-22.zip

# 2. In Colab (L4 recommended; ~6 GPU-h)
from google.colab import drive
drive.mount('/content/drive')
!cd /content && rm -rf project && unzip -q \
    /content/drive/MyDrive/PhD/phase1_2026-04-22.zip -d project
!pip install torch numpy -q
!cd /content/project && python phase1_beat_classical/prepare_phase1_manifest.py
!cd /content/project && python colab_phase1_beat_classical.py

# 3. Back in this environment
# Sync Drive/PhD/phase1_beat_classical_2026-04-22/ to local phase1_beat_classical/runs/
python phase1_beat_classical/aggregate_phase1_results.py
```

After aggregation completes, `phase1_results_2026-04-22.md` contains
the primary table + verdict, and `phase1_results_2026-04-22.json`
contains the machine-readable contrasts.

## 8. What is NOT yet done (explicitly)

1. **Training itself**: 9 Colab L4 runs = ~6 GPU-h wall-clock are
   required before any numerical claim can be made about Phase I.
2. **5-seed extension** (from 3 seeds to 5): contingent on whether any
   cell's σ exceeds 0.015 after 3 seeds (see §4).
3. **Phase II (Aria pretrain)**: covered by
   `BEAT_CLASSICAL_RESEARCH_PLAN_2026-04-22.md` Technique #4; will be
   kicked off only if Phase I does not reach the CLASSICAL_BEATEN
   category.
4. **Statistical rigour for the cumulative claim**: the headline
   comparison is the sequential contrast (T6 → T6+T1 → T6+T1+T2),
   which should be reported with Bonferroni-corrected p-values for the
   three cumulative tests (corrected α = 0.0167). This is included in
   `aggregate_phase1_results.py`'s output.

## 9. Honest risk register

Three ways Phase I could plausibly fail; none of them invalidate the
thesis, and each is addressed either in the fallback plan or in
Phase II.

1. **Data-augmentation saturation (T6).** The current ±5 random
   augmentation already samples 12 unique shifts during training; the
   ×12 deterministic variant may lift the effective training signal
   by only a fraction of what one-transposition-per-piece-per-epoch
   would imply, because note buckets (delta, duration, velocity) are
   invariant to transposition. Fallback: proceed directly to T6+T1
   (the global PCP feature is independent of augmentation strategy).
2. **Global PCP marginal (T1).** B9 already processes pitch-class
   information through the embedding layer; a separate 12-bin
   histogram could be redundant if the GRU has already learned to
   accumulate it. Fallback: the T1 mechanism is additive, so the
   fallback is simply to proceed to T2 regardless of T1's marginal
   lift.
3. **DCML-chord-label mismatch (T2).** DCML's Roman-numeral labels
   are relative to a local-key stacktrace; the chord root we derive
   in `extract_chord_labels_from_dcml` assumes the local_is_minor
   flag resolves correctly (which it does in Block B.3's parser output).
   Any residual mismatch shows up as a chord-root-head that cannot
   converge below random. Fallback: set λ_chord = 0 (effectively
   disabling T2) and report T6+T1 as the best.

---

## 10. Summary for the supervisor

> **Phase I pipeline committed; ready to run on Colab.** The three-
> technique cumulative ablation (×12 augmentation + global-PCP
> feature + multi-task chord head) is implemented as a minimal
> extension of the deployable B9, uses the frozen ATEPP-41 test
> split, and requires ~6 GPU-h of Colab L4 time. Pre-registration
> above commits the hypotheses, seeds, and outcome-category decision
> rules. Post-training, `aggregate_phase1_results.py` produces the
> paired cluster bootstrap table and a verdict under the four outcome
> categories (CLASSICAL_BEATEN / CLASSICAL_MATCHED / PARTIAL / NULL).
> Supervisor input sought on: whether λ_chord = 0.3 is acceptable for
> the T2 chord-head weight, and whether 3 seeds (rather than 5) is
> acceptable for Phase I's first pass.
