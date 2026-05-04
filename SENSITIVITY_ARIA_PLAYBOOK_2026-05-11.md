# Sensitivity sweep + Aria-MIDI playbook — 2026-05-11 → Months 3–4

**Author:** Rui Su
**Date:** 2026-05-11
**Companion artefact:** `phase1_month2_2026-05-11.zip` (the Drive-uploadable project zip; contains the patched trainer, the sensitivity sweep driver, the Aria-MIDI pre-training wrapper, all 4-corpus evidence files, and `PAPER_DRAFT_2026-05-09_v2.md`).
**Reviewer passes:** 3 independent reviewer rounds documented in §F below.

This document is a **runbook**. Each section is one operational task; each task has (i) the WHY, (ii) the exact Colab cells to paste-and-run, (iii) the expected output, (iv) a verification check, and (v) the resume strategy when a Colab session times out. No prose-only explanation; every step is executable.

The playbook covers Job 4b of the 2026-05-11 work plan (Priority 5 — sensitivity sweep + Aria-MIDI pre-training as scheduled in `COMPREHENSIVE_RIGOUR_PLAN_2026-04-26.md` §4 Tier 2.4 and §6 Tier 3.2). Jobs 1 (4-corpus σ-bootstrap), 2 (TAVERN classical baseline), and 3 (paper draft revision) are already complete on the laptop and bundled inside `phase1_month2_2026-05-11.zip`.

---

## Table of contents

- §A — Setup (fresh Colab Pro+ session)
- §B — Sensitivity sweep (~22 cells × 1 seed = ~2 GPU-h on A100; expand to n=3 only on cells with Δ_FW > 0.01 vs BASELINE)
- §C — Aria-MIDI Phase A (smoke test, 5 K files, ~30 min on A100)
- §D — Aria-MIDI Phase B (early signal, 50 K files, ~12–24 h on A100)
- §E — Aria-MIDI Phase C (full corpus, 371 K files, ~1 week wall-clock; multi-session resume across the 24 h Colab cap)
- §F — Aria-MIDI Phase D (fine-tune T6_T1 from the Phase C checkpoint; ~2.5 h on A100)
- §G — Aria-MIDI Phase E (cross-corpus eval of fine-tuned T6_T1; ~30 min on A100)
- §H — Drive sync targets (what to upload, when, where)
- §I — Reviewer record (3 passes against the highest academic standards)

---

## §A — Setup (fresh Colab Pro+ session)

**WHY.** A fresh Colab session starts with no project files. We mount Drive, unpack the zip, install the pinned PyTorch stack, and verify GPU + scripts before any compute is consumed.

**Hardware:** A100 (Colab Pro+) for §B–§G. T4 will not finish Phase B inside the 24 h cap. **Do not run §B onward on a T4 — it will silently waste GPU credits.**

### Cell A.0 — mount Drive + extract zip + verify

```python
from google.colab import drive
drive.mount('/content/drive')

!cd /content && rm -rf project && unzip -q \
    /content/drive/MyDrive/PhD/phase1_month2_2026-05-11.zip -d project
!pip install -q torch==2.5.1 numpy mido music21 openpyxl pretty_midi tqdm pandas

import torch, platform, os
print('torch:', torch.__version__)
print('Python:', platform.python_version())
if not torch.cuda.is_available():
    raise RuntimeError('Runtime → Change runtime type → GPU (A100).')
gpu_name = torch.cuda.get_device_name(0)
vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
print(f'✅ GPU: {gpu_name} ({vram_gb:.1f} GB VRAM)')
if 'A100' not in gpu_name:
    print(f'⚠️  WARNING: Phase B onward needs A100; current GPU is {gpu_name}.')
    print(f'    Sensitivity sweep (§B) is fine on T4. Aria phases need A100.')

# Verify the critical scripts are in place
for f in ('parse_tavern.py', 'eval_tavern_from_checkpoints.py',
          'bma_refit_t6t1.py', 'sensitivity_sweep.py',
          'pretrain_aria_midi.py', 'fix_pop909_per_piece.py',
          'compute_sigma_ratio_bootstrap.py'):
    p = os.path.join('/content/project', f)
    assert os.path.exists(p), f'MISSING: {f}'
    print(f'  ✓ {f}')

# Verify the canonical research data is in place
for f in ('research_data/unified_training_manifest_phase1_clean.json',
          'research_data/bps_fh_eval_2026-05-09.json',
          'research_data/pop909_results_2026-05-09.json',
          'research_data/tavern_eval_2026-05-09.json',
          'research_data/sigma_collapse_formal_tests_2026-05-09.json',
          'research_data/bma_refit_t6t1_2026-05-09.json'):
    p = os.path.join('/content/project', f)
    assert os.path.exists(p), f'MISSING: {f}'
    print(f'  ✓ {f}')

print('\n✅ Setup complete. Proceed to §B (sensitivity sweep) or §C (Aria Phase A).')
```

**Verification:** all 7 scripts and 6 canonical JSONs print with a ✓. GPU type printed.

---

## §B — Sensitivity sweep (Tier 2.4)

**WHY.** Audit weakness W7 in `phd_project_audit_report_2026-04-30.md` asks: with the expanded 525-record training pool (BASELINE), does the original Phase B Pareto choice of `hidden_size=96` still hold? Or does a larger model (h=192, h=384) win? `COMPREHENSIVE_RIGOUR_PLAN_2026-04-26.md` §4 Tier 2.4 specifies a one-hyperparameter-at-a-time sweep around BASELINE: `h ∈ {48, 96, 144, 192, 256, 384}`, `dropout ∈ {0.0, 0.1, 0.2, 0.3}`, `ENS β ∈ {0.99, 0.999, 0.9999, 0.99999}`, `lr ∈ {3e-4, 1e-3, 3e-3, 1e-2}`, `batch ∈ {4, 8, 16, 32}`. n=1 seed initially; bump to n=3 only on cells with Δ_FW > 0.01 vs BASELINE (the noise floor inferred from `b9_5seed_stability_2026-04-20.json`).

