# Phase C Path A — Viability Analysis and Research Redirection

**Date:** 2026-04-19
**Status:** Research pause. Decision required before further GPU expenditure.
**Branch:** `main` (after commit `c178c40` — Moonbeam scripts landed; no training run completed yet)
**Context:** Five consecutive Colab integration failures on Moonbeam foundation-model transfer. User requested a pause and a rigorous re-analysis of whether the current research path is viable.

---

## 1. Executive summary

**Continuing the Moonbeam integration path is no longer the scientifically rational use of remaining compute.** Each fix reveals another infrastructure gap. Meanwhile, **the project already contains a self-contained, working pretraining pipeline** (`pretrain_symbolic_key.py` + `pretrain_aria_midi.py` → `SymbolicKeyTransformer` + `train_harmonic_context_model.py --pretrained-checkpoint`) that tests the same scientific hypothesis (H1: data-limited → pretraining transfer closes the classical gap) **without any external-model integration cost**.

**Prior (pre-audit) evidence is not encouraging either:** the existing `transformer_24key_pretrained_eval.json` shows the project's own S-KEY-pretrained transformer landed at test MIREX = 0.5230 vs no-pretrain at 0.5206 — **+0.0024, a null-sized lift** (on the pre-audit evaluation pipeline, so numbers aren't definitive but are indicative).

**Three options, ranked by research value per GPU-hour:**

| # | Option | GPU cost | Risk | Expected ceiling |
|---|---|---|---|---|
| A | **Re-evaluate existing S-KEY-pretrained ATEPP variants** on the audited pipeline (Phase B Cell 6/7/8) | ~1 GPU-h | Low | Confirm or disconfirm the +0.002 lift with proper paired bootstrap |
| B | **Run Aria-MIDI pretraining** (371k files, 1500× ATEPP) + 3-seed fine-tune | ~15–25 GPU-h | Medium | If pretraining transfer is real, this is where it shows. |
| C | **Accept Phase A/B/C-PathB as complete thesis** and pivot to Phase D (error analysis / deployment benchmarking) | 0 GPU-h | Lowest | Current results support a defensible PhD |

**The Moonbeam path is effectively off the table** unless a third party releases a clean pip-installable version or we write a bespoke adapter that's out of scope.

---

## 2. What we tried with Moonbeam — a post-mortem

Five integration attempts, each uncovering a deeper blocker:

| Attempt | Error | Root cause |
|---|---|---|
| 1. Standard `subprocess.check_call` training | Generic exit code 1 | Stderr suppressed |
| 2. Stderr-captured launch | `HFValidationError: Repo id must be…` | Newer pip `transformers` rejects filepaths in `LlamaConfig.from_pretrained(...)` |
| 3. `pip install Moonbeam/transformers_minimal/` | `returned non-zero exit status 1` | Moonbeam's `pyproject.toml` has only `[tool.ruff]`/`[tool.pytest]` — **no `[build-system]` / `[project]` section**; pip can't build it |
| 4. Physically swap `site-packages/transformers` with Moonbeam's fork | peft import fails: `No module named 'transformers.models.bloom'` | Moonbeam's fork is a stripped subset; peft depends on BloomPreTrainedModel, GPT2PreTrainedModel, etc. that are absent |
| 5. Selective overlay (only `models/llama/*.py`) | `ModuleNotFoundError: No module named 'transformers.models.llama.pip_bak'` | My `shutil.copytree(PIP_LLAMA, LLAMA + '.pip_bak')` created a sibling directory inside `models/` that pip-transformers' lazy module loader tries to import. Also `transformers==4.41.2` downgrade failed because `tokenizers==0.22.2` is pinned by Colab's system packages. |

**Each attempt consumed 5–15 min of Colab setup + analysis time**, in addition to the base 2.9 GB zip re-extract on runtime restart. We are five attempts deep and **not a single training step has executed**.

**The problem is structural:**
- Moonbeam's transformers fork is intentionally minimal — designed for self-contained replication of their paper, not integration into larger pipelines.
- It was built against `transformers 4.41.0.dev0`; Colab's `transformers` (≥ 4.46) has moved on.
- peft (which we need for LoRA) pulls in modules (bloom, bert, t5) that Moonbeam's fork doesn't ship.
- Colab's system-package pins (`tokenizers == 0.22.2`) prevent downgrading `transformers` to 4.41 without breaking other things.

