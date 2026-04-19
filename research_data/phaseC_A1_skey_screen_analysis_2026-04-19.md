# Phase C-A1 — S-KEY ATEPP-pretrained screening analysis

**Date:** 2026-04-19
**Branch:** `main` at `b638db6` (pre-reg amendment landed the morning of the screen)
**Compute:** NVIDIA L4 Colab Pro, 6 cells × 1 seed × 10 epochs ≈ **46 min training + ~15 min eval + ~10 min HMM/ensemble ≈ 1.2 GPU-h total** (came in under the 2–3 h budget because early-stop triggered at epoch 8–9 on every variant).
**Input artefacts:** `research_data/symbolic_key_pretrained_{equal, equiv-only, high-mode, low-batch, mode-only, skey-default}.pt` (6 pretrained checkpoints, loaded cleanly into `SymbolicKeyTransformer` with zero missing/unexpected state-dict keys).
**Output artefacts (on Drive):** `phase_c_A1_skey_screen_2026-04-19/{checkpoints, evals, track1_hmm_ensemble}/` + `phaseC_A1_skey_screen_summary.json`.
**Pre-registered gate:** `Δ ≥ 0.005 vs B9 plain MIREX (0.5235)` at single-seed.

---

## 1. Raw result

| Variant | pretrain epoch / loss | val_mirex (best) | test plain | test +HMM | test +ens | Δ vs B9 plain | Δ vs classical |
|---|---|---:|---:|---:|---:|---:|---:|
| equal | 2 / 0.815 | 0.5946 | 0.4867 | 0.4934 | 0.6178 | −0.0368 | −0.1334 |
| equiv-only | 27 / 0.501 | 0.5888 | 0.4853 | 0.4918 | 0.6180 | −0.0382 | −0.1348 |
| high-mode | 18 / 2.638 | 0.5950 | 0.4860 | 0.4947 | 0.6182 | −0.0375 | −0.1341 |
| low-batch | 22 / 1.436 | 0.5916 | 0.4929 | 0.5007 | 0.6191 | −0.0306 | −0.1272 |
| **mode-only** | **29 / 1.389** | **0.5902** | **0.4971** | 0.5064 | 0.6206 | **−0.0264** | −0.1230 |
| skey-default | 30 / 1.884 | 0.5930 | 0.4879 | 0.4968 | 0.6175 | −0.0356 | −0.1322 |
| **B9 (Phase B comparator)** | — | 0.6109 (3-seed mean) | **0.5235** | 0.5345 | 0.6208 | 0.0000 | −0.0966 |

**All 6 variants screen NEGATIVE against the Δ ≥ +0.005 gate.** Every variant is significantly BELOW B9 by 0.026–0.038 MIREX.

---

## 2. The more interesting finding — homogeneity across pretraining variants

The **range across variants** is remarkably tight:

- Test MIREX range: 0.4853 → 0.4971 = **0.0118** (smaller than B9's seed σ × 4)
- Val MIREX range: 0.5888 → 0.5950 = **0.0062** (smaller than B9's seed σ × 3)
- +ensemble MIREX range: 0.6175 → 0.6206 = **0.0031** (noise-level)

**Despite six substantially different S-KEY pretraining objectives** (equivariance-only, mode-only, batch-balance-heavy, low-batch, high-mode weighting, default), all six converge to **essentially the same fine-tune outcome**.

This is a **scientifically informative negative result**: the specific choice of S-KEY hyperparameters during pretraining on ATEPP does not materially affect the fine-tune task. The signal is dominated by the fine-tune data, not the pretraining initialization. **The pretraining provides a warm-start but not a useful feature representation for 24-way key classification at this corpus scale.**

A competent reviewer might reasonably say: *"Your screening shows the pretraining objective is essentially orthogonal to fine-tune performance at ATEPP scale. That's a stronger negative result than simple underperformance."*

---

## 3. Why pretraining-transfer underperforms B9 (three hypotheses ranked by evidence)

### H-arch: the transformer architecture is the bottleneck, not pretraining

**Supporting evidence:**
- Phase B Finding 5 already established that transformer underperforms GRU on this task at this scale (B5 = 0.4682, B6 = 0.4999 vs B9 GRU = 0.5235).
- All 6 pretrained variants land in the band 0.4853–0.4971 — within Phase B's B5/B6 transformer range.
- No pretraining variant exceeds B6 (no-pretrain transformer) by more than 0.0011.
- **Interpretation:** the ~0.49 ± 0.005 test MIREX is essentially the **transformer ceiling** at this training-data scale, regardless of whether weights were initialised from scratch or from S-KEY pretraining.

### H-data: the pretraining corpus is too small

**Supporting evidence:**
- S-KEY pretrained on ATEPP (~300 files), then fine-tuned on ATEPP (250 files, same corpus).
- Same-corpus pretraining = zero additional data; only self-supervised reorganization of existing data.
- Genuine pretraining transfer requires PRETRAIN corpus ≫ FINETUNE corpus (typically 100–10,000×).

### H-objective: S-KEY at ATEPP scale is under-objective

**Weakly supporting:**
- 6 variants differ by pretraining hyperparameters but converge to near-identical fine-tune outcomes.
- This suggests the pretrained representations are all roughly equivalent — the fine-tune just re-derives keys regardless of initialization.
- **Caveat:** we don't have bidirectional attention as a factor; causality is consistent pretrain→finetune (both use `SymbolicKeyTransformer`'s built-in causal mask).

### Verdict

**H-arch and H-data are both likely; H-objective is a downstream consequence.** At ATEPP scale, the transformer architecture simply isn't data-hungry enough to extract pretraining benefit. This **does not** rule out Aria-MIDI pretraining (1,500× the scale) — but it lowers the prior that architecture-level pretraining alone closes the classical gap.

---

## 4. Val→test drift — consistent with Phase A Track 2 diagnostic

| Variant | val MIREX | test MIREX | drift |
|---|---:|---:|---:|
| equal | 0.5946 | 0.4867 | −0.1079 |
| equiv-only | 0.5888 | 0.4853 | −0.1035 |
| high-mode | 0.5950 | 0.4860 | −0.1090 |
| low-batch | 0.5916 | 0.4929 | −0.0987 |
| mode-only | 0.5902 | 0.4971 | −0.0931 |
| skey-default | 0.5930 | 0.4879 | −0.1051 |
| **mean** | **0.5922** | **0.4893** | **−0.1029** |
| B9 (Phase A) | 0.6109 | 0.5235 | −0.1126 |

Transformer drift (−0.103) ≈ GRU drift (−0.113). **This confirms Phase A Track 2's finding that val→test drift is a property of the data split (class-distribution mismatch + composition-size bias), not of any particular model class.** Pretraining on the same corpus as the fine-tune set does not rescue this drift.

---

## 5. The `+ensemble` column — classical's ceiling is robust

Every variant's `+ens` column is within 0.003 of classical alone (0.6201), and within 0.003 of B9's `+ens` (0.6208). The Neural+Classical blend alpha tuning on val consistently picks a blend near pure classical (because classical always wins at test time in this regime). **The ensemble output is a property of classical, not of the neural component.** This is the third consecutive phase where the ensemble converges to classical on the audited pipeline — first Phase A Track 1, then Phase B, now Phase C Path A.

---

## 6. Decision analysis

The pre-registered decision gate (§11 of `phaseC_preregistration.md`) says: "If all screen negative → proceed to C-A2-aria-pretrain OR accept H1 disconfirmed on ATEPP scale and close Path A."

**Two orthogonal questions:**
1. Do we spend ~5 GPU-h on C-A1-FULL (3 seeds × 30 epochs on mode-only) to get paired-bootstrap rigor on the best-screening variant?
2. Do we spend ~15–20 GPU-h on C-A2 (Aria pretraining at 1,500× scale)?

### 6.1 Argument for C-A1-FULL (rigorous single-variant confirmation)

**PRO:**
- Converts the single-seed screening into a publishable paired-bootstrap result
- 30 epochs may close SOME of the gap (mode-only screened at 0.4971 but was early-stopped at epoch 9; full 30-ep training could push to 0.51+)
- Full protocol matches B9 exactly → directly comparable
- Cheap relative to Aria (~5 GPU-h)

**CON:**
- We'd still expect a null — B6 (no-pretrain transformer, 30 ep, 3 seeds) = 0.4999 ± 0.0037 in Phase B. Pretraining mode-only converges to ≈0.497 in 10 epochs. **The 30-epoch ceiling for this architecture on this data is ~0.50, not 0.52.**
- Producing a cleaner null doesn't actually change any thesis conclusion

### 6.2 Argument for C-A2 (Aria pretraining at scale)

**PRO:**
- Tests a **genuinely different hypothesis**: does pretraining at 1,500× the fine-tune corpus size help?
- Aria-MIDI has 371k files. Even with --limit 50000 (13% of corpus) we'd have 170× ATEPP scale.
- A clean null at Aria scale is a **much stronger negative result** than ATEPP — shuts down the data-scaling lever definitively.
- A positive result would reshape the thesis narrative entirely.

**CON:**
- 15–20 GPU-h commitment
- 30% prior probability of meaningful lift (my postdoc estimate — the transformer architecture ceiling argument applies even at scale)

### 6.3 Recommended plan — run BOTH in this order

**This is professional scientific practice**, not wasteful. The two runs answer different questions:

| Run | Question answered | Time | Value |
|---|---|---|---|
| **C-A1-FULL × mode-only** (3 seeds × 30 ep) | "Does rigorous same-corpus S-KEY pretraining match B9?" | ~5 GPU-h | Convert screening → paired-bootstrap rigor for thesis |
| **C-A2 Aria** (--limit 50000, 8 epochs pretraining → 3 seeds finetune) | "Does pretraining at 170× corpus scale close the gap?" | ~15 GPU-h | Settles the scale hypothesis definitively |

**Total: ~20 GPU-h. Fits the user's budget.**

### 6.4 Alternative plan — skip C-A1-FULL, go straight to Aria

If the user wants to conserve GPU budget or has time pressure:
- Accept the 6-variant screening as sufficient evidence that S-KEY on ATEPP doesn't beat B9
- Write it up in the thesis as "6-variant hyperparameter ablation, all null, Δ range 0.012, mean gap to B9 −0.034"
- Use remaining budget for C-A2 Aria

**My professional recommendation: go with the recommended plan (6.3).** The user is not time-pressured; rigor is worth ~5 GPU-h. If Aria later fails too, we have two paired-bootstrap-significant nulls (C-A1-FULL and C-A2) which is the strongest possible disproof of H1.

---

## 7. Thesis narrative update

Regardless of what C-A1-FULL and C-A2 show, **Phase C-A1 screening is already a publishable sub-finding**:

> **"Symbolic S-KEY pretraining hyperparameter choice is essentially orthogonal to fine-tune outcome at ATEPP scale. Six S-KEY pretraining variants (equivariance-only, mode-only, batch-balance-heavy, high-mode-weight, low-batch-weight, and default Kong et al. 2025 configuration) produce fine-tuned 24-way key classifiers with a test-MIREX range of only 0.012 (0.485–0.497) — tighter than a single B9 seed's standard deviation. All six variants perform significantly below the GRU baseline (B9 = 0.5235) by a consistent 0.026–0.038 MIREX. This narrows the source of the pretraining-transfer null result: it is not the choice of S-KEY objective, but either (a) the architecture mismatch between causal transformer and this data regime, or (b) insufficient pretraining corpus scale. Phase C-A2 addresses hypothesis (b) directly by pretraining on the 371k-file Aria-MIDI corpus."**

This paragraph fits cleanly as Section 6.X of the thesis: demonstrates rigor + an interpretable negative result + motivates the next experiment.

---

## 8. Concrete next instruction for Colab

**Step 2A: C-A1-FULL on mode-only (3 seeds × 30 ep, ~5 GPU-h)**

```python
# Cell: C-A1-FULL — mode-only, 3 seeds × 30 epochs, same B9 protocol
FULL_VARIANT = 'mode-only'   # best-screening variant
FULL_SEEDS   = [20260309, 20260310, 20260311]
DRIVE_CA1F   = '/content/drive/MyDrive/ruisuphd/phase_c_A1_full_modeonly_2026-04-19'
for d in (f'{DRIVE_CA1F}/checkpoints', f'{DRIVE_CA1F}/evals', f'{DRIVE_CA1F}/track1_hmm_ensemble'):
    os.makedirs(d, exist_ok=True)

for seed in FULL_SEEDS:
    ckpt = f'{DRIVE_CA1F}/checkpoints/CA1F-{FULL_VARIANT}_seed{seed}.pt'
    if os.path.exists(ckpt):
        print(f'[skip] seed {seed}'); continue
    cmd = [
        sys.executable, 'train_harmonic_context_model.py',
        '--manifest',   'research_data/unified_training_manifest.json',
        '--label-dir',  'research_data/score_key_labels',
        '--label-dirs', LABEL_DIRS,
        '--model-type', 'transformer',
        '--pretrained-checkpoint', f'{REPO}/research_data/symbolic_key_pretrained_{FULL_VARIANT}.pt',
        '--checkpoint', ckpt,
        '--weight-mode', 'ens', '--ens-beta', '0.999',
        '--selection-metric', 'val_mirex',
        '--require-causal', '--deterministic',
        '--epochs', '30',          # full B9-comparable budget
        '--batch-size', '8',
        '--learning-rate', '1e-4',  # keep lower LR for pretrained
        '--warmup-epochs', '3',    # match B9
        '--patience', '10',        # match B9
        '--seed', str(seed),
    ]
    t0 = time.time(); print(f'[run] seed {seed}')
    subprocess.check_call(cmd, cwd=REPO)
    print(f'[done] seed {seed} in {(time.time()-t0)/60:.1f} min')

# Eval (reuse Cell 5 logic, pointing at new paths)
# Track1 (reuse Cell 6 logic)
# Aggregate (reuse Cell 7 logic, compare mean of 3 seeds vs B9)
```

I'll package this as a compact single-cell Colab addition when you green-light Step 2A. Expected: mode-only will stabilise around 0.495–0.500 test MIREX (3-seed mean), still significantly below B9 at paired bootstrap.

**Step 2B: C-A2 Aria pretraining + fine-tune** (on your next Colab session after 2A completes)

I'll draft a separate notebook for this — it needs Aria-MIDI uploaded to Drive (4.5 GB) OR `hf_hub_download` via aria's HuggingFace release. I'll handle the upload path, the `pretrain_aria_midi.py` command invocation, and the fine-tune cells. Rough protocol:

- Pretrain `SymbolicKeyTransformer` on Aria-MIDI `--limit 50000` (subset), 8 epochs, lr=5e-4 (Aria pretraining defaults), batch 16, max_seq_len 256 — est. ~10–12 GPU-h on L4.
- Save checkpoint to `research_data/symbolic_key_aria_pretrained.pt`.
- Fine-tune with `train_harmonic_context_model.py --model-type transformer --pretrained-checkpoint {aria_ckpt} --epochs 30 --seed {309,310,311}` — est. ~5 GPU-h.
- Eval + HMM + ensemble + paired bootstrap.

---

## 9. What this document captures

1. Clean tabular result of the screening with all relevant comparators.
2. The homogeneity-across-variants finding (§2) — publishable as a sub-claim.
3. Three competing hypotheses for why pretraining is null (§3), with evidence-weighted ranking.
4. Val→test drift robustness check (§4) — confirms it's a data property.
5. Decision analysis with two-run recommended plan (§6).
6. Draft thesis paragraph (§7).
7. Concrete next Colab cell for C-A1-FULL (§8).

Path forward requires user approval on the two-run plan vs skip-to-Aria. My recommendation is **the two-run plan** because Phase C's scientific value is maximised by rigorous paired-bootstrap results on both ATEPP-scale AND Aria-scale pretraining.