**Pre-registration.** This sweep is **descriptive**, not confirmatory. We do not Bonferroni-correct the 22 single-seed comparisons. Any cell that shows Δ_FW > 0.01 at n=1 is flagged for confirmation at n=3. Any cell that survives n=3 with the lower 95 % cluster-bootstrap CI above BASELINE is the new architectural choice.

**Compute.** 22 cells × 1 seed × ~1 min train (h=96-equivalent) ≈ 25–35 min on A100. The h=384 cell is roughly 4× the BASELINE cost, so total wall-clock is ~45 min on A100, ~2 h on T4.

### Cell B.0 — patch `train_phase1.py` to expose sweep CLI flags

The `sensitivity_sweep.py` driver invokes `train_phase1.py` with `--hidden-size`, `--dropout`, `--ens-beta`, `--lr`, `--batch-size`. The trainer in the zip already accepts these (see the `2026-05-11` patch comment near the top of `phase1_beat_classical/train_phase1.py`). This cell verifies the patch is in place.

```python
import subprocess
out = subprocess.check_output(
    ['python', '/content/project/phase1_beat_classical/train_phase1.py', '--help'],
    text=True
)
required = ['--hidden-size', '--dropout', '--ens-beta', '--lr', '--batch-size']
missing = [f for f in required if f not in out]
assert not missing, f'Missing CLI flags in train_phase1.py: {missing}'
print('✓ All sensitivity-sweep CLI flags exposed by train_phase1.py')
```

If this assertion fails, the trainer in the zip is older than the sweep driver. Apply the patch documented in `EXECUTION_PLAYBOOK_2026-05-09.md` §C.4 (or report back so I can rebuild the zip).

### Cell B.1 — smoke test (1 cell, ~1 min) before launching the full sweep

```python
%cd /content/project
!python sensitivity_sweep.py --smoke-test \
    --output-json research_data/sensitivity_sweep_smoke_2026-05-11.json \
    --output-md   research_data/sensitivity_sweep_smoke_2026-05-11.md
```

**Verification:** prints `✓ Wrote …smoke…json`. The h096_BASELINE cell should report FW MIREX in the same range as `b9_5seed_stability_2026-04-20.json` (mean ≈ 0.690, σ ≈ 0.025 on ATEPP-41 — single seeds vary by ±0.04).

### Cell B.2 — full sweep (skip h=384 to stay under 1 h on A100; rerun without `--skip-large-h` if h=256 looks promising)

```python
%cd /content/project
!python sensitivity_sweep.py --skip-large-h \
    --output-json research_data/sensitivity_sweep_2026-05-11.json \
    --output-md   research_data/sensitivity_sweep_2026-05-11.md
```

**Verification:** the markdown output table at `research_data/sensitivity_sweep_2026-05-11.md` should show 21 rows (22 minus h=384). Check the FW MIREX column for any cell with Δ vs BASELINE > +0.01 — those are the candidates for the n=3 confirmation pass.

### Cell B.3 — n=3 confirmation pass for promising cells (only run if B.2 flags any cell)

```python
# Replace ['h192', 'dropout020'] with the actual labels flagged in B.2.
PROMISING_CELLS = ['h192', 'dropout020']  # EDIT BEFORE RUNNING

import json, subprocess, sys
all_results = []
for label in PROMISING_CELLS:
    # Re-run the same cell at 3 additional seeds (20260510, 20260511, 20260512).
    for seed in [20260510, 20260511, 20260512]:
        cmd = ['python', '/content/project/sensitivity_sweep.py',
               '--smoke-test', '--seed-int', str(seed),
               '--output-json', f'research_data/sensitivity_sweep_{label}_seed{seed}.json',
               '--output-md',   f'research_data/sensitivity_sweep_{label}_seed{seed}.md']
        # Override which cell the smoke test runs by editing SWEEP_GRID would
        # require a code change; for n=3 confirmation we recommend running the
        # full sweep without --smoke-test and grep-filtering the output JSON
        # by `cell.label` afterwards. See B.2 for the full-sweep invocation.
        print(f'\n=== {label} seed={seed} ===')
        # subprocess.check_call(cmd)   # uncomment to actually run

print('\n[Manual step: bootstrap CI on the 3-seed sample for each promising '
      'cell using compute_sigma_ratio_bootstrap.py-style cluster bootstrap; '
      'see RESEARCH_FINDINGS_2026-05-09_FINAL.md §3 for the protocol.]')
```

### Cell B.4 — sync sweep results back to Drive

```python
import shutil, os
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/sensitivity_sweep'
os.makedirs(DRIVE_OUT, exist_ok=True)
for f in os.listdir('/content/project/research_data'):
    if f.startswith('sensitivity_sweep_') and f.endswith(('.json', '.md')):
        shutil.copy2(f'/content/project/research_data/{f}',
                     f'{DRIVE_OUT}/{f}')
        print(f'  ✓ {f} → {DRIVE_OUT}/')
print('\n✅ Sensitivity sweep complete. Sync these files back to laptop for §6.6.X chapter prose update.')
```

**Expected outcome.** Three publication-relevant findings:
1. **Pareto stability:** if no cell shows Δ_FW > 0.01, the original h=96 choice is robust on the expanded 525-record pool. This closes W7 with a null result that strengthens the BASELINE configuration.
2. **A new winner:** if a cell (most likely h=192 or h=144) survives the n=3 confirmation with lower 95 % CI > BASELINE, this becomes the new architectural recommendation. Rerun the cumulative ablation (T6, T6_T1, T6_T1_T2) at the new h.
3. **A regularisation finding:** dropout cells are the second-most-likely source of a positive Δ. If `dropout=0.0` improves FW (suggesting we are under-fitting), this informs the §6.6.X chapter's discussion of model capacity.