A clean fix would require either:
- (i) Building a new buildable package from Moonbeam's sources (add `[build-system]` to `pyproject.toml`, resolve pinning conflicts) — multi-day engineering task.
- (ii) Writing a compact reimplementation of Moonbeam's forward pass on top of the current pip `transformers` — also multi-day.
- (iii) Patching the specific failure chain one-by-one (which is what we've been doing; diminishing returns).

**None of these are research work. They are tooling work that doesn't advance the thesis.**

---

## 3. What the project ALREADY has — the native alternative

Discovered during this viability analysis (had been overlooked in the Phase C pre-reg):

### 3.1 Pretraining infrastructure — already written, tested, and has outputs on disk

| Component | File | Status |
|---|---|---|
| **SymbolicKeyTransformer** architecture | `harmonic_context_model.py` | 381k params, causal, compatible with existing evaluate/HMM/ensemble scripts |
| **S-KEY pretraining on ATEPP** | `pretrain_symbolic_key.py` | Implements Kong et al. (ICASSP 2025): equivariance + mode + batch-balance loss. |
| **S-KEY pretraining on Aria-MIDI** | `pretrain_aria_midi.py` | Adapts S-KEY to Aria's 371k-file recursive structure. **Not yet run.** |
| **Pretrained checkpoint loader** | `train_harmonic_context_model.py:58` | Already supports `--pretrained-checkpoint` flag + `--model-type transformer`. Loads state-dict into `SymbolicKeyTransformer`. |
| **Existing S-KEY variants on disk** | `research_data/symbolic_key_pretrained_*.pt` (7 variants) | `_default`, `_equal`, `_equiv-only`, `_high-mode`, `_low-batch`, `_mode-only`, `_equiv-only` — appears to be a prior ablation study over S-KEY hyperparameters. All are 1.5 MB each, pretrained but not yet evaluated on the audited pipeline. |
| **Transformer eval JSONs on disk** | `research_data/transformer_24key_{nopretrain,pretrained}_eval.json` | Pre-audit numbers: nopretrain test_mirex = 0.5206, pretrained = 0.5230 (Δ +0.0024, essentially null). |

### 3.2 What this means for Phase C Path A

We can test H1 (pretraining transfer) **without any Moonbeam integration** by:

| New Cell ID | Config | GPU cost | Tests |
|---|---|---|---|
| **C-A1** | Evaluate each of the 7 existing `symbolic_key_pretrained_*.pt` on audited pipeline (just runs `evaluate_harmonic_context_model.py` per checkpoint) | ~0.5 GPU-h | "Does the existing S-KEY ATEPP pretraining provide any lift on the corrected evaluation?" |
| **C-A2** | Fine-tune `SymbolicKeyTransformer` with ONE winning S-KEY checkpoint → 3 seeds using Phase B's B9 protocol (`--weight-mode ens --selection-metric val_mirex`) | ~3 GPU-h | "Does S-KEY pretraining + current best fine-tune recipe beat B9?" |
| **C-A3** | Aria-MIDI pretraining on 371k files (~10–15 GPU-h) → fine-tune 3 seeds | ~15–20 GPU-h | "Does pretraining at real scale (1500× ATEPP) close the classical gap?" |

**This is the scientifically correct Phase C Path A.** Same hypothesis, same downstream evaluation, same paired-bootstrap comparators (B9 + classical), no integration hell.

---

## 4. Prior-evidence analysis — what the pre-audit transformer numbers tell us

| Model | Pre-audit test MIREX | Pre-audit val MIREX |
|---|---:|---:|
| transformer 24-key, **no pretrain** | 0.5206 | 0.4875 |
| transformer 24-key, **S-KEY pretrained** | 0.5230 | 0.4787 |

**Observations:**

1. **Difference is +0.0024 on test, *negative* 0.0088 on val.** Essentially indistinguishable from noise at single-seed.
2. **Both are close to B9's 0.5235 plain MIREX.** The pre-audit transformer numbers roughly match the audited GRU numbers — modest evidence that the S-KEY pretraining on ATEPP didn't meaningfully change the architecture's asymptotic performance.
3. **Pre-audit pipeline had multiple known bugs** (label-dir resolution, composition split confusion — see Phase A consolidation §1). The absolute numbers aren't definitive, but the **relative comparison** (pretrained vs no-pretrain, with the same bugs affecting both) is likely approximately preserved.

**Conclusion from prior evidence:** S-KEY pretraining on ATEPP provided **minimal-to-zero lift** over no-pretraining. This doesn't rule out Aria pretraining (1500× larger corpus) providing real lift, but it lowers the probability. The data-limited hypothesis H1 is not strongly supported by the existing evidence we already have.

---

## 5. Updated research viability assessment

### 5.1 Probability estimates (my postdoc-level priors)

| Hypothesis | Prior probability of closing ≥ 0.015 gap to classical | Reasoning |
|---|---:|---|
| S-KEY ATEPP pretraining → B9-protocol fine-tune helps | **< 10 %** | Pre-audit evidence shows Δ ≈ 0. |
| Aria-MIDI pretraining → fine-tune helps | **15–30 %** | Large corpus scaling is untested; Moonbeam's 81.6k pretraining is a data point (if it worked, Moonbeam would already publish symbolic-key-detection SOTA — they don't). Aria's 371k is larger but Aria-MIDI is heavily pop-oriented; ATEPP test set is classical piano. Domain shift may limit transfer. |
| Moonbeam pretraining → fine-tune helps IF integrated | **30–50 %** | Strongest pretraining but inaccessible. |

