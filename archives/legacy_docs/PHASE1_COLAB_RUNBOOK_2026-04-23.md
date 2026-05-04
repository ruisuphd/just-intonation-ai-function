# Phase I "Beat Classical" — Colab Runbook

**Date:** 2026-04-23 (amended 2026-04-25 for the Cell 1.5 leakage fix)
**Reconstructed:** 2026-04-25 from `RESEARCH_FINDINGS_TO_DATE_2026-04-25.md`.

---

## 1. What this runbook does

Walks the user through a full Phase I sweep on Colab (L4 or T4) using
the project zip the user uploaded to Drive. Five cells:

* **Cell 1** — mount Drive + unzip project + set up `/content/project`
* **Cell 1.5** — apply the 18-piece leakage fix to the manifest
  (NEW, post-2026-04-25)
* **Cell 2** — run the 6-variant Phase I sweep
* **Cell 3** — aggregate per-variant results into a summary
* **Cell 4** — copy results back to Drive

## 2. Cell 1 — environment setup

```python
from google.colab import drive
drive.mount('/content/drive')

import shutil, zipfile, os
PROJECT = '/content/project'
ZIP = '/content/drive/MyDrive/PhD_2026/phase1_2026-04-23.zip'

if not os.path.exists(PROJECT):
    os.makedirs(PROJECT, exist_ok=True)
    with zipfile.ZipFile(ZIP, 'r') as zf:
        zf.extractall(PROJECT)
    print(f'Extracted to {PROJECT}')

# Pin PyTorch (the project tested at this version)
!pip install -q torch==2.5.1 numpy==1.26.4

# Confirm
import torch
print(f'torch: {torch.__version__}, cuda: {torch.cuda.is_available()}')
```

Expected output:

```
Mounted at /content/drive
Extracted to /content/project
torch: 2.5.1, cuda: True
```

A pip warning about `torchaudio 2.10.0 / torchvision 0.25.0
require torch==2.10.0 but we pin torch==2.5.1` is **safe to ignore**
— Phase I doesn't import torchaudio or torchvision.

## 3. Cell 1.5 — apply leakage fix

**This cell is mandatory** if you uploaded the 2026-04-23 zip.
It rewrites the manifest to remove 18 DCML pieces that appear in
both train and val (the same composition labelled twice under
different sources).

See `COLAB_LEAKAGE_FIX_CELL_1_5.md` for the full block of code to
paste. Expected output ends with:

```
Patched colab_phase1_beat_classical.py: now uses unified_training_manifest_phase1_clean.json
```

If you skip this cell, the run will produce val MIREX inflated to
~0.787 instead of the expected ~0.62, and the checkpoint selection
will be biased.

## 4. Cell 2 — run the sweep

```python
%cd /content/project
!python colab_phase1_beat_classical.py
```

Expected runtime: ~3 hours on L4, ~10 hours on T4. The script
sweeps:

| # | Variant | What it adds |
|---|---|---|
| 1 | T0 | B9 baseline (sanity check on the Phase I manifest) |
| 2 | T6 | + ×12 transposition aug |
| 3 | T1 | + global PCP feature |
| 4 | T2 | + chord head |
| 5 | T6_T1 | T6 ∪ T1 |
| 6 | T6_T1_T2 | T6 ∪ T1 ∪ T2 (full stack) |

Each variant writes:

* `runs/phase1_<variant>_seed20260412.pt` — best-val checkpoint
* `runs/phase1_<variant>_seed20260412_results.json` — full history,
  best val MIREX, test FW MIREX, flags

## 5. Cell 3 — aggregate

```python
%cd /content/project
!python aggregate_phase1_results.py --result-dir runs/
```

Writes `research_data/phase1_summary.md` and
`research_data/phase1_summary.json` with the table:

| Variant | n seeds | val MIREX | test MIREX (FW) |
|---|---|---|---|
| T0 | 1 | … | … |
| T1 | 1 | … | … |
| ...

## 6. Cell 4 — copy results to Drive

```python
import shutil
shutil.copytree(
    '/content/project/runs',
    '/content/drive/MyDrive/PhD_2026/phase1_runs',
    dirs_exist_ok=True,
)
shutil.copy(
    '/content/project/research_data/phase1_summary.md',
    '/content/drive/MyDrive/PhD_2026/phase1_summary.md',
)
shutil.copy(
    '/content/project/research_data/phase1_summary.json',
    '/content/drive/MyDrive/PhD_2026/phase1_summary.json',
)
print('Done.')
```

## 7. Pre-flight checklist

Before running Cell 2:

- [ ] Colab runtime is **L4** (T4 works but is 3× slower)
- [ ] Cell 1 succeeded — torch.cuda.is_available() = True
- [ ] **Cell 1.5 ran** — `unified_training_manifest_phase1_clean.json`
      exists in `/content/project/research_data/`
- [ ] Drive has at least 5 GB free for the 6 checkpoints + result JSONs

## 8. Troubleshooting

* **"FileNotFoundError: train_phase1.py"** — Cell 1 didn't extract the
  zip correctly; check that `/content/project/train_phase1.py` exists.
* **"Variant T6 OOM"** — reduce batch size to 4 (`--batch-size 4`).
* **"Cell 1.5 reports 0 leaked pieces"** — the manifest may have
  already been patched in a previous session; verify with
  `wc -l /content/project/research_data/unified_training_manifest_phase1_clean.json`
  (~ 2,181 entries expected).
* **Colab disconnects mid-sweep** — the script writes per-variant
  results JSONs as it goes; you can re-run `colab_phase1_beat_classical.py`
  and it will skip variants whose JSON already exists.

## 9. Files

* `colab_phase1_beat_classical.py` — driver
* `aggregate_phase1_results.py` — summariser
* `train_phase1.py` — actual training (called per variant)
* `COLAB_LEAKAGE_FIX_CELL_1_5.md` — Cell 1.5 fix
* `phase1_2026-04-23.zip` — project archive on Drive