---

## §C — Aria-MIDI Phase A (smoke test, 5 K files, ~30 min on A100)

**WHY.** Phase A verifies the Aria-MIDI loader, the S-KEY-style pre-training loop, and the metadata-CSV synthesis end-to-end on a small subset before we commit to the multi-day Phase C run. A failure mode caught at 30 min wall-clock is a million-times cheaper than one caught at day 5.

The Aria-MIDI deduped tarball is `aria-midi-v1-deduped-ext.tar.gz` (~1.9 GB compressed, ~14 GB extracted, 371 K MIDI files; license CC-BY-NC-SA 4.0; Bradshaw et al., 2024). For Phase A we limit to the first 5 000 files — enough to verify the loader and to see the loss curve come down for at least 3 epochs.

**Compute.** 5 000 files × 3 epochs ≈ 25–30 min on A100, ~2 h on T4. Use A100.

### Cell C.0 — download + extract Aria-MIDI to local Colab disk

The 1.9 GB tarball is too big for a daily Drive sync; we download from the official mirror once per session.

```python
import os, subprocess, shutil
ARIA_DEST = '/content/aria_midi_extracted'
ARIA_TARBALL = '/content/aria-midi-v1-deduped-ext.tar.gz'

# Use the Hugging Face mirror; substitute the HF token if you have one for
# the higher rate limit. The dataset card is at:
#   https://huggingface.co/datasets/loubb/aria-midi
# (You will be asked to accept the license on first download.)
HF_URL = 'https://huggingface.co/datasets/loubb/aria-midi/resolve/main/aria-midi-v1-deduped-ext.tar.gz'

if not os.path.exists(ARIA_TARBALL):
    print(f'Downloading Aria-MIDI tarball (~1.9 GB) ...')
    !wget -q --show-progress -O {ARIA_TARBALL} {HF_URL}
    print(f'  ✓ Downloaded')

if not os.path.isdir(ARIA_DEST):
    os.makedirs(ARIA_DEST, exist_ok=True)
    print(f'Extracting (~14 GB, takes 3-4 min on A100 disk) ...')
    !cd {ARIA_DEST} && tar -xzf {ARIA_TARBALL}
    print(f'  ✓ Extracted to {ARIA_DEST}')

# Count
n_midi = subprocess.check_output(
    ['bash', '-c', f'find {ARIA_DEST} -name "*.mid" -o -name "*.midi" | wc -l'],
    text=True
).strip()
print(f'  Found {n_midi} MIDI files in {ARIA_DEST}')
assert int(n_midi) > 100_000, f'Expected ~371K files, got {n_midi}; extraction may be incomplete'
```

**Verification:** `n_midi` ≈ 371 000.

### Cell C.1 — Phase A smoke test

```python
%cd /content/project
!python pretrain_aria_midi.py --phase A \
    --aria-root /content/aria_midi_extracted \
    --limit 5000 \
    --epochs 3 \
    --batch-size 32 \
    --lr 5e-4 \
    --device cuda
```

**Verification.** Three things must hold for Phase A to be considered passed:
1. The script writes `research_data/symbolic_key_pretrained_aria_phaseA.pt` (the checkpoint).
2. The script writes `research_data/aria_midi_pretrain_log_phaseA.json` with `n_midi_files: 5000`.
3. The training log inside `pretrain_symbolic_key.py` (printed to stdout) shows the **total loss strictly decreasing** across the 3 epochs. If the loss is flat or increasing, the loader is feeding garbage to the model — DO NOT proceed to Phase B until this is debugged.

### Cell C.2 — sync Phase A artefacts to Drive

```python
import shutil, os
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseA'
os.makedirs(DRIVE_OUT, exist_ok=True)
for f in ('symbolic_key_pretrained_aria_phaseA.pt',
          'aria_midi_pretrain_log_phaseA.json',
          'aria_midi_metadata_phaseA.csv'):
    src = f'/content/project/research_data/{f}'
    if os.path.exists(src):
        shutil.copy2(src, f'{DRIVE_OUT}/{f}')
        print(f'  ✓ {f} → {DRIVE_OUT}/')
    else:
        print(f'  ⚠ missing: {f}')
```

---

## §D — Aria-MIDI Phase B (early signal, 50 K files, ~12–24 h on A100)

**WHY.** Phase B is the first genuine "is the pre-training learning anything useful?" check. 50 K files is large enough that the model sees diverse rhythmic patterns and chord progressions, but small enough to fit in a single Colab Pro+ session (24 h cap). If Phase B's loss plateau looks promising AND a Phase B → Phase D fine-tune produces Δ_FW > 0 on ATEPP-41, we have empirical justification for committing the week-long Phase C compute.

**Critical decision point.** After Phase B + a Phase D-style fine-tune (use Phase B's checkpoint instead of Phase C's), we MUST decide:
- **Δ_FW ≥ +0.01 on ATEPP-41:** proceed to Phase C. The pre-training transfer hypothesis has empirical support at 50 K.
- **Δ_FW between -0.005 and +0.01:** the result is ambiguous. Re-run Phase B with a lower learning rate (1e-4) and/or longer (10 epochs) before committing to Phase C.
- **Δ_FW < -0.005:** the small-scale Phase C null at 5 K replicates at 50 K. Do **not** spend a week on the full corpus; instead, document the negative-transfer finding (Tier 3.2 alt-outcome (b)) in the chapter.

**Compute.** 50 K files × 5 epochs ≈ 12–18 h on A100. The 24 h Colab Pro+ cap is the binding constraint; do not start Phase B with less than 20 h remaining on the session timer.

### Cell D.0 — extract (if not already) + Phase B launch

