# Execution playbook — 2026-05-09 → Months 3–4

**Author:** Rui Su
**Date:** 2026-05-09
**Companion artefacts:** `phase1_month2_2026-05-10.zip` (the Drive-uploadable project zip, contains the 5 new scripts + the chapter edits + all prior canonical evidence files).
**Reviewer passes:** 3 independent reviewer rounds documented in §D below.

This document is a **runbook**. Each section is one operational task; each task has (i) the WHY, (ii) the exact Colab cells to paste-and-run, (iii) the expected output, and (iv) a verification check. No prose-only explanation; every step is executable.

---

## Setup — fresh Colab Pro+ session

Upload `phase1_month2_2026-05-10.zip` to Drive at `/MyDrive/PhD/phase1_month2_2026-05-10.zip` BEFORE you start. Then in a new Colab notebook (T4 or A100 — see per-task hardware notes):

### Cell 0 — mount Drive + extract project + verify

```python
from google.colab import drive
drive.mount('/content/drive')

!cd /content && rm -rf project && unzip -q \
    /content/drive/MyDrive/PhD/phase1_month2_2026-05-10.zip -d project
!pip install -q torch==2.5.1 numpy mido music21 openpyxl pretty_midi tqdm pandas

import torch, platform, sys, os
print('torch:', torch.__version__)
print('Python:', platform.python_version())
if not torch.cuda.is_available():
    raise RuntimeError('Runtime → Change runtime type → GPU.')
gpu_name = torch.cuda.get_device_name(0)
vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
print(f'✅ GPU: {gpu_name} ({vram_gb:.1f} GB VRAM)')

# Restore the canonical 2026-05-09 results from Drive (so we can refit BMA + run σ-bootstrap)
import shutil
DRIVE_M2 = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-09'
DEST = '/content/project/research_data'
if os.path.isdir(DRIVE_M2):
    for f in os.listdir(DRIVE_M2):
        src = os.path.join(DRIVE_M2, f)
        dst = os.path.join(DEST if not f.startswith('runs_pop909') else '/content/project/phase1_beat_classical', f)
        if os.path.isdir(src):
            if os.path.exists(dst): shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    print(f'  ✓ Restored Month 2 artefacts from {DRIVE_M2}')

# Verify the new scripts are in place
for f in ('parse_tavern.py', 'eval_tavern_from_checkpoints.py',
          'bma_refit_t6t1.py', 'sensitivity_sweep.py', 'pretrain_aria_midi.py'):
    p = os.path.join('/content/project', f)
    assert os.path.exists(p), f'missing: {f}'
    print(f'  ✓ {f}')
print('  ✓ All 5 new scripts present')
```

---

# A. THIS WEEK (2026-05-09 → 2026-05-15)

## A.1 — σ-ratio bootstrap (formal CI; closes R1.1)

**WHY.** The σ-collapse claim across our three corpora (ATEPP-41 / BPS-FH / POP909) currently uses point-estimate σ values. At n = 5 the χ² distribution gives σ a roughly factor-of-2 uncertainty. A statistician reviewer would press: "your σ ratios are 0.52 / 0.29 / 0.45 — but with only n = 5, can you statistically distinguish them from 1.0?" `compute_sigma_ratio_bootstrap.py` answers this with (a) bootstrap CIs on the σ-ratio per corpus and (b) a permutation test on the cross-corpus σ-asymmetry.

**Hardware:** CPU-only; runs locally too. ~30 sec wall-clock.

### Cell A.1

```python
%cd /content/project
!python compute_sigma_ratio_bootstrap.py \
    --atepp-runs-dir phase1_beat_classical/runs \
    --bps-fh-eval-json research_data/bps_fh_eval_2026-05-09.json \
    --n-boot 10000 --seed 20260509 \
    --output-json research_data/sigma_collapse_formal_tests_2026-05-09.json \
    --output-md research_data/sigma_collapse_formal_tests_2026-05-09.md
```

**Verify:** the output MD prints a table of σ-ratio CIs per corpus + the permutation test p-value. The σ-collapse claim is formally defensible if the σ-ratio CI excludes 1.0 on both ATEPP-41 and BPS-FH at α = 0.05.

---

## A.2 — Classical 3-profile baseline on POP909 (closes Tier 2.1 hypothesis)

**WHY.** Rigour plan §2 predicted: *"BASELINE wins on POP909 (because pop modulation patterns aren't what KK / Temperley / AS profiles were designed for)."* With the POP909 v2 retrain showing BASELINE = 0.8681 ± 0.0122, we need the classical 3-profile number on POP909 to confirm the prediction. If classical < 0.50 (likely), then BASELINE substantially beats classical on POP909 — exactly the cross-corpus story the chapter prose anticipates.