### 5.2 Expected-value-per-GPU-hour comparison

| Option | Cost (GPU-h) | P(success) | EV of headline lift if successful | EV per GPU-h |
|---|---:|---:|---:|---:|
| Moonbeam (continue debugging) | 15+ (integration) + 4 (training) | **10 %** (given integration hurdles) | +0.03 | **~0.0001** |
| Evaluate existing S-KEY variants on audited pipeline | 1 | 80 % (just needs eval runs) | Disconfirms/confirms H1 cheaply | **~0.01 confirmation rate per GPU-h** |
| Aria pretrain + fine-tune | 20 | 20 % | +0.025 | **~0.00025** |
| Accept current, shift to Phase D | 0 | N/A | Thesis defensible on existing findings | Highest per-hour (infinite) |

### 5.3 Thesis narrative strength, with vs without Path A

| Path A outcome | Thesis narrative |
|---|---|
| STRONG_WINNER | "Pretraining transfer breaks the classical ceiling on symbolic key detection." Strong Paper 1 headline. |
| TRANSFER_WINNER (beats B9 but not classical) | "Pretraining transfer meaningfully improves the causal-neural baseline but does not close the gap to classical." Useful architectural finding. |
| Null on Path A as well | **"Null + ceiling" across all three hypotheses (architecture, loss design, pretraining transfer). The classical ceiling is a property of the task at this data scale, not an artefact of any particular neural method we tried."** This is a **rigorous negative result worth publishing** — the MIR field benefits from knowing this. |
| Abandon Path A without running | Thesis still has Phase A/B/C-PathB, ENS-weighting contribution, PCP null, dual-baseline framework. **"We established the current ceiling and four supporting findings; pretraining transfer is a promising direction for future work."** Defensible but slightly softer. |

**A top postdoc would argue:** a thoroughly-executed null result on Path A is scientifically MORE valuable than an abandoned Path A. If we can run Path A CHEAPLY and get the answer, we should. If Path A requires expensive infrastructure work just to start, the cost may not be justified.

---

## 6. Recommended next steps (decision tree)

```
                    [DECISION POINT]
                         │
              ┌──────────┴──────────┐
              │                     │
   Do you want to pursue      Skip Path A, go
   pretraining transfer?      straight to Phase D
              │                     │
              │                   (error analysis,
   ┌──────────┴──────────┐         deployment bench,
   │                     │          thesis writeup)
  YES, cheaply          YES, at scale
   │                     │
   C-A1: Evaluate the    C-A3: Aria pretraining
   7 existing S-KEY      on 371k MIDI files
   pretrained variants   (15–20 GPU-h) →
   on audited pipeline   fine-tune 3 seeds →
   (~1 GPU-h)            paired bootstrap
   │                     │
   ├─ Any variant beats  ├─ Beats B9 at Δ≥0.015?
   │  B9?                │  YES → STRONG/TRANSFER_WINNER
   │  YES → proceed to   │  NO  → "Null + ceiling"
   │  C-A2 fine-tune     │       outcome per pre-reg §4
   │  (3 seeds, 3 GPU-h) │
   │  NO  → H1 on ATEPP  │
   │  disconfirmed       │
   │                     │
   └────────┬────────────┘
            │
   Write phaseC_consolidation with
   whichever outcome fired.
   Proceed to Phase D.
```