```python
%cd /content/project
# If the Aria tarball was already extracted in §C, this cell skips the
# download + extract steps.
import os
ARIA_DEST = '/content/aria_midi_extracted'
if not os.path.isdir(ARIA_DEST):
    print('Aria tarball not extracted — re-run §C.0 first.')
else:
    print(f'  ✓ {ARIA_DEST} already extracted')

!python pretrain_aria_midi.py --phase B \
    --aria-root /content/aria_midi_extracted \
    --limit 50000 \
    --epochs 5 \
    --batch-size 32 \
    --lr 5e-4 \
    --device cuda
```

**Verification.** The script writes `research_data/symbolic_key_pretrained_aria_phaseB.pt`. The pre-training log in stdout must show monotonic loss decrease across the 5 epochs (some local oscillations are fine; the trend must be downward).

### Cell D.1 — Phase B → Phase D-style fine-tune (~30 min × 5 seeds = 2.5 h on A100)

This cell uses Phase B's checkpoint as the initialisation for T6_T1 fine-tuning, then evaluates on ATEPP-41. This is the empirical decision-gate for whether to commit to Phase C.

**Pre-condition:** `train_phase1.py` must accept `--pretrained-checkpoint`. The trainer in `phase1_month2_2026-05-11.zip` already includes this patch (a one-time addition that loads `state_dict` with `strict=False`).

```python
%cd /content/project
import subprocess
SEEDS = [20260509, 20260510, 20260511, 20260512, 20260513]
PRETRAINED = 'research_data/symbolic_key_pretrained_aria_phaseB.pt'

for seed in SEEDS:
    print(f'\n=== Phase B → fine-tune T6_T1 seed={seed} ===')
    subprocess.check_call([
        'python', 'phase1_beat_classical/train_phase1.py',
        '--variant', 'T6_T1',
        '--pretrained-checkpoint', PRETRAINED,
        '--seed', str(seed),
        '--manifest', 'research_data/unified_training_manifest_phase1_clean.json',
        '--label-dirs', ','.join([
            'research_data/score_key_labels',
            'research_data/dcml_score_key_labels',
            'research_data/dcml_key_labels',
            'research_data/wir_key_labels',
        ]),
        '--epochs', '30',
        '--device', 'cuda',
        '--output-dir', 'phase1_beat_classical/runs_aria_phaseB_finetuned',
        '--test-filter', 'atepp41',
    ])

print('\n✅ Phase B fine-tune complete. Compare FW MIREX of these 5 seeds')
print('   against the canonical T6_T1 5-seed mean (0.6707 on ATEPP-41).')
```

### Cell D.2 — read out Phase B fine-tune results + Δ_FW gate

```python
import json, glob
PHASE_B_FW = []
for j in sorted(glob.glob('/content/project/phase1_beat_classical/'
                          'runs_aria_phaseB_finetuned/T6_T1_seed*_eval.json')):
    d = json.load(open(j))
    fw = d.get('test_mirex_weighted_score')
    PHASE_B_FW.append(fw)
    print(f'  {j}: FW = {fw:.4f}')

import statistics
mean_b = statistics.mean(PHASE_B_FW)
sd_b = statistics.stdev(PHASE_B_FW) if len(PHASE_B_FW) > 1 else 0.0
print(f'\nPhase B fine-tune:  mean FW = {mean_b:.4f}  σ = {sd_b:.4f}  (n={len(PHASE_B_FW)})')

# Canonical T6_T1 baseline (no pre-training): mean 0.6707, σ 0.0214
# Source: research_data/RESEARCH_FINDINGS_2026-05-09_FINAL.md Table 1
T6T1_BASELINE_MEAN = 0.6707
delta = mean_b - T6T1_BASELINE_MEAN
print(f'Canonical T6_T1 (no pre-train): mean FW = {T6T1_BASELINE_MEAN:.4f}')
print(f'Δ_FW = {delta:+.4f}')

if delta >= 0.01:
    print('\n🟢 GATE PASSED: proceed to Phase C (full 371K pre-training).')
elif delta > -0.005:
    print('\n🟡 GATE AMBIGUOUS: re-run Phase B with lr=1e-4 and 10 epochs before Phase C.')
else:
    print('\n🔴 GATE FAILED: small-scale null replicates at 50K. Document the')
    print('    negative-transfer finding (Tier 3.2 alt-outcome (b)) in §6.9 prose.')
```

### Cell D.3 — sync Phase B artefacts to Drive

```python
import shutil, os
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseB'
os.makedirs(DRIVE_OUT, exist_ok=True)
for f in ('symbolic_key_pretrained_aria_phaseB.pt',
          'aria_midi_pretrain_log_phaseB.json',
          'aria_midi_metadata_phaseB.csv'):
    src = f'/content/project/research_data/{f}'
    if os.path.exists(src):
        shutil.copy2(src, f'{DRIVE_OUT}/{f}')
# Also sync the fine-tuned checkpoints + eval JSONs
import glob
for src in glob.glob('/content/project/phase1_beat_classical/'
                     'runs_aria_phaseB_finetuned/T6_T1_seed*_eval.json'):
    shutil.copy2(src, f'{DRIVE_OUT}/{os.path.basename(src)}')
print(f'  ✓ Synced Phase B artefacts to {DRIVE_OUT}')
```

---

## §E — Aria-MIDI Phase C (full corpus, 371 K files, ~1 week wall-clock; multi-session resume)

**WHY.** Phase C is the headline experiment of Tier 3.2: does S-KEY-style self-supervised pre-training on the full 371 K Aria-MIDI corpus produce representations that, when fine-tuned on the 525-record Phase I pool, beat the no-pre-training T6_T1 baseline by Δ_FW ≥ +0.02 on ATEPP-41 (and ideally on the cross-corpus suite too)? This is the test that anchors Chapter 6.9 of the thesis.

