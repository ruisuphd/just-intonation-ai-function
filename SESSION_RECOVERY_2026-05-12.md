# Session recovery + sensitivity sweep findings — 2026-05-12

**Author:** Rui Su
**Trigger:** the 2026-05-04 morning Colab session in `phd_training_030526(2) (1).ipynb` ran the sensitivity sweep to completion (✅ all 20 cells, ~10 h on T4) but Cell C.1 (Phase A pre-training) crashed with `pretrain_symbolic_key.py: No such file or directory`. Patch Cell 2 then crashed for the same reason.
**Root cause:** the zip-build script `build_phase1_month2_zip.py` shipped only the wrapper `pretrain_aria_midi.py` but not the underlying `pretrain_symbolic_key.py` it invokes via subprocess. **No GPU compute was wasted** — the failure was at the subprocess invocation step, before any training started.
**Status:** zip rebuilt locally with the missing file (35 top-level files now, 176 MB compressed, contents otherwise identical).

This document supplies (i) the headline findings from the sensitivity sweep that DID complete, (ii) the action checklist to recover the Phase A run, and (iii) a "fresh-session restart" playbook for any future reconnect.

---

## §1 — Sensitivity sweep findings (the part that DID succeed)

The 20-cell sweep (n=1 seed each, ~28–37 min per cell on T4) completed and is synced to Drive at `/MyDrive/PhD/phase1_month2_2026-05-11/sensitivity_sweep/`. Locally available at `phase1_month2_2026-05-11/sensitivity_sweep/sensitivity_sweep_2026-05-11.md`.

**Pre-registration reminder.** The sweep is **DESCRIPTIVE** at n=1. Cells with Δ_FW > 0.01 vs BASELINE are flagged for **n=3 confirmation** (which is the **CONFIRMATORY** family that DOES face Bonferroni correction). The single-seed numbers below are NOT the final result — they are the screening output that tells us where to spend the next round of compute.

**The 20 cells, sorted by descending Δ_FW (variant=BASELINE — no T6 / T1 / T2):**

| Rank | Param | Value | Label | FW MIREX | Δ vs BASELINE | best_epoch | Wall-clock |
|---:|---|---:|---|---:|---:|---:|---:|
| 1 | batch_size | 4 | batch04 | 0.6285 | **+0.0529** ⭐ | 12 | 25.5 min |
| 2 | batch_size | 32 | batch32 | 0.6233 | **+0.0478** ⭐ | 26 | 37.7 min |
| 3 | lr | 0.003 | lr3e-3 | 0.6217 | **+0.0461** ⭐ | 13 | 26.9 min |
| 4 | ens_beta | 0.99999 | ens_beta099999 | 0.6212 | **+0.0456** ⭐ | 12 | 26.3 min |
| 5 | hidden_size | 144 | h144 | 0.6162 | **+0.0406** ⭐ | 15 | 30.9 min |
| 6 | hidden_size | 192 | h192 | 0.6071 | **+0.0315** ⭐ | 16 | 33.3 min |
| 7 | dropout | 0.0 | dropout000 | 0.6052 | **+0.0296** ⭐ | 13 | 27.2 min |
| 8 | lr | 3e-4 | lr3e-4 | 0.5986 | **+0.0230** ⭐ | 26 | 35.5 min |
| 9 | batch_size | 16 | batch16 | 0.5915 | **+0.0159** ⭐ | 29 | 36.9 min |
| 10 | hidden_size | 48 | h048 | 0.5896 | **+0.0141** ⭐ | 25 | 34.3 min |
| 11 | dropout | 0.3 | dropout030 | 0.5827 | +0.0071 | 14 | 29.3 min |
| 12 | ens_beta | 0.9999 | ens_beta09999 | 0.5824 | +0.0068 | 14 | 29.3 min |
| 13 | dropout | 0.2 | dropout020 | 0.5787 | +0.0031 | 14 | 29.7 min |
| 14a | hidden_size | 96 | h096_BASELINE | 0.5756 | 0.0000 | 14 | 27.4 min |
| 14b | dropout | 0.1 | dropout010_BASELINE | 0.5756 | 0.0000 | 14 | 29.6 min |
| 14c | lr | 1e-3 | lr1e-3_BASELINE | 0.5756 | 0.0000 | 14 | 27.9 min |
| 14d | batch_size | 8 | batch08_BASELINE | 0.5756 | 0.0000 | 14 | 28.9 min |
| 14e | ens_beta | 0.999 | ens_beta0999_BASELINE | 0.5756 | 0.0000 | 14 | 29.6 min |
| 19 | ens_beta | 0.99 | ens_beta099 | 0.5755 | -0.0000 | 14 | 29.3 min |
| 20 | lr | 0.01 | lr1e-2 | 0.5400 | -0.0356 | 19 | 33.7 min |