---

## 7. Questions I need answered before executing any of the above

1. **Is the thesis timeline hard-deadlined?** If you need to defend/submit within a few weeks, I'd strongly recommend Option C (accept current, shift to Phase D). Phase C Path A is nice-to-have not need-to-have at this point.

2. **Do you have the ~20 GPU-h budget AND willingness to spend it on a 20–30 % probability of a meaningful lift?** (Path B Aria pretraining.) If yes, we launch. If no, we stick to the cheap Option A evaluation.

3. **Does your supervisor / committee value negative results?** If yes, "we tried pretraining transfer and it didn't close the gap" is a contribution. If your supervisor is expecting positive results only, we should be honest that the probability is moderate, not high.

4. **Are any of the existing `symbolic_key_pretrained_*.pt` variants meaningfully different?** These are seven files (_default, _equal, _equiv-only, _high-mode, _low-batch, _mode-only, _equiv-only) that look like a pre-Phase-A S-KEY hyperparameter ablation. I'd like to confirm you remember what each variant was (or have an older planning doc) so I know which one to evaluate first.

5. **Moonbeam: truly abandon, or wait for someone to fix upstream?** If you want to revisit Moonbeam after thesis submission as "future work," that's a clean handoff. If you want to keep trying now, I can estimate how many more hours it'd take (my estimate: 4–8 h of focused Colab debugging + possibly writing a custom package wrapper).

---

## 8. Concrete actions I recommend in Auto mode

**If you want the fastest, lowest-risk path forward** (my top recommendation):

### Step 1 (tonight or tomorrow, ~1 GPU-h on Colab)

Build a small Colab notebook that:
- Pulls each `symbolic_key_pretrained_*.pt` from Drive
- Fine-tunes `SymbolicKeyTransformer` with B9's protocol for **1 seed** (20260309) × 10 epochs (fast smoke check)
- Evaluates on the audited pipeline
- Reports whether ANY variant beats B9 by Δ ≥ 0.005 (a loose screen) in a single-seed comparison

**Decision gate after Step 1:**
- **If any variant screens positive** (Δ ≥ 0.005 vs B9): expand to 3 seeds, proper Phase C Path A cell C-A1. Full paired bootstrap.
- **If all screen negative**: S-KEY ATEPP pretraining confirmed ineffective on the audited pipeline. Either:
  - (a) Proceed to Step 2 (Aria pretraining) — tests the scale hypothesis.
  - (b) Close Path A, accept "null + ceiling," go to Phase D.

### Step 2 (only if Step 1 screens negative AND you want to test at scale, ~15–20 GPU-h)

Run `pretrain_aria_midi.py` on 371k Aria MIDI files (needs upload or HF fetch). Then fine-tune B9-protocol × 3 seeds. Evaluate with paired bootstrap. Consolidate.

### Step 3 (regardless of Step 1/2 outcome)

Write `phaseC_consolidation_2026-04-XX.md` with whichever Path A outcome fired. Announce Phase C complete. Move to Phase D.

---

## 9. Honest disclosure

I have been iterating on Colab fixes aggressively. Each fix cost you ~5–10 min of cell execution + my analysis time, plus potential GPU-h on the failing runs. A top postdoc reviewing this transcript would note that **I should have paused and reassessed after the third integration failure** rather than the fifth. I'm doing that now, but the lesson is: when infrastructure work dominates research work, that's a signal to rethink the path.

This document is that reassessment. The decision is yours — but my professional recommendation is **Option A + evaluate existing S-KEY variants first, then decide on Aria based on that signal**.

---

## 10. Where this document lives

Path: `research_data/phaseC_path_viability_2026-04-19.md` (this file)
Companion paired-bootstrap scripts and summary JSONs: `research_data/phaseC_results_2026-04-18/`
Updated pre-registration: `research_data/phaseC_preregistration.md` (§11 needs another amendment after you decide)
Related commits: `698520d` → `99d02f7` → `2ed7981` → `6d35294` → `c178c40` (all Phase B/C artefacts).

No code changes have been made in this analysis — the Moonbeam scripts from `c178c40` remain in the tree, the selective-overlay experiments happened entirely in Colab's ephemeral environment.