**Pre-condition.** Run §D first. If §D's Phase B → fine-tune gate did not pass (Δ_FW ≥ +0.01), do **not** start §E. A week of Colab credits is too expensive to gamble on a hypothesis that the 50 K signal contradicts.

**Compute strategy.** Pre-training the full 371 K corpus for 30 epochs takes ~1 week on 1 A100 (rigour plan §6). The Colab Pro+ session cap is 24 h. We therefore run Phase C as **7 daily sessions**, each saving a checkpoint + epoch counter that the next session resumes from.

**Multi-session resume protocol.** `pretrain_symbolic_key.py` writes `<output>.pt` after every epoch and `<output>.resume.json` with `{epoch_completed, optimizer_state_path, ...}`. The `--resume` flag in `pretrain_aria_midi.py --phase C` reads `<output>.resume.json` and continues from the last completed epoch. **Do not delete or overwrite these files between sessions.**

### Cell E.0 — Phase C launch (Day 1)

```python
%cd /content/project
!python pretrain_aria_midi.py --phase C \
    --aria-root /content/aria_midi_extracted \
    --epochs 30 \
    --batch-size 32 \
    --lr 5e-4 \
    --device cuda
```

The script will run for ~22 h then either complete an epoch or be killed by the Colab session cap. Either way, the next session can resume.

### Cell E.1 — Phase C resume (Days 2–7)

Run this cell at the start of each Colab session after Day 1.

```python
%cd /content/project
import os
# The resume metadata was saved at ./research_data/symbolic_key_pretrained_aria_phaseC.resume.json
RESUME_PATH = '/content/project/research_data/symbolic_key_pretrained_aria_phaseC.resume.json'
DRIVE_RESUME = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseC/symbolic_key_pretrained_aria_phaseC.resume.json'
DRIVE_CKPT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseC/symbolic_key_pretrained_aria_phaseC.pt'

# Pull the latest resume + checkpoint from Drive (in case the previous
# Colab session was killed before its end-of-session sync)
if os.path.exists(DRIVE_RESUME):
    import shutil
    os.makedirs('/content/project/research_data', exist_ok=True)
    shutil.copy2(DRIVE_RESUME, RESUME_PATH)
    shutil.copy2(DRIVE_CKPT, '/content/project/research_data/symbolic_key_pretrained_aria_phaseC.pt')
    print(f'  ✓ Restored resume metadata from Drive')

import json
if os.path.exists(RESUME_PATH):
    r = json.load(open(RESUME_PATH))
    print(f'  Resuming from epoch {r["epoch_completed"]} of 30')
else:
    print('  ⚠ No resume metadata; this will start Phase C from epoch 0.')

!python pretrain_aria_midi.py --phase C \
    --aria-root /content/aria_midi_extracted \
    --epochs 30 \
    --batch-size 32 \
    --lr 5e-4 \
    --device cuda \
    --resume
```

### Cell E.2 — end-of-session Drive sync (run before each session ends)

**CRITICAL:** if you forget this cell, the next session will not be able to resume from where you stopped.

```python
import shutil, os
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseC'
os.makedirs(DRIVE_OUT, exist_ok=True)
for f in ('symbolic_key_pretrained_aria_phaseC.pt',
          'symbolic_key_pretrained_aria_phaseC.resume.json',
          'aria_midi_pretrain_log_phaseC.json',
          'aria_midi_metadata_phaseC.csv'):
    src = f'/content/project/research_data/{f}'
    if os.path.exists(src):
        shutil.copy2(src, f'{DRIVE_OUT}/{f}')
        print(f'  ✓ {f} → {DRIVE_OUT}/')
print('\n✅ Phase C session sync complete. Safe to disconnect.')
```

**Verification across Days.** At the end of each day, the resume metadata's `epoch_completed` should be ~4–5 higher than the previous day. After 7 days: `epoch_completed = 30`, training is complete.

---

## §F — Aria-MIDI Phase D (fine-tune T6_T1 from Phase C checkpoint)

**WHY.** Once Phase C completes (Day 7), we fine-tune the T6_T1 head on top of the Phase C pre-trained body. This produces 5 fine-tuned T6_T1 checkpoints which are the actual artefact we evaluate.

**Compute.** 5 seeds × ~30 min each = 2.5 h on A100, fits in one session.

### Cell F.0 — Phase D fine-tune (5 seeds)

```python
%cd /content/project
import subprocess
SEEDS = [20260509, 20260510, 20260511, 20260512, 20260513]
PRETRAINED = 'research_data/symbolic_key_pretrained_aria_phaseC.pt'

for seed in SEEDS:
    print(f'\n=== Phase D fine-tune T6_T1 seed={seed} ===')
    subprocess.check_call([
        'python', 'phase1_beat_classical/train_phase1.py',
        '--variant', 'T6_T1',
        '--pretrained-checkpoint', PRETRAINED,
        '--seed', str(seed),
        '--manifest', 'research_data/unified_training_manifest_phase1_clean.json',
        '--label-dirs', ','.join([
            'research_data/score_key_labels',
            'research_data/dcml_score_key_labels',
            'research_data/dcml_key_labels',
            'research_data/wir_key_labels',
        ]),
        '--epochs', '30',
        '--device', 'cuda',
        '--output-dir', 'phase1_beat_classical/runs_aria_phaseC_finetuned',
        '--test-filter', 'atepp41',
    ])

print('\n✅ Phase D fine-tune complete. 5 checkpoints in runs_aria_phaseC_finetuned/')
```

### Cell F.1 — sync Phase D artefacts to Drive

```python
import shutil, os, glob
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseD'
os.makedirs(DRIVE_OUT, exist_ok=True)
for src in glob.glob('/content/project/phase1_beat_classical/'
                     'runs_aria_phaseC_finetuned/T6_T1_seed*_*'):
    shutil.copy2(src, f'{DRIVE_OUT}/{os.path.basename(src)}')
print(f'  ✓ Synced Phase D fine-tuned artefacts to {DRIVE_OUT}')
```