⭐ = exceeds the +0.01 threshold for n=3 confirmation expansion.

### §1.1 — Headline observations

1. **Pareto STABILITY of `hidden_size=96` is REJECTED at n=1.** Both larger (h=144, h=192) AND smaller (h=48) variants beat h=96 at n=1, and h=144 (Δ +0.0406) is the largest of the three. Audit weakness W7 ("does h=192 help on the expanded 525-record pool?") is closer to "yes, h=144 maybe helps" than "no, stick with h=96".

2. **Batch-size effects are NON-MONOTONIC.** Both batch=4 (Δ +0.0529) AND batch=32 (Δ +0.0478) beat batch=8. This is unusual — it suggests the BASELINE-variant (no augmentation, no global PCP, no chord head) is unusually sensitive to batch dynamics. Don't draw architectural conclusions from this without n=3 confirmation.

3. **`lr=1e-2` is too high (Δ -0.0356).** Confirms the `1e-3` baseline LR is in the right ballpark. The mid-range `lr=3e-3` is the best at n=1 — worth confirming.

4. **`ens_beta=0.99999` has the largest single-parameter effect on the convergence rate** — best epoch arrives at epoch 12 (vs 14 for BASELINE). High β makes ENS class weights nearly uniform, which weakens the rare-class re-weighting. The fact that this WINS suggests the BASELINE ENS β=0.999 may be over-correcting on the small (525-record) pool.

5. **Dropout effects are noisy.** dropout=0.0 wins by Δ +0.0296 but dropout=0.2/0.3 are essentially indistinguishable from BASELINE. Likely an overfitting/regularisation question that needs n=3.

### §1.2 — Critical caveats

- **All numbers are n=1.** The B9 5-seed σ on ATEPP-41 is ≈ 0.025 FW MIREX (per `b9_5seed_stability_2026-04-20.json`). This means a single-seed Δ of 0.05 is roughly **2× the noise floor** — directionally suggestive but not formal. Cells like Δ +0.0141 (h=48) are within 1σ and **MUST** be confirmed at n=3.
- **The variant is BASELINE, not T6_T1.** These deltas don't directly translate to "what is the best architecture for cumulative ablation". A pessimistic reading: every BASELINE cell is in the noise floor and the cumulative-ablation gains (T6 +0.05, T1 +0.06) dominate any architectural reshuffling.
- **Same seed (20260509) for all 20 cells.** Cross-cell deltas are still meaningful (same train/val split), but per-cell point estimates can't be interpreted as "this is the truth".

### §1.3 — Recommended n=3 confirmation slate

Given limited GPU budget, prioritise the cells with biggest Δ that also have **architectural** rather than purely numerical implications:

**Tier A (architectural decisions for the chapter):**
- `h144` (Δ +0.0406): does increasing hidden size from 96 → 144 actually help on the expanded pool?
- `h192` (Δ +0.0315): is the original Phase B grid choice of h=96 simply wrong on the larger pool?
- `dropout000` (Δ +0.0296): are we over-regularising?

**Tier B (training-dynamics tuning):**
- `lr3e-3` (Δ +0.0461): is 1e-3 too low?
- `batch04` (Δ +0.0529) AND `batch32` (Δ +0.0478): the non-monotonicity needs >1 seed before we can interpret it.

**Tier C (de-prioritise — these are about ENS β only, less consequential for the headline story):**
- `ens_beta099999` (Δ +0.0456): even if this confirms, it doesn't change the main paper's claims.

**At n=3 confirmation, ~3 GPU-hours total on T4 (3 cells × 3 seeds × ~25 min each)** for Tier A. Tier B adds another ~3 hours. Total ~6 hours — fits in one Colab session.

---

## §2 — Phase A Drive sync state (incomplete — no .pt yet)

Synced to `/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseA/`:
- ✅ `aria_midi_metadata_phaseA.csv` (280 KB; 5 000 entries) — the wrapper produced this BEFORE the subprocess failed, so it's safe to reuse.
- ❌ `symbolic_key_pretrained_aria_phaseA.pt` — never created (subprocess died first).
- ❌ `aria_midi_pretrain_log_phaseA.json` — never created.

Phase A needs to be re-run from scratch in the next session, but the metadata CSV can be reused (saves the ~2 sec MIDI enumeration step).

---

## §3 — Action: rebuild the zip + re-upload to Drive

I have already rebuilt the laptop-local zip with `pretrain_symbolic_key.py` included.

```
phase1_month2_2026-05-11.zip
  35 top-level files (was 34; added pretrain_symbolic_key.py)
  176.2 MB compressed (unchanged)
  9 087 total files (was 9 086)
```