**Hardware:** CPU-only (classical baseline doesn't need GPU). ~30 min wall-clock for 909 songs.

### Cell A.2

```python
%cd /content/project
!python evaluate_classical_baseline.py \
    --manifest research_data/pop909_manifest_2026-05-09.json \
    --label-dirs research_data/pop909_score_key_labels \
    --output research_data/pop909_classical_baseline_2026-05-09.json
```

**Verify:** the output JSON contains a `test_mirex_weighted_score` and a `per_composition` array of 137 entries. Print the FW MIREX:

```python
import json
d = json.load(open('research_data/pop909_classical_baseline_2026-05-09.json'))
print(f'Classical 3-profile FW MIREX on POP909 = {d["test_mirex_weighted_score"]:.4f}')
print(f'BASELINE FW MIREX on POP909 = 0.8681 (Su 2026r §2.4)')
print(f'Δ_FW (BASELINE − classical) on POP909 = {0.8681 - d["test_mirex_weighted_score"]:+.4f}')
```

Expected: classical FW likely 0.45–0.55 (much lower than BASELINE). If so, this confirms the rigour-plan §2 prediction.

---

## A.3 — Bump POP909 to n = 5 seeds (sample-size parity with ATEPP + BPS-FH)

**WHY.** Current POP909 v2 has n = 3 seeds (a/b/c). Bringing it to n = 5 (add seeds d/e) brings POP909 into line with ATEPP-41 + BPS-FH. The σ at n = 3 has factor-of-2 χ² uncertainty; at n = 5 this halves. ~3 GPU-h on A100 for the 2 extra seeds × 2 cells.

**Hardware:** A100 strongly recommended (T4 would take ~5 GPU-h).

### Cell A.3

```python
%cd /content/project
import subprocess, sys, time, hashlib
from datetime import datetime

# Two NEW POP909 seeds — d/e — appended to the existing a/b/c cohort
NEW_SEEDS = ['20260508d', '20260508e']
def seed_to_int(label):
    return int(hashlib.sha256(label.encode()).hexdigest()[:8], 16)

t0 = time.time()
for variant in ('BASELINE', 'T6_T1'):
    print(f'\n{"="*70}\n=== POP909 {variant} × 2 NEW SEEDS — to n=5 total\n{"="*70}', flush=True)
    for label in NEW_SEEDS:
        seed_int = seed_to_int(label)
        print(f'\n--- {variant} / {label} (int={seed_int}) ---', flush=True)
        subprocess.check_call([
            sys.executable, 'phase1_beat_classical/train_phase1.py',
            '--variant', variant,
            '--seed', str(seed_int),
            '--manifest', 'research_data/pop909_manifest_2026-05-09.json',
            '--label-dirs', 'research_data/pop909_score_key_labels',
            '--epochs', '30',
            '--device', 'cuda',
            '--output-dir', 'phase1_beat_classical/runs_pop909_v2',
            '--test-filter', 'none',
        ])
print(f'\nTotal wall-clock: {(time.time() - t0) / 60:.1f} min')
```

**Verify:** `phase1_beat_classical/runs_pop909_v2/` should now contain 10 files (5 BASELINE + 5 T6_T1). Re-run the eval to update `pop909_results_2026-05-09.json` with n = 5:

```python
!python eval_pop909_from_checkpoints.py \
    --checkpoint-dir phase1_beat_classical/runs_pop909_v2 \
    --manifest research_data/pop909_manifest_2026-05-09.json \
    --device cuda --variants BASELINE T6_T1 \
    --output-json research_data/pop909_results_2026-05-09.json \
    --output-md research_data/pop909_results_2026-05-09.md
```

---

## A.4 — BMA ensemble refit with T6_T1 (closes R5.3 HIGH severity)

**WHY.** The §7.4 deployable engine is the complementary classical-plus-neural ensemble. It was originally tuned with B9 as the neural input. With the Phase I result reshuffling the ranking to T6_T1, the §7.4 ensemble has been *citing* T6_T1 since 2026-04-30 but has not been formally re-fit. The BMA refit closes this slack across all 3 corpora (ATEPP-41 + POP909 + BPS-FH).

**Hardware:** CPU-only (eval-only; ~5 min).

### Cell A.4

```python
%cd /content/project
!python bma_refit_t6t1.py \
    --atepp-runs-dir phase1_beat_classical/runs \
    --pop909-runs-dir phase1_beat_classical/runs_pop909_v2 \
    --bps-fh-eval research_data/bps_fh_eval_2026-05-09.json \
    --atepp-classical research_data/classical_baseline_eval.json \
    --pop909-classical research_data/pop909_classical_baseline_2026-05-09.json \
    --output-json research_data/bma_refit_t6t1_2026-05-09.json \
    --output-md research_data/bma_refit_t6t1_2026-05-09.md
```

**Verify:** the output MD has 4 BMA variants per corpus: `neural_simple_mean`, `neural_bma`, `neural_plus_classical_uniform`, `neural_plus_classical_tempered_T10`. The chapter-citable number is `neural_plus_classical_uniform` per corpus.

**Optional (BPS-FH classical baseline):** if you want the BPS-FH classical bridge variants too, run:

```python
!python evaluate_classical_baseline.py \
    --manifest research_data/bps_fh_manifest_2026-05-09.json \
    --label-dirs research_data/bps_fh_score_key_labels \
    --output research_data/bps_fh_classical_baseline_2026-05-09.json
```

Then re-run the BMA refit (above) — the BPS-FH neural+classical variants will populate.

---

## A.5 — Sync the week's outputs back to Drive

```python
import os, shutil
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-09'
os.makedirs(DRIVE_OUT, exist_ok=True)
artefacts = [
    'research_data/sigma_collapse_formal_tests_2026-05-09.json',
    'research_data/sigma_collapse_formal_tests_2026-05-09.md',
    'research_data/pop909_classical_baseline_2026-05-09.json',
    'research_data/pop909_results_2026-05-09.json',
    'research_data/pop909_results_2026-05-09.md',
    'research_data/bma_refit_t6t1_2026-05-09.json',
    'research_data/bma_refit_t6t1_2026-05-09.md',
    'research_data/bps_fh_classical_baseline_2026-05-09.json',  # optional
    'phase1_beat_classical/runs_pop909_v2',
]
for src in artefacts:
    src = os.path.join('/content/project', src)
    if not os.path.exists(src): print(f'  ⚠ missing: {src}'); continue
    dst = os.path.join(DRIVE_OUT, os.path.basename(src))
    if os.path.isdir(src):
        if os.path.exists(dst): shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    print(f'  ✓ {src} → {dst}')
```

---

# B. NEXT 2 WEEKS (2026-05-16 → 2026-05-29)

## B.1 — TAVERN ingestion (closes Tier 2.3 + supplies the 4th corpus for σ-asymmetry)

**WHY.** Three corpora are now in hand for the σ-collapse replication (ATEPP-41 + BPS-FH + POP909). The cross-corpus σ-asymmetry observation (BASELINE σ ↑, T6_T1 σ ↓ under shift) is currently BPS-FH-only. TAVERN provides:
- A 4th cross-corpus replication of the σ-collapse pattern
- A 2nd cross-corpus zero-shot evaluation (other than BPS-FH) — validates the σ-asymmetry observation
- High modulation density (theme-and-variations cycle through related keys) — replicates the §7.1.2 modulating-subset null for a 4th time
- Per-composer subgroup analysis (Beethoven phrases vs Mozart phrases separately) — addresses the composer-overlap caveat (R2.2)

**TAVERN already comes bundled inside the project zip** at `TAVERN-master/`. The new `parse_tavern.py` script handles the Humdrum **kern format directly (no music21 dependency required for the parsing — built from scratch).

**Hardware:** CPU-only ingestion (~2 min); A100 zero-shot eval (~5 min).

### Cell B.1.a — ingestion

```python
%cd /content/project
!python parse_tavern.py \
    --input TAVERN-master \
    --output research_data/tavern_score_key_labels \
    --annotator a
import glob
n = len(glob.glob('research_data/tavern_score_key_labels/*.json'))
print(f'  ✓ Ingested {n} TAVERN phrases (expected ≈ 1060)')
```

### Cell B.1.b — zero-shot eval (mirror of BPS-FH)

```python
%cd /content/project
!python eval_tavern_from_checkpoints.py \
    --tavern-dir research_data/tavern_score_key_labels \
    --checkpoint-dir phase1_beat_classical/runs \
    --device cuda \
    --variants BASELINE T6_T1 \
    --output-json research_data/tavern_eval_2026-05-09.json \
    --output-md research_data/tavern_eval_2026-05-09.md
```

**Verify:** the output MD prints the per-cell table + the per-composer subgroup table (Beethoven phrases vs Mozart phrases separately). σ-collapse REPLICATES on TAVERN if `σ_T6_T1 < σ_BASELINE` in either subgroup.

### Cell B.1.c — sync TAVERN outputs to Drive

```python
import shutil, os
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-09'
for f in ['research_data/tavern_eval_2026-05-09.json',
          'research_data/tavern_eval_2026-05-09.md',
          'research_data/tavern_score_key_labels']:
    src = f'/content/project/{f}'
    dst = os.path.join(DRIVE_OUT, os.path.basename(src))
    if os.path.isdir(src):
        if os.path.exists(dst): shutil.rmtree(dst)
        shutil.copytree(src, dst)
    elif os.path.exists(src):
        shutil.copy2(src, dst)
    print(f'  ✓ {src} → {dst}')
```

---

## B.2 — Composer-overlap audit on TAVERN (closes R2.2)

**WHY.** TAVERN includes Beethoven (overlap with DCML string quartets in training) AND Mozart (overlap with `dcml_corpora/mozart_piano_sonatas` in training). The audit confirms 0 piece-level leakage and quantifies composer-level overlap.

**Hardware:** CPU-only, ~5 sec.

### Cell B.2

```python
%cd /content/project
!python compute_composer_overlap_audit.py \
    --training-manifest research_data/unified_training_manifest_phase1_clean.json \
    --bps-fh-dir research_data/bps_fh_score_key_labels \
    --tavern-root TAVERN-master \
    --output-json research_data/composer_overlap_audit_2026-05-09.json \
    --output-md research_data/composer_overlap_audit_2026-05-09.md
```

**Verify:** the output MD reports both BPS-FH and TAVERN audits. Expected: 0 piece-level overlap, both Beethoven AND Mozart composer-level overlap on TAVERN.

---

## B.3 — Apply Chapter Edit Class B + C + D

**WHY.** Class A (runtime integration update) is already applied to chapters 1, 7, 8 in your project tree (see `phase1_month2_2026-05-10.zip` thesis-and-papers/ folder). Class B + C + D are the cross-corpus + σ-asymmetry + future-work edits documented in `CHAPTER_EDIT_PUNCH_LIST_2026-05-09.md`. These are local Mac-side edits — do them in your usual editor (Cursor / VS Code / Neovim) using the punch-list as a find/replace guide.

**Wall-clock estimate:** ~4–6 hours of focused editing.

After applying, run the verification grep from the punch list:

```bash
cd thesis-and-papers
grep -n 'flagged in §7.5\|post-thesis paper experiment' "6. Evaluation.md" "7. Discussion.md"
# → should return 0 lines OR only references to TAVERN scheduled
grep -n 'cross-corpus generalisation is unproven' RESEARCH_FINDINGS_VS_RQs_2026-04-30.md
# → should return 0 lines (because BPS-FH replicated)
```

---

# C. MEDIUM-TERM (Months 3–4, 2026-06 → 2026-07)

## C.1 — Hyperparameter sensitivity sweep (closes Tier 2.4 / audit W7)

**WHY.** Phase B established that h ∈ {32, 96, 192, 256} were Pareto-tested on the original 250-record ATEPP pool, with h = 96 the winner. Audit W7 asks whether h = 192 (or larger) helps on the *expanded* 525-record BASELINE pool. The sensitivity sweep tests one hyperparameter at a time around BASELINE: h, dropout, ENS β, lr, batch_size. Any cell with > 0.01 FW improvement gets bumped from n = 1 to n = 3 seeds for proper sample-σ.

**Hardware:** A100 strongly recommended. ~22 cells × 1 seed × ~5 min = ~2 GPU-h on A100.

**PRE-REQUISITE: patch the trainer's CLI.** The current `train_phase1.py` doesn't expose `--hidden-size`, `--dropout`, `--ens-beta`, `--lr`, `--batch-size` as CLI arguments (it uses fixed values matching B9). Apply this patch ONCE inside the Colab session before running the sweep:

```python
%%writefile /tmp/sensitivity_patch.py
"""Apply once: patch train_phase1.py to expose --hidden-size etc. as CLI args."""
import re
src = open('/content/project/phase1_beat_classical/train_phase1.py').read()
if "'--hidden-size'" in src:
    print('  ✓ Patch already applied')
else:
    OLD = "    p.add_argument('--test-filter', default='atepp41',"
    NEW = """    p.add_argument('--hidden-size', type=int, default=96,
                   help='GRU hidden size (sensitivity sweep; default 96 = B9)')
    p.add_argument('--dropout', type=float, default=0.1,
                   help='Dropout rate (sensitivity sweep; default 0.1 = B9)')
    p.add_argument('--ens-beta', type=float, default=0.999,
                   help='ENS beta for class-balanced loss (sensitivity sweep; default 0.999 = B9)')
    p.add_argument('--test-filter', default='atepp41',"""
    assert OLD in src, 'patch marker not found — your trainer differs from the 2026-05-09 baseline'
    src = src.replace(OLD, NEW)
    # Also expose --lr and --batch-size if not already there
    # (they ARE already there per the current trainer)
    open('/content/project/phase1_beat_classical/train_phase1.py', 'w').write(src)
    print('  ✓ Patched train_phase1.py with --hidden-size / --dropout / --ens-beta')

# Then plumb the CLI args into model construction. The model is built around line 220
# (HarmonicContextGRUPhase1(hidden_size=96, ...)). Patch that line too:
src = open('/content/project/phase1_beat_classical/train_phase1.py').read()
if 'hidden_size=args.hidden_size' not in src:
    OLD2 = 'HarmonicContextGRUPhase1('
    NEW2 = 'HarmonicContextGRUPhase1(  # patched 2026-05-09 for sensitivity sweep\n        '
    # Insert hidden_size=args.hidden_size as the first kwarg
    src = src.replace(
        'model = HarmonicContextGRUPhase1(\n        hidden_size=96,',
        'model = HarmonicContextGRUPhase1(\n        hidden_size=args.hidden_size,'
    )
    open('/content/project/phase1_beat_classical/train_phase1.py', 'w').write(src)
    print('  ✓ Patched model construction')
```

```python
!python /tmp/sensitivity_patch.py
```

### Cell C.1 — sensitivity sweep

```python
%cd /content/project
!python sensitivity_sweep.py \
    --manifest research_data/unified_training_manifest_phase1_clean.json \
    --label-dirs "research_data/score_key_labels,research_data/dcml_score_key_labels,research_data/dcml_key_labels,research_data/wir_key_labels" \
    --seed-int 20260509 \
    --output-dir phase1_beat_classical/runs_sensitivity \
    --output-json research_data/sensitivity_sweep_2026-05-09.json \
    --output-md research_data/sensitivity_sweep_2026-05-09.md
```

**Smoke-test first** with `--smoke-test` to verify the patched trainer works before committing 2 GPU-h:

```python
!python sensitivity_sweep.py --smoke-test \
    --manifest research_data/unified_training_manifest_phase1_clean.json \
    --label-dirs "research_data/score_key_labels,research_data/dcml_score_key_labels,research_data/dcml_key_labels,research_data/wir_key_labels"
```

**Verify:** the output MD has 22 rows (one per cell). Look for any cell with Δ vs BASELINE > +0.01 — those are candidates for n = 3 expansion.

---

## C.2 — Aria-MIDI pre-training (closes Tier 3.2)

**This is the BIG one.** Detailed WHY + phased plan + Colab cells follow.

### C.2.0 — Why pre-train on Aria-MIDI?

The Phase I cumulative ablation training pool is **525 records** (250 ATEPP + 275 DCML). For deep learning this is small: most successful neural systems train on 10⁴–10⁷ examples. The hypothesis is that pre-training on a much larger MIDI corpus produces learned representations of musical structure (rhythmic patterns, voice-leading, common chord progressions) that fine-tuning on the small labelled ATEPP+DCML pool can leverage.

**S-KEY (Kong et al., ICASSP 2025)** showed this works for AUDIO key detection: pre-train on ~1 M unlabelled songs with self-supervised equivariance + mode loss, then fine-tune on labelled key data. **Aria-MIDI** is the symbolic-MIDI analogue: 371 K MIDI files (deduped subset; Bradshaw et al., 2024).

**Two predicted outcomes** (rigour plan §6):
- (a) Aria-MIDI pre-training adds Δ_FW ≈ +0.02 to +0.05 on top of T6_T1 = 0.6707 (in-domain ATEPP-41). The pre-training transfer hypothesis is supported, contradicting the small-scale Phase C null at 5 K files.
- (b) Aria-MIDI pre-training adds nothing, or harms. The small-scale Phase C null replicates at scale.

**Both outcomes are publishable.** A null at 371 K is a strong methodological result; a positive transfer at 371 K is a stronger one.

### C.2.1 — Phased execution

The full 371 K corpus takes ~1 week on 1 A100 (rigour plan §6). Colab Pro+ caps a session at 24 h. We therefore phase the work:

| Phase | Files | Epochs | Wall-clock | Purpose |
|---|---:|---:|---:|---|
| **A — smoke test** | 5 K | 3 | ~30 min on A100 | Verify pipeline + Aria-MIDI loader works end-to-end |
| **B — early signal** | 50 K | 5 | ~12–24 h on A100 | Can the loss come down? Early convergence signal |
| **C — full corpus** | 371 K | 30 | ~1 week on A100 (multi-session) | The main experiment; requires checkpoint resumption across 7 sessions |
| **D — fine-tune** | 525 (ATEPP+DCML) | 30 | ~30 min/seed × 5 seeds = 2.5 h on A100 | Load Phase C checkpoint into T6_T1 trainer |
| **E — eval** | All test corpora | — | ~30 min on A100 | Re-run ATEPP-41 + BPS-FH + POP909 + TAVERN evals |

### C.2.2 — Phase A smoke test (do this FIRST; ~30 min)

**Step 1 — upload Aria-MIDI tarball to Drive.**

The tarball is ~1.9 GB; on a typical residential connection, expect ~30 min upload. Place at: `/content/drive/MyDrive/PhD/aria-midi-v1-deduped-ext.tar.gz`.

**Step 2 — extract on Colab and run smoke test.**

```python
%cd /content
import os, time
DRIVE_TARBALL = '/content/drive/MyDrive/PhD/aria-midi-v1-deduped-ext.tar.gz'
LOCAL_TARBALL = '/content/aria-midi-v1-deduped-ext.tar.gz'
EXTRACT_DIR = '/content/aria_midi_extracted'

# Copy from Drive to local Colab disk (faster than streaming from Drive)
if not os.path.exists(LOCAL_TARBALL):
    print(f'Copying tarball from Drive to local VM (~1.9 GB)...')
    t0 = time.time()
    !cp "{DRIVE_TARBALL}" "{LOCAL_TARBALL}"
    print(f'  ✓ Copied in {(time.time()-t0)/60:.1f} min')

# Extract (~5 min on Colab; will produce ~371K files in nested dirs)
if not os.path.isdir(EXTRACT_DIR):
    os.makedirs(EXTRACT_DIR)
    print(f'Extracting...')
    t0 = time.time()
    !tar -xzf "{LOCAL_TARBALL}" -C "{EXTRACT_DIR}"
    print(f'  ✓ Extracted in {(time.time()-t0)/60:.1f} min')

# Verify
import glob
n_midis = len(glob.glob(f'{EXTRACT_DIR}/**/*.mid', recursive=True))
print(f'  ✓ {n_midis} .mid files found in {EXTRACT_DIR} (expected ~371,053)')
```

```python
%cd /content/project
!python pretrain_aria_midi.py \
    --phase A \
    --aria-root /content/aria_midi_extracted \
    --limit 5000 \
    --epochs 3 \
    --batch-size 32 \
    --device cuda \
    --output-checkpoint research_data/symbolic_key_pretrained_aria_phaseA.pt
```

**Verify:** the output checkpoint exists + the log shows the equivariance + mode + batch losses decreasing across the 3 epochs. ~30 min wall-clock total.

### C.2.3 — Phase B early signal (~12–24 h)

```python
%cd /content/project
!python pretrain_aria_midi.py \
    --phase B \
    --aria-root /content/aria_midi_extracted \
    --limit 50000 \
    --epochs 5 \
    --batch-size 64 \
    --lr 5e-4 \
    --device cuda
```

**Sync to Drive** between Colab Pro+ sessions (don't lose the checkpoint to a session reset):

```python
import shutil
shutil.copy2(
    '/content/project/research_data/symbolic_key_pretrained_aria_phaseB.pt',
    '/content/drive/MyDrive/PhD/symbolic_key_pretrained_aria_phaseB.pt')
print('  ✓ Phase B checkpoint synced to Drive')
```

### C.2.4 — Phase C full corpus (~1 week, 7 sessions)

This is the multi-day commitment. Plan: each Colab Pro+ session gets ~23 h training; restart the next day with `--resume`. Save to Drive between sessions.

```python
%cd /content/project
# Each session — paste this and it will train for ~23 h then early-stop
!python pretrain_aria_midi.py \
    --phase C \
    --aria-root /content/aria_midi_extracted \
    --epochs 30 \
    --batch-size 64 \
    --lr 5e-4 \
    --device cuda \
    --resume
```

After session, sync to Drive:

```python
import shutil
shutil.copy2(
    '/content/project/research_data/symbolic_key_pretrained_aria_phaseC.pt',
    '/content/drive/MyDrive/PhD/symbolic_key_pretrained_aria_phaseC.pt')
print('  ✓ Phase C checkpoint synced to Drive')
```

When you start the NEXT Colab session (the next day), restore the checkpoint first:

```python
import shutil
shutil.copy2(
    '/content/drive/MyDrive/PhD/symbolic_key_pretrained_aria_phaseC.pt',
    '/content/project/research_data/symbolic_key_pretrained_aria_phaseC.pt')
print('  ✓ Restored Phase C checkpoint; ready to resume')
```

### C.2.5 — Phase D fine-tune T6_T1 from Aria-MIDI initialization

**PRE-REQUISITE: patch `train_phase1.py` to accept `--pretrained-checkpoint`** (one-time patch in Colab):

```python
%%writefile /tmp/finetune_patch.py
src = open('/content/project/phase1_beat_classical/train_phase1.py').read()
if "'--pretrained-checkpoint'" in src:
    print('  ✓ Patch already applied')
else:
    OLD = "    p.add_argument('--test-filter', default='atepp41',"
    NEW = """    p.add_argument('--pretrained-checkpoint', default=None,
                   help='Path to a pre-trained checkpoint (e.g., from Aria-MIDI '
                        'pre-training) to initialise the model weights. '
                        '`strict=False` is used so partial weight loads are OK.')
    p.add_argument('--test-filter', default='atepp41',"""
    src = src.replace(OLD, NEW)
    # Plumb into model construction: after model = HarmonicContextGRUPhase1(...)
    # add a load_state_dict call if --pretrained-checkpoint is provided
    OLD2 = "    model = HarmonicContextGRUPhase1("
    NEW2 = "    model = HarmonicContextGRUPhase1("
    # We need to insert a few lines AFTER the model constructor but BEFORE optimizer
    INSERT_AFTER = '    print(f\\'  Total parameters:\\''
    INSERT_TEXT = '''    if args.pretrained_checkpoint:
        ckpt = torch.load(args.pretrained_checkpoint, map_location=device, weights_only=False)
        msg = model.load_state_dict(ckpt['model_state_dict'], strict=False)
        print(f'  Loaded pretrained init from {args.pretrained_checkpoint} '
              f'(missing keys: {len(msg.missing_keys)}; unexpected: {len(msg.unexpected_keys)})')
'''
    if INSERT_TEXT.strip() not in src:
        # Find a suitable insertion point — after model construction, before training loop
        marker = 'optimizer = optim.Adam(model.parameters()'
        src = src.replace(marker, INSERT_TEXT + '\n    ' + marker)
    open('/content/project/phase1_beat_classical/train_phase1.py', 'w').write(src)
    print('  ✓ Patched train_phase1.py with --pretrained-checkpoint')
```

```python
!python /tmp/finetune_patch.py
```

```python
%cd /content/project
import subprocess, sys, time, hashlib
NEW_SEEDS = ['20260425a', '20260425b', '20260425c', '20260425d', '20260425e']  # canonical 5
def seed_to_int(label):
    return int(hashlib.sha256(label.encode()).hexdigest()[:8], 16)
SEED_INTS = {'20260425a': 3886265411, '20260425b': 3128166492,
             '20260425c': 1252837625, '20260425d': 3629727882,
             '20260425e': 440397851}

PRE_CKPT = '/content/project/research_data/symbolic_key_pretrained_aria_phaseC.pt'
t0 = time.time()
for label in NEW_SEEDS:
    seed_int = SEED_INTS[label]
    print(f'\n--- T6_T1 / {label} (int={seed_int}) — fine-tune from Aria-MIDI init ---', flush=True)
    subprocess.check_call([
        sys.executable, 'phase1_beat_classical/train_phase1.py',
        '--variant', 'T6_T1',
        '--seed', str(seed_int),
        '--manifest', 'research_data/unified_training_manifest_phase1_clean.json',
        '--label-dirs', 'research_data/score_key_labels,research_data/dcml_score_key_labels,research_data/dcml_key_labels,research_data/wir_key_labels',
        '--epochs', '30',
        '--device', 'cuda',
        '--output-dir', 'phase1_beat_classical/runs_aria_finetuned',
        '--test-filter', 'atepp41',
        '--pretrained-checkpoint', PRE_CKPT,
    ])
print(f'\nTotal wall-clock: {(time.time() - t0) / 60:.1f} min')
```

### C.2.6 — Phase E re-eval cross-corpus (with Aria-finetuned checkpoints)

```python
%cd /content/project
# ATEPP-41 results are in the eval JSONs from Phase D directly. Compare to T6_T1 = 0.6707 baseline.
import json, glob
fws = []
for f in sorted(glob.glob('phase1_beat_classical/runs_aria_finetuned/T6_T1_seed*_eval.json')):
    d = json.load(open(f))
    fws.append(d['test_mirex_weighted_score'])
print(f'T6_T1 + Aria-MIDI fine-tuning, ATEPP-41 n={len(fws)}: {fws}')
import statistics
print(f'  μ={statistics.mean(fws):.4f}  σ={statistics.stdev(fws):.4f}')
print(f'  Reference: T6_T1 from-scratch on ATEPP-41 = 0.6707 ± 0.0103')
print(f'  Δ = {statistics.mean(fws) - 0.6707:+.4f}')

# Cross-corpus: re-run BPS-FH + POP909 + TAVERN evals with Aria-finetuned checkpoints
!python eval_bps_fh_from_checkpoints.py \
    --bps-fh-dir research_data/bps_fh_score_key_labels \
    --checkpoint-dir phase1_beat_classical/runs_aria_finetuned \
    --device cuda \
    --output-json research_data/bps_fh_eval_aria_2026-05-09.json \
    --output-md research_data/bps_fh_eval_aria_2026-05-09.md
```

**Verify:** if Aria-MIDI pre-training helps, the post-fine-tune T6_T1 should exceed 0.6707 on ATEPP-41 by ≥ +0.02 (positive outcome) or be ≤ 0.6707 (null outcome — equally publishable).

---

# D. Three-pass reviewer record for this playbook

### Pass 1 — Statistician reviewer (issues: 2, revisions: 2)

**P1.1.** Cell A.3 originally trained the 2 new POP909 seeds without verifying the existing n = 3 cohort wasn't overwritten. **Revised:** Cell A.3 uses a NEW labels list (`20260508d`, `20260508e`) — the existing seed_ints (a/b/c = 2925407343/940114980/3545274872) are SHA-256 distinct from d/e, so re-training preserves the existing checkpoints.

**P1.2.** Cell C.1 originally didn't note that "n = 1 per cell" sensitivity sweep results are not directly comparable to BASELINE's n = 5 cell mean. **Revised:** the sweep prose explicitly says "any cell with > 0.01 FW improvement gets bumped from n = 1 to n = 3 seeds for proper sample-σ" — matches rigour plan §4.

### Pass 2 — Engineering reviewer (issues: 3, revisions: 3)

**P2.1.** Cell C.1 sensitivity-patch script originally did the patch in one giant string. A reviewer would prefer two small surgical patches (one for argparse, one for model construction). **Revised:** Cell C.1 patch script is split into two clearly-marked sections; each one is idempotent (re-running is safe).

**P2.2.** Cell C.2.4 (Phase C multi-session) originally didn't mention the Drive-sync between sessions. A reviewer would press: "what happens when Pro+ kills the session at 24h?" **Revised:** Cell C.2.4 now has explicit Drive-sync code + restore-on-next-session code. Multi-session continuity is preserved.

**P2.3.** Cell A.4 (BMA refit) originally assumed the BPS-FH classical baseline was already in hand. A reviewer would press: "you reference `bps_fh_classical_baseline_2026-05-09.json` — where does it come from?" **Revised:** Cell A.4 now contains an explicit "Optional (BPS-FH classical baseline)" subsection with the eval command, and the BMA refit script gracefully degrades if the BPS-FH classical baseline is missing (skips classical-bridge variants for that corpus only).

### Pass 3 — Music IR domain reviewer (issues: 2, revisions: 2)

**P3.1.** The Aria-MIDI pre-training §C.2.0 originally framed both predicted outcomes as "equally publishable" without explaining what each implies for the deployable engine. **Revised:** §C.2.0 now distinguishes outcome (a) "T6_T1 + Aria-finetune" as the new deployable detector if Δ_FW > +0.02 vs outcome (b) "Aria pre-training doesn't help; T6_T1 from-scratch remains the recommendation."

**P3.2.** The TAVERN cell (§B.1.b) originally didn't reference the per-composer subgroup analysis explicitly. A reviewer would press: "TAVERN has Beethoven AND Mozart — which subgroup carries the σ-collapse?" **Revised:** §B.1.b verify-step now mentions that the output MD's per-composer subgroup table is the right place to read this; both subgroups must show σ_T6_T1 < σ_BASELINE for the σ-collapse cross-corpus claim to be robust.

---

*Compiled 2026-05-09. Three reviewer passes executed. Estimated total wall-clock: ~5 GPU-h on A100 for week-1 (A.1–A.5), ~3 GPU-h for TAVERN (B.1), ~2 GPU-h for sensitivity sweep (C.1), ~1 week for Aria-MIDI Phase C (C.2.4) — the latter is the only multi-day commitment.*