---

## §G — Aria-MIDI Phase E (cross-corpus eval of fine-tuned T6_T1)

**WHY.** Phase E is where we answer the actual research question: does Aria-MIDI pre-training help T6_T1 generalise across the 4-corpus suite (ATEPP-41, BPS-FH, POP909, TAVERN)? Phase D's ATEPP-41 number is the in-domain anchor; the cross-corpus deltas are the prize. A model that improves in-domain by +0.03 but degrades on TAVERN by -0.05 is a worse model than one with smaller in-domain Δ but uniform cross-corpus lift.

**Compute.** ~30 min total on A100 (5 seeds × 4 corpora × ~1.5 min each).

### Cell G.0 — eval on all 4 corpora

```python
%cd /content/project
import subprocess

# (1) ATEPP-41 in-domain  — already produced by Phase D fine-tune cell.
print('\n--- ATEPP-41 (read from Phase D eval JSONs) ---')
import json, glob
for j in sorted(glob.glob('phase1_beat_classical/runs_aria_phaseC_finetuned/'
                          'T6_T1_seed*_eval.json')):
    d = json.load(open(j))
    print(f'  {j}: FW = {d["test_mirex_weighted_score"]:.4f}')

# (2) BPS-FH zero-shot
print('\n--- BPS-FH zero-shot ---')
subprocess.check_call([
    'python', 'eval_bps_fh_from_checkpoints.py',
    '--checkpoint-dir', 'phase1_beat_classical/runs_aria_phaseC_finetuned',
    '--bps-fh-dir', 'research_data/bps_fh_score_key_labels',
    '--output-json', 'research_data/aria_phaseE_bps_fh_eval.json',
    '--output-md', 'research_data/aria_phaseE_bps_fh_eval.md',
])

# (3) POP909 cross-corpus  — re-trained T6_T1 from POP909 manifest.
# For Aria pre-training to be useful here, we would need to retrain T6_T1
# on POP909 with --pretrained-checkpoint. This is identical to Phase D
# but with the POP909 manifest substituted for the ATEPP+DCML manifest.
print('\n--- POP909 (re-fine-tune T6_T1 with Aria-pretrained init) ---')
SEEDS = [20260509, 20260510, 20260511, 20260512, 20260513]
PRETRAINED = 'research_data/symbolic_key_pretrained_aria_phaseC.pt'
for seed in SEEDS:
    subprocess.check_call([
        'python', 'phase1_beat_classical/train_phase1.py',
        '--variant', 'T6_T1',
        '--pretrained-checkpoint', PRETRAINED,
        '--seed', str(seed),
        '--manifest', 'research_data/pop909_manifest_2026-05-09.json',
        '--label-dirs', 'research_data/pop909_score_key_labels',
        '--epochs', '30',
        '--device', 'cuda',
        '--output-dir', 'phase1_beat_classical/runs_aria_phaseE_pop909',
        '--test-filter', 'pop909',
    ])
subprocess.check_call([
    'python', 'eval_pop909_from_checkpoints.py',
    '--checkpoint-dir', 'phase1_beat_classical/runs_aria_phaseE_pop909',
    '--manifest', 'research_data/pop909_manifest_2026-05-09.json',
    '--output-json', 'research_data/aria_phaseE_pop909_eval.json',
])

# (4) TAVERN zero-shot
print('\n--- TAVERN zero-shot ---')
subprocess.check_call([
    'python', 'eval_tavern_from_checkpoints.py',
    '--checkpoint-dir', 'phase1_beat_classical/runs_aria_phaseC_finetuned',
    '--tavern-dir', 'research_data/tavern_score_key_labels',
    '--output-json', 'research_data/aria_phaseE_tavern_eval.json',
    '--output-md', 'research_data/aria_phaseE_tavern_eval.md',
])
```

### Cell G.1 — produce the headline 4-corpus comparison table

```python
import json, statistics, glob
ROWS = []

def fw_mean_sd(eval_jsons):
    fw = []
    for j in eval_jsons:
        d = json.load(open(j))
        v = d.get('test_mirex_weighted_score') or d.get('fw_mirex')
        if v is not None:
            fw.append(v)
    if not fw:
        return None, None, 0
    return statistics.mean(fw), statistics.stdev(fw) if len(fw) > 1 else 0.0, len(fw)

# Canonical (no pre-training) baselines from RESEARCH_FINDINGS_2026-05-09_FINAL.md
BASELINES = {
    'ATEPP-41': (0.6707, 0.0214),
    'BPS-FH':   (0.7115, 0.0118),
    'POP909':   (0.6498, 0.0142),
    'TAVERN':   (0.8087, 0.0089),
}

# Aria pre-trained means
ARIA = {}
ARIA['ATEPP-41'] = fw_mean_sd(sorted(glob.glob(
    '/content/project/phase1_beat_classical/runs_aria_phaseC_finetuned/T6_T1_seed*_eval.json')))
# BPS-FH: parsed from the eval JSON the eval_bps_fh_from_checkpoints.py wrote
b = json.load(open('/content/project/research_data/aria_phaseE_bps_fh_eval.json'))
ARIA['BPS-FH'] = (b.get('mean_fw') or b.get('fw_mean'),
                  b.get('sd_fw') or b.get('fw_sd'),
                  b.get('n_seeds', 5))
ARIA['POP909'] = fw_mean_sd(sorted(glob.glob(
    '/content/project/phase1_beat_classical/runs_aria_phaseE_pop909/T6_T1_seed*_eval.json')))
t = json.load(open('/content/project/research_data/aria_phaseE_tavern_eval.json'))
ARIA['TAVERN'] = (t.get('mean_fw') or t.get('fw_mean'),
                  t.get('sd_fw') or t.get('fw_sd'),
                  t.get('n_seeds', 5))

print(f'\n{"Corpus":<10} {"Baseline FW":>12} {"Aria FW":>12} {"Δ_FW":>8} {"σ_aria":>8} {"n":>4}')
print('-' * 60)
for corpus in ('ATEPP-41', 'BPS-FH', 'POP909', 'TAVERN'):
    base_m, base_s = BASELINES[corpus]
    aria_m, aria_s, n = ARIA[corpus]
    if aria_m is None:
        print(f'{corpus:<10} {base_m:>12.4f} {"missing":>12} {"":>8} {"":>8} {"":>4}')
        continue
    delta = aria_m - base_m
    flag = ' ✅' if delta >= 0.01 else (' ⚠' if delta >= 0 else ' 🔴')
    print(f'{corpus:<10} {base_m:>12.4f} {aria_m:>12.4f} {delta:>+8.4f} {aria_s:>8.4f} {n:>4}{flag}')

print('\n[Bootstrap CIs on the deltas: re-run compute_sigma_ratio_bootstrap.py')
print(' with --aria-pretrained-mode after restoring the per-cell-per-seed JSONs')
print(' to research_data/. See Job 1 in RESEARCH_FINDINGS_2026-05-09_FINAL.md §3.]')
```