**Action for you:**
1. Upload the new `phase1_month2_2026-05-11.zip` from the laptop to Drive at `/MyDrive/PhD/phase1_month2_2026-05-11.zip`, **overwriting the existing file**.
2. Confirm the upload completes (Drive will show "Uploaded today" timestamp).
3. Open a fresh Colab session and follow the Session Restart Playbook in §4.

---

## §4 — Session Restart Playbook (every fresh Colab session)

Every time you reconnect to Colab (after a 24 h timeout, or just opening a fresh notebook), the runtime is **completely wiped** — no project files, no patched scripts, no Aria-MIDI extraction. You must re-mount + re-extract + re-patch + re-extract the Aria tarball.

### Order of cells on every fresh session

| Cell | Source | Purpose | T4 wall-clock |
|---|---|---|---|
| **1.** Cell A.0 | Playbook §A | Mount Drive, extract zip, install torch, verify scripts | ~3 min |
| **2.** Patch Cell 1 | `COLAB_FIX_CELLS_2026-05-11.md` §1 | Patch `train_phase1.py` (add `--hidden-size`, etc.) | ~5 sec |
| **3.** Patch Cell 2 | `COLAB_FIX_CELLS_2026-05-11.md` §2 | Patch `pretrain_symbolic_key.py` (add `--resume-from`) | ~5 sec |
| **4.** Patch Cell 3 | `COLAB_FIX_CELLS_2026-05-11.md` §3 | Patch `pretrain_aria_midi.py` (resume pass-through) | ~5 sec |
| **5a.** (only Phase A first time) Cell C.0 | Playbook §C | Download + extract Aria-MIDI tarball | ~1 min download + 3 min extract |
| **5b.** (Phase B/C resume sessions) — | Skip C.0; the tarball lives on Colab's `/content/` and is wiped on reconnect, so on **every** fresh session you need to re-download + extract. ~4 min sunk cost per session. | | |

### Then proceed to whichever phase is current

- **Phase A (smoke test, 1 session):** Cell C.1 → Cell C.2.
- **Phase B (50K, 2–3 sessions):** Cell D.0_T4 (resume) → train as long as session lives → Cell D.0_T4_SYNC before disconnect.
- **Phase B → fine-tune (1 session, ~6–10 h):** Cell D.1_T4 → Cell D.2_T4 (gate decision).
- **Phase C (371K, 15–20 sessions):** Cell E.0_T4 → train → Cell E.0_T4_SYNC before disconnect.
- **Phase D (5 seeds × 30 ep, 1 session, ~6–10 h):** Cell F.0_T4.
- **Phase E (cross-corpus eval, 1 session, ~1 h):** Playbook §G cells.

### Re-mount specifics for Drive

If Drive isn't mounted (e.g. restart of just the Python kernel), this single line re-mounts:
```python
from google.colab import drive; drive.mount('/content/drive', force_remount=True)
```
The `force_remount=True` flag is safe and idempotent. Use it at the top of any cell that touches `/content/drive/...`.

---

## §5 — Today's action checklist (in order)

To get back to where Cell C.1 should have left you yesterday:

1. **Upload the rebuilt zip.** Drag `phase1_month2_2026-05-11.zip` (176 MB, on your laptop at `/Users/ruisu/Desktop/ruisuphd/prototype090326AI-functions/phase1_month2_2026-05-11.zip`) into Drive, overwriting the existing one at `/MyDrive/PhD/phase1_month2_2026-05-11.zip`. Wait until Drive shows the new timestamp.

2. **Open a fresh Colab notebook.** Runtime → Change runtime type → T4 GPU.

3. **Run the four startup cells in order:** Cell A.0 (~3 min), Patch Cell 1, Patch Cell 2, Patch Cell 3. Verify each prints its `✅` line.

4. **Run Cell C.0** (download + extract Aria-MIDI; ~4 min). Should print `Found 371053 MIDI files`.

5. **Run Cell C.1** (Phase A pre-training; ~75–90 min on T4). This should NOW succeed because `pretrain_symbolic_key.py` is in the zip.

6. **Run Cell C.2** (Drive sync). Confirm `symbolic_key_pretrained_aria_phaseA.pt` and `aria_midi_pretrain_log_phaseA.json` appear in the Drive `aria_midi_phaseA/` directory.

7. **Verify the Phase A loss curve dropped monotonically across the 3 epochs** (look at the stdout from Cell C.1; if loss stays flat, the loader has a bug — DO NOT proceed to Phase B).

After Phase A succeeds, proceed to Phase B per the playbook §D / §5 of `COLAB_FIX_CELLS_2026-05-11.md` (the T4-aware multi-session resume cells).

---

## §6 — Optional: kick off the n=3 confirmation pass for the sensitivity sweep

If you want to spend an afternoon confirming the Tier A sweep findings (h144, h192, dropout000), here's a single Colab cell that runs ~3 GPU-hours of confirmation:

```python
# === n=3 CONFIRMATION: Tier A sensitivity-sweep cells ===
# Re-runs h144, h192, dropout000 at 3 NEW seeds each (excluding the original 20260509).
# Total: 3 cells × 3 seeds × ~25 min = ~3.5 GPU-h on T4.
%cd /content/project
import subprocess, json, os

CONFIRMATION_CELLS = [
    {'label': 'h144',       'overrides': ['--hidden-size', '144']},
    {'label': 'h192',       'overrides': ['--hidden-size', '192']},
    {'label': 'dropout000', 'overrides': ['--dropout', '0.0']},
]
SEEDS = [20260520, 20260521, 20260522]
OUTPUT_DIR = 'phase1_beat_classical/runs_sensitivity_n3'
os.makedirs(OUTPUT_DIR, exist_ok=True)
LABEL_DIRS = ','.join([
    'research_data/score_key_labels',
    'research_data/dcml_score_key_labels',
    'research_data/dcml_key_labels',
    'research_data/wir_key_labels',
])

results = []
for cell in CONFIRMATION_CELLS:
    for seed in SEEDS:
        run_id = f'{cell["label"]}_seed{seed}'
        eval_json = f'{OUTPUT_DIR}/{run_id}_eval.json'
        if os.path.exists(eval_json):
            print(f'  ⏭ {run_id} already exists — skipping')
            results.append({'label': cell['label'], 'seed': seed, 'eval_json': eval_json})
            continue
        print(f'\n=== {run_id} ===')
        cmd = [
            'python', 'phase1_beat_classical/train_phase1.py',
            '--variant', 'BASELINE',
            '--seed', str(seed),
            '--manifest', 'research_data/unified_training_manifest_phase1_clean.json',
            '--label-dirs', LABEL_DIRS,
            '--epochs', '30',
            '--device', 'cuda',
            '--output-dir', OUTPUT_DIR,
            '--test-filter', 'atepp41',
        ] + cell['overrides']
        subprocess.check_call(cmd)
        # The trainer writes <variant>_seed<seed>_eval.json; rename to <label>_seed<seed>_eval.json
        src = f'{OUTPUT_DIR}/BASELINE_seed{seed}_eval.json'
        if os.path.exists(src):
            os.rename(src, eval_json)
            results.append({'label': cell['label'], 'seed': seed, 'eval_json': eval_json})

# Summary
import statistics
print('\n\n' + '='*60)
print(f'{"Cell":<12} {"n":>3} {"FW mean":>10} {"FW σ":>10} {"vs h096_BL":>12}')
print('='*60)
H96_BASELINE = 0.5756  # from sensitivity_sweep_2026-05-11.md
for label in [c['label'] for c in CONFIRMATION_CELLS]:
    fws = []
    for r in results:
        if r['label'] == label:
            d = json.load(open(r['eval_json']))
            fws.append(d.get('test_mirex_weighted_score'))
    if not fws:
        continue
    m = statistics.mean(fws)
    sd = statistics.stdev(fws) if len(fws) > 1 else 0.0
    delta = m - H96_BASELINE
    print(f'{label:<12} {len(fws):>3} {m:>10.4f} {sd:>10.4f} {delta:>+12.4f}')

# Save
import json as _j
SUMMARY_JSON = '/content/project/research_data/sensitivity_n3_confirmation_2026-05-12.json'
_j.dump({'results': results, 'h96_baseline': H96_BASELINE},
        open(SUMMARY_JSON, 'w'), indent=2)
print(f'\n✓ {SUMMARY_JSON}')

# Sync to Drive
import shutil
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/sensitivity_sweep'
os.makedirs(DRIVE_OUT, exist_ok=True)
shutil.copy2(SUMMARY_JSON, f'{DRIVE_OUT}/{os.path.basename(SUMMARY_JSON)}')
for r in results:
    shutil.copy2(r['eval_json'], f'{DRIVE_OUT}/{os.path.basename(r["eval_json"])}')
print(f'✓ Synced to {DRIVE_OUT}')
```

This cell is **idempotent** — if a session times out mid-run, re-launching it skips already-completed seeds (via the `if os.path.exists(eval_json)` check). Total ~3.5 GPU-h, well within one T4 session.

After this completes, the formal claim about whether `h144`/`h192`/`dropout000` actually beat `h096_BASELINE` on the expanded pool can be made. Add a paired cluster bootstrap (using `compute_sigma_ratio_bootstrap.py` machinery on the per-piece fold-IDs) for the final 95 % CI.

---

*Compiled by `SESSION_RECOVERY_2026-05-12.md` 2026-05-12. Companion to `SENSITIVITY_ARIA_PLAYBOOK_2026-05-11.md` and `COLAB_FIX_CELLS_2026-05-11.md`.*