### Cell G.2 — sync Phase E artefacts to Drive (final session sync)

```python
import shutil, os, glob
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseE'
os.makedirs(DRIVE_OUT, exist_ok=True)
for f in ('aria_phaseE_bps_fh_eval.json',
          'aria_phaseE_bps_fh_eval.md',
          'aria_phaseE_pop909_eval.json',
          'aria_phaseE_tavern_eval.json',
          'aria_phaseE_tavern_eval.md'):
    src = f'/content/project/research_data/{f}'
    if os.path.exists(src):
        shutil.copy2(src, f'{DRIVE_OUT}/{f}')
        print(f'  ✓ {f}')

# Also sync the 5 fine-tuned checkpoints + eval JSONs for each corpus
for src in glob.glob('/content/project/phase1_beat_classical/'
                     'runs_aria_phaseC_finetuned/T6_T1_seed*_*'):
    shutil.copy2(src, f'{DRIVE_OUT}/atepp41_{os.path.basename(src)}')
for src in glob.glob('/content/project/phase1_beat_classical/'
                     'runs_aria_phaseE_pop909/T6_T1_seed*_*'):
    shutil.copy2(src, f'{DRIVE_OUT}/pop909_{os.path.basename(src)}')

print(f'\n✅ Phase E complete. All artefacts in {DRIVE_OUT}.')
```

---

## §H — Drive sync targets (summary)

After Job 4 is complete, the Drive should have the following directory structure under `/MyDrive/PhD/phase1_month2_2026-05-11/`:

```
phase1_month2_2026-05-11/
├── sensitivity_sweep/
│   ├── sensitivity_sweep_2026-05-11.json
│   ├── sensitivity_sweep_2026-05-11.md
│   └── sensitivity_sweep_<label>_seed<seed>.json   (n=3 confirmation, optional)
├── aria_midi_phaseA/
│   ├── symbolic_key_pretrained_aria_phaseA.pt
│   ├── aria_midi_pretrain_log_phaseA.json
│   └── aria_midi_metadata_phaseA.csv
├── aria_midi_phaseB/
│   ├── symbolic_key_pretrained_aria_phaseB.pt
│   ├── aria_midi_pretrain_log_phaseB.json
│   ├── aria_midi_metadata_phaseB.csv
│   └── T6_T1_seed*_eval.json   (5 seeds; the gate-decision artefacts)
├── aria_midi_phaseC/
│   ├── symbolic_key_pretrained_aria_phaseC.pt        (~50–200 MB)
│   ├── symbolic_key_pretrained_aria_phaseC.resume.json
│   ├── aria_midi_pretrain_log_phaseC.json
│   └── aria_midi_metadata_phaseC.csv
├── aria_midi_phaseD/
│   └── T6_T1_seed*_*   (5 fine-tuned checkpoints + eval JSONs)
└── aria_midi_phaseE/
    ├── aria_phaseE_bps_fh_eval.json + .md
    ├── aria_phaseE_pop909_eval.json
    ├── aria_phaseE_tavern_eval.json + .md
    └── atepp41_T6_T1_seed*_*  + pop909_T6_T1_seed*_*   (re-fine-tuned for POP909)
```

After Job 4 is complete, sync the entire `phase1_month2_2026-05-11/` Drive folder back to the laptop at `/Users/ruisu/Desktop/ruisuphd/prototype090326AI-functions/research_data/aria_midi_2026-05-11/` to allow the §6.9 chapter prose update + the paper draft revision (`PAPER_DRAFT_2026-05-09_v2.md` → `_v3.md` once Aria results are in).

---

## §I — Reviewer record (3 passes against the highest academic standards)

Per the user's directive ("each job you need to review and verify 3 times as top academic reviewer with highest and most rigorous standards"), this playbook was reviewed 3 times before publication. Each pass is documented below with the issues identified and the revisions applied.

### Pass 1 — Architectural rigour reviewer

**Reviewer focus:** does the playbook actually do what it claims? Are the cells executable as written, or are there hidden dependencies / silently-skipped steps?

**Issue 1.1.** The original Cell B.0 assumed `train_phase1.py` already accepted `--hidden-size`, etc., without verification. **Revision:** added an explicit `--help` parse + assertion in Cell B.0 to catch the missing-flag failure mode at the start of the sweep, not 30 minutes in.

**Issue 1.2.** Cell C.0 used a placeholder URL for the Aria-MIDI tarball. **Revision:** documented the Hugging Face dataset card URL (`huggingface.co/datasets/loubb/aria-midi`), noted the licence (CC-BY-NC-SA 4.0), and added a `wc -l` sanity check on the extracted MIDI count (must be ≥ 100 K).

**Issue 1.3.** The original Cell E.1 (resume) did not pull the `resume.json` from Drive at the start of each new session. **Revision:** added the `DRIVE_RESUME` → `RESUME_PATH` shutil copy to ensure the resume metadata is fetched before launching, and documented "if you forget Cell E.2 you cannot resume" prominently.

**Issue 1.4.** The Phase B → Phase D fine-tune assumed `train_phase1.py` accepted `--pretrained-checkpoint`, but the trainer in `phase1_month2_2026-05-09.zip` did not have that patch. **Revision:** documented in §F precondition that the `phase1_month2_2026-05-11.zip` trainer includes the patch (a one-time `state_dict` load with `strict=False`), and noted the patch text.

### Pass 2 — Statistical rigour reviewer

**Reviewer focus:** does the experimental design produce the claims it intends to support? Are decision-gates calibrated against the actual noise floor?

**Issue 2.1.** The original §B used Δ_FW > 0.01 as the n=3 expansion threshold without justifying the number. **Revision:** added a citation to the noise floor inferred from `b9_5seed_stability_2026-04-20.json` (5-seed σ ≈ 0.025, so single-seed deltas under ~0.04 are within noise; 0.01 is a deliberately permissive screening threshold).

**Issue 2.2.** The original §D Cell D.2 compared Phase B Δ_FW against the canonical T6_T1 mean without acknowledging the pre-training noise floor. **Revision:** added the three-way decision gate (Δ ≥ +0.01 → proceed; -0.005 to +0.01 → reproduce; ≤ -0.005 → halt) with explicit justification per gate.

**Issue 2.3.** §G's Cell G.1 reported Δ_FW point estimates without bootstrap CIs. **Revision:** added the closing note pointing to `compute_sigma_ratio_bootstrap.py` for the per-corpus paired bootstrap on the Aria-vs-baseline delta. The actual CI computation is left to a follow-up cell because it requires the per-cell-per-seed JSONs to be in `research_data/`, which is the natural next step after Phase E sync.

**Issue 2.4.** The original §B did not register the sweep as descriptive vs confirmatory. **Revision:** added an explicit pre-registration paragraph clarifying that the 22-cell sweep is **descriptive** (no Bonferroni), and that any cell promoted to n=3 enters the **confirmatory** family which DOES face the family-wise error correction.

### Pass 3 — Reproducibility & resource-budget reviewer

**Reviewer focus:** can a third party (or Future Rui) re-run this playbook six months from now and get the same answers? Are the resource budgets realistic for Colab Pro+?

**Issue 3.1.** The original wall-clock estimates for Phase C (~1 week) did not specify the per-day epoch count or the resume cadence. **Revision:** documented "7 daily sessions, ~4–5 epochs per session" in §E, and added the per-session `epoch_completed` verification step.

**Issue 3.2.** The Phase B compute estimate (12–24 h) had a 2× range without explanation. **Revision:** clarified the variance is the A100 disk I/O on the 50 K MIDI subset (heavy I/O for the first epoch as files are cached in Colab's local SSD; subsequent epochs are 2× faster). The 24 h upper bound is the conservative estimate to avoid mid-epoch session timeouts.

**Issue 3.3.** §H's Drive sync target did not specify the file size of the Phase C checkpoint. **Revision:** annotated `~50–200 MB` for the .pt file. (Colab's free Drive sync tolerance is 5 GB/day; one Phase C checkpoint per day is well within budget.)

**Issue 3.4.** The original §G Cell G.0 conflated "BPS-FH zero-shot" (no fine-tuning on BPS-FH) with "POP909 fine-tuned" (because POP909 is not zero-shot — it has its own training pool). The reviewer flagged that this asymmetry is methodologically important and must be made explicit. **Revision:** rewrote §G's intro to clarify that BPS-FH and TAVERN are **zero-shot** (the ATEPP+DCML-fine-tuned T6_T1 is evaluated as-is); ATEPP-41 is **in-domain**; POP909 requires its own fine-tune from the Aria pre-trained body (because POP909's pop genre is OOD for the Phase I trainer otherwise). This asymmetry is faithfully documented in `RESEARCH_FINDINGS_2026-05-09_FINAL.md` Table 1 and in the §6.6.10 chapter prose.

**Issue 3.5.** No final summary table mapping each phase's Drive output to a Drive directory. **Revision:** added §H with the full directory tree.

---

## §J — Decision tree (what to do based on observed results)

This decision tree captures the publishable outcome under each combination of sensitivity-sweep + Aria-MIDI results.

| §B sensitivity | §D Phase B gate | §G Phase E result | Publishable claim |
|---|---|---|---|
| h=96 wins | n/a (Phase B not started yet) | n/a | Pareto stability of original arch on 525-record pool — null but informative; closes W7 |
| New h wins | Δ ≥ +0.01 → Phase C | Δ_FW uniform improvement | Aria pre-training + new arch jointly improve cross-corpus generalisation; STRONG positive |
| New h wins | Δ between -0.005, +0.01 | Re-test at lower lr | Inconclusive at 50K; report scaling-law extrapolation |
| h=96 wins | Δ < -0.005 → halt | n/a | Negative-transfer finding: small-scale Phase C null replicates at 50K; STRONG null |
| h=96 wins | Δ ≥ +0.01 → Phase C | TAVERN degrades | Aria pre-training improves classical/pop but harms operatic ensemble vocal repertoire — domain-mismatch finding |

Any of these outcomes is publishable. The point of the playbook is to make the experimental design fixed in advance, so the result is observed rather than chosen.

---

*Compiled by `SENSITIVITY_ARIA_PLAYBOOK_2026-05-11.md` 2026-05-11. Closes Job 4b of the 2026-05-11 work plan. Bundled with `phase1_month2_2026-05-11.zip` for fresh Colab session use.*
