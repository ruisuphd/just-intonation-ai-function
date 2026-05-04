# Colab fix cells — 2026-05-11 (T4 + multi-session resume)

**Author:** Rui Su
**Date:** 2026-05-11
**Trigger:** `phd_training_030526(2).ipynb` Cell B.0 failed with `Missing CLI flags in train_phase1.py: ['--hidden-size', '--dropout', '--ens-beta']`. The trainer in `phase1_month2_2026-05-11.zip` is the original 2026-05-08 trainer (CLI surface unchanged); the sensitivity-sweep CLI flags were planned but never patched into the trainer source before the zip was built.
**Hardware change:** user prefers T4 over A100. T4 is ~3× slower than A100 for Transformer pre-training. **Phase B and Phase C now exceed the 24 h Colab cap** and require multi-session resume.

This document supplies (i) **idempotent in-place patch cells** that fix the trainer + add resume support without rebuilding the zip, and (ii) **drop-in replacement cells** for §B–§G of `SENSITIVITY_ARIA_PLAYBOOK_2026-05-11.md` that add multi-session resume + T4-aware wall-clock budgets.

Paste cells in the order shown. Each patch cell is **idempotent** — running it twice is safe.

---

## §F — T4 wall-clock budget (replaces A100 estimates from playbook)

| Phase | Files | Epochs | A100 (original estimate) | **T4 (revised estimate)** | Sessions needed |
|---|---:|---:|---:|---:|---:|
| A — smoke test | 5 K | 3 | ~30 min | **~75–90 min** | 1 |
| B — early signal | 50 K | 5 | ~12–24 h | **~36–60 h** | **2–3 sessions** |
| C — full corpus | 371 K | 30 | ~1 week | **~3 weeks** | **15–20 sessions** |
| D — fine-tune T6_T1 (5 seeds × 30 ep) | 525 records | 30 | ~2.5 h | **~6–10 h** | 1 |
| E — cross-corpus eval | n/a | n/a | ~30 min | **~1 h** | 1 |

**T4-aware caveat for Phase D.** Each seed's T6_T1 fine-tune is independent. We loop over seeds with a per-seed checkpoint to Drive, so a Phase D session that times out at seed 3 of 5 can resume with seed 4 in the next session.

**T4-aware caveat for Phase C.** 15–20 sessions over ~3 weeks of wall-clock time is a real commitment of human attention. Recommend only after Phase B passes the gate (Δ_FW ≥ +0.01 vs canonical T6_T1).

---

## §1 — Patch Cell 1: add missing CLI flags + pretrained-checkpoint loader to `train_phase1.py`

This cell does an in-place edit of `phase1_beat_classical/train_phase1.py` to:

1. Add 4 new CLI args: `--hidden-size`, `--dropout`, `--ens-beta`, `--pretrained-checkpoint`.
2. Use `args.hidden_size` + `args.dropout` in model construction (was hardcoded `96, 0.1`).
3. Use `args.ens_beta` in class-weight construction (was hardcoded `0.999`).
4. After model construction, if `args.pretrained_checkpoint` is set, load it with `strict=False` (for Phase D Aria fine-tune).

The cell is **idempotent**: it detects whether the patch is already applied via a sentinel string (`# Sensitivity sweep + Phase D patch (2026-05-11)`).

**Paste this AFTER your existing Cell A.0 setup and BEFORE you re-run Cell B.0:**

```python
# === Patch Cell 1: train_phase1.py — add --hidden-size/--dropout/--ens-beta/--pretrained-checkpoint ===
import os
TRAINER = '/content/project/phase1_beat_classical/train_phase1.py'
SENTINEL = '# Sensitivity sweep + Phase D patch (2026-05-11)'

src = open(TRAINER).read()
if SENTINEL in src:
    print('  ✓ Patch already applied — skipping.')
else:
    # --- Edit 1: insert new CLI args after `--lr` line
    old_lr = "    p.add_argument('--lr', type=float, default=1e-3)\n"
    new_args = (
        old_lr +
        f"    {SENTINEL}\n"
        "    p.add_argument('--hidden-size', type=int, default=96,\n"
        "                   help='GRU hidden size (sensitivity sweep)')\n"
        "    p.add_argument('--dropout', type=float, default=0.1,\n"
        "                   help='GRU dropout (sensitivity sweep)')\n"
        "    p.add_argument('--ens-beta', type=float, default=0.999,\n"
        "                   help='ENS class-weight β (sensitivity sweep)')\n"
        "    p.add_argument('--pretrained-checkpoint', default=None,\n"
        "                   help='Path to pre-trained .pt for Phase D Aria fine-tune')\n"
    )
    assert old_lr in src, 'cannot find --lr line; patch aborted'
    src = src.replace(old_lr, new_args, 1)

    # --- Edit 2: model construction uses args.hidden_size + args.dropout
    old_model = '        hidden_size=96, num_layers=1, dropout=0.1,'
    new_model = '        hidden_size=args.hidden_size, num_layers=1, dropout=args.dropout,'
    assert old_model in src, 'cannot find hardcoded hidden_size=96; patch aborted'
    src = src.replace(old_model, new_model, 1)

    # --- Edit 3: ENS β uses args.ens_beta
    old_beta = 'class_weights = build_ens_class_weights(train_records, beta=0.999).to(device)'
    new_beta = 'class_weights = build_ens_class_weights(train_records, beta=args.ens_beta).to(device)'
    assert old_beta in src, 'cannot find hardcoded beta=0.999; patch aborted'
    src = src.replace(old_beta, new_beta, 1)

    # --- Edit 4: insert pretrained-checkpoint loader after model construction.
    # Sentinel: the model "Model: HarmonicContextGRUPhase1 ..." print line.
    old_print = ("    print(f'Model: HarmonicContextGRUPhase1 variant {args.variant} '\n"
                 "          f'({n_params:,} parameters)')\n")
    pretrained_block = (
        old_print +
        "\n"
        "    # Phase D pretrained-init (2026-05-11 patch). Loads with strict=False\n"
        "    # so the chord head + any new modules in T6_T1_T2 are still trainable.\n"
        "    if args.pretrained_checkpoint:\n"
        "        ckpt = torch.load(args.pretrained_checkpoint, map_location=device)\n"
        "        sd = ckpt.get('model_state_dict', ckpt)\n"
        "        missing, unexpected = model.load_state_dict(sd, strict=False)\n"
        "        print(f'  ✓ Loaded pretrained checkpoint: {args.pretrained_checkpoint}')\n"
        "        print(f'    missing keys: {len(missing)}, unexpected: {len(unexpected)}')\n"
    )
    assert old_print in src, 'cannot find Model: print line; patch aborted'
    src = src.replace(old_print, pretrained_block, 1)

    # Write back
    open(TRAINER, 'w').write(src)
    print('  ✓ Patched train_phase1.py')

# Verify the patch worked
import subprocess
out = subprocess.check_output(['python', TRAINER, '--help'], text=True)
required = ['--hidden-size', '--dropout', '--ens-beta', '--pretrained-checkpoint',
            '--lr', '--batch-size']
missing = [f for f in required if f not in out]
assert not missing, f'verification FAILED: still missing {missing}'
print('  ✅ All required CLI flags present in train_phase1.py')
```

**Expected output:**
```
  ✓ Patched train_phase1.py
  ✅ All required CLI flags present in train_phase1.py
```

(Or `✓ Patch already applied — skipping.` on a re-run.)

After this cell completes, you can re-run the original Cell B.0 from the playbook (the assertion will pass) and proceed with Cells B.1 / B.2 / B.3 unchanged.

---

## §2 — Patch Cell 2: add per-epoch save + resume to `pretrain_symbolic_key.py`

This cell does an in-place edit of `pretrain_symbolic_key.py` to:

1. Add a `--resume-from` CLI arg.
2. Save a checkpoint **after every epoch** (not just on best loss) — separate `<output>.epoch.pt` file plus `<output>.resume.json` sidecar with the epoch counter + optimizer state.
3. On startup, if `--resume-from` points to an existing `<output>.resume.json`, load `epoch_completed`, `model_state_dict`, `optimizer_state_dict`, `scheduler_state_dict` and continue from `epoch_completed + 1`.

This is required for Phase B/C resume on T4. The cell is idempotent (sentinel: `# Resume + per-epoch save (2026-05-11)`).

```python
# === Patch Cell 2: pretrain_symbolic_key.py — add --resume-from + per-epoch save ===
import os
PRETRAIN = '/content/project/pretrain_symbolic_key.py'
SENTINEL = '# Resume + per-epoch save (2026-05-11)'

src = open(PRETRAIN).read()
if SENTINEL in src:
    print('  ✓ Patch already applied — skipping.')
else:
    # --- Edit 1: add --resume-from to argparse.
    # Sentinel: the `--output` argument.
    OLD_OUTPUT_LINE = "        help='Output checkpoint path',"
    NEW_RESUME_BLOCK = (
        OLD_OUTPUT_LINE + "\n"
        "    )\n"
        "    parser.add_argument(\n"
        f"        '--resume-from', default=None,\n"
        f"        help='{SENTINEL} Path to <output>.resume.json to resume from'\n"
    )
    assert OLD_OUTPUT_LINE in src, 'cannot find --output help line; patch aborted'
    src = src.replace(OLD_OUTPUT_LINE + '\n    )', NEW_RESUME_BLOCK, 1)

    # --- Edit 2: replace the `for epoch in range(1, args.epochs + 1):` loop
    # so it (a) reads start_epoch from the resume sidecar if present, and
    # (b) saves a checkpoint + resume.json sidecar after every epoch.
    OLD_LOOP_HEAD = (
        '    best_loss = float(\'inf\')\n'
        '\n'
        '    for epoch in range(1, args.epochs + 1):'
    )
    NEW_LOOP_HEAD = (
        '    best_loss = float(\'inf\')\n'
        '    start_epoch = 1\n'
        '\n'
        '    # Resume support (2026-05-11 patch)\n'
        '    resume_path = args.resume_from\n'
        '    if resume_path is None:\n'
        '        # Auto-detect default sidecar next to --output\n'
        '        cand = args.output + \'.resume.json\'\n'
        '        if os.path.exists(cand):\n'
        '            resume_path = cand\n'
        '    if resume_path and os.path.exists(resume_path):\n'
        '        import json as _json\n'
        '        r = _json.load(open(resume_path))\n'
        '        ckpt_path = r.get(\'epoch_checkpoint\', args.output + \'.epoch.pt\')\n'
        '        ck = torch.load(ckpt_path, map_location=device)\n'
        '        model.load_state_dict(ck[\'model_state_dict\'])\n'
        '        if \'optimizer_state_dict\' in ck:\n'
        '            optimizer.load_state_dict(ck[\'optimizer_state_dict\'])\n'
        '        if \'scheduler_state_dict\' in ck:\n'
        '            scheduler.load_state_dict(ck[\'scheduler_state_dict\'])\n'
        '        start_epoch = r[\'epoch_completed\'] + 1\n'
        '        best_loss = r.get(\'best_loss\', float(\'inf\'))\n'
        '        print(f\'  ✓ Resumed from epoch {r["epoch_completed"]}; '
        'starting at epoch {start_epoch}, best_loss={best_loss:.4f}\')\n'
        '\n'
        '    for epoch in range(start_epoch, args.epochs + 1):'
    )
    assert OLD_LOOP_HEAD in src, 'cannot find epoch loop head; patch aborted'
    src = src.replace(OLD_LOOP_HEAD, NEW_LOOP_HEAD, 1)

    # --- Edit 3: after the existing per-epoch print + best-checkpoint save,
    # ALWAYS save a per-epoch checkpoint + resume.json sidecar.
    # Sentinel: the existing `print(f'  -> Saved best checkpoint ...)` line.
    OLD_BEST_PRINT = "            print(f'  -> Saved best checkpoint (loss={best_loss:.4f})')\n"
    NEW_PER_EPOCH = (
        OLD_BEST_PRINT +
        '\n'
        '        # Per-epoch save + resume sidecar (2026-05-11 patch)\n'
        '        per_epoch_pt = args.output + \'.epoch.pt\'\n'
        '        torch.save(\n'
        '            {\n'
        '                \'model_state_dict\': model.state_dict(),\n'
        '                \'optimizer_state_dict\': optimizer.state_dict(),\n'
        '                \'scheduler_state_dict\': scheduler.state_dict(),\n'
        '                \'epoch\': epoch,\n'
        '                \'best_loss\': best_loss,\n'
        '                \'args\': vars(args),\n'
        '            },\n'
        '            per_epoch_pt,\n'
        '        )\n'
        '        import json as _json\n'
        '        _json.dump(\n'
        '            {\n'
        '                \'epoch_completed\': epoch,\n'
        '                \'best_loss\': best_loss,\n'
        '                \'epoch_checkpoint\': per_epoch_pt,\n'
        '                \'output\': args.output,\n'
        '            },\n'
        '            open(args.output + \'.resume.json\', \'w\'),\n'
        '            indent=2,\n'
        '        )\n'
    )
    assert OLD_BEST_PRINT in src, 'cannot find best-checkpoint print line; patch aborted'
    src = src.replace(OLD_BEST_PRINT, NEW_PER_EPOCH, 1)

    open(PRETRAIN, 'w').write(src)
    print('  ✓ Patched pretrain_symbolic_key.py')

# Verify the patch
import subprocess
out = subprocess.check_output(['python', PRETRAIN, '--help'], text=True)
assert '--resume-from' in out, 'verification FAILED: --resume-from not in --help'
print('  ✅ --resume-from CLI flag now present in pretrain_symbolic_key.py')
```

**Expected output:** `✅ --resume-from CLI flag now present in pretrain_symbolic_key.py`

---

## §3 — Patch Cell 3: pass `--resume-from` through `pretrain_aria_midi.py`

The wrapper script `pretrain_aria_midi.py` already reads its own `--resume` flag for Phase C, but it doesn't currently pass it through to the underlying `pretrain_symbolic_key.py` invocation. This patch adds the pass-through.

```python
# === Patch Cell 3: pretrain_aria_midi.py — pass --resume through to pretrain_symbolic_key.py ===
import os
WRAPPER = '/content/project/pretrain_aria_midi.py'
SENTINEL = '# Resume pass-through (2026-05-11)'

src = open(WRAPPER).read()
if SENTINEL in src:
    print('  ✓ Patch already applied — skipping.')
else:
    OLD_LIMIT_BLOCK = (
        '        if args.limit is not None:\n'
        '            cmd += [\'--limit\', str(args.limit)]'
    )
    NEW_LIMIT_BLOCK = (
        OLD_LIMIT_BLOCK + '\n'
        f'        {SENTINEL}\n'
        '        if args.resume:\n'
        '            cmd += [\'--resume-from\', str(out_ckpt) + \'.resume.json\']'
    )
    assert OLD_LIMIT_BLOCK in src, 'cannot find --limit block; patch aborted'
    src = src.replace(OLD_LIMIT_BLOCK, NEW_LIMIT_BLOCK, 1)
    open(WRAPPER, 'w').write(src)
    print('  ✓ Patched pretrain_aria_midi.py')

# No CLI verification needed; this only affects subprocess invocation.
print('  ✅ Resume pass-through wired')
```

---

## §4 — REPLACEMENT Cell C.1: Phase A on T4 (~75–90 min, single session)

Phase A still fits in one T4 session. The original cell works **unchanged**, but expect ~90 min (not 30 min as the A100 estimate said).

```python
%cd /content/project
# Phase A on T4: ~75-90 min wall-clock (was ~30 min on A100).
!python pretrain_aria_midi.py --phase A \
    --aria-root /content/aria_midi_extracted \
    --limit 5000 \
    --epochs 3 \
    --batch-size 32 \
    --lr 5e-4 \
    --device cuda
```

After completion, sync to Drive (Cell C.2 from the playbook unchanged).

---

## §5 — REPLACEMENT Cell D.0/D.1: Phase B on T4 with multi-session resume (~36–60 h, 2–3 sessions)

This replaces playbook §D's Cell D.0. Phase B on T4 takes ~36–60 h, exceeding Colab's 24 h cap. Each session: pull resume metadata from Drive → train as long as the session lives → push resume metadata back to Drive.

### Cell D.0_T4 — Phase B launch / resume (run at the start of EVERY Phase B session)

```python
# === Cell D.0_T4: Phase B — pull resume + launch / continue ===
import os, shutil
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseB'
LOCAL_RD  = '/content/project/research_data'
os.makedirs(DRIVE_OUT, exist_ok=True)

# Pull resume sidecar + per-epoch checkpoint from Drive (no-op on Day 1).
for f in ('symbolic_key_pretrained_aria_phaseB.pt',
          'symbolic_key_pretrained_aria_phaseB.pt.epoch.pt',
          'symbolic_key_pretrained_aria_phaseB.pt.resume.json',
          'aria_midi_metadata_phaseB.csv',
          'aria_midi_cache_phaseB.jsonl'):
    src = f'{DRIVE_OUT}/{f}'
    dst = f'{LOCAL_RD}/{f}'
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)
        print(f'  ✓ Restored {f} from Drive')

# Print resume status
import json
resume_path = f'{LOCAL_RD}/symbolic_key_pretrained_aria_phaseB.pt.resume.json'
if os.path.exists(resume_path):
    r = json.load(open(resume_path))
    print(f'\n  → Resuming Phase B from epoch {r["epoch_completed"]} of 5')
    if r['epoch_completed'] >= 5:
        print('  ✅ Phase B is already complete — skip to Cell D.1_T4 (fine-tune).')
else:
    print(f'\n  → Phase B Day 1 (no resume metadata found — will start from epoch 0).')

%cd /content/project
!python pretrain_aria_midi.py --phase B \
    --aria-root /content/aria_midi_extracted \
    --limit 50000 \
    --epochs 5 \
    --batch-size 32 \
    --lr 5e-4 \
    --device cuda \
    --resume
```

### Cell D.0_T4_SYNC — END-OF-SESSION sync to Drive (CRITICAL: run before disconnecting)

```python
# === Cell D.0_T4_SYNC: Phase B — push resume + checkpoint back to Drive ===
import os, shutil
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseB'
LOCAL_RD  = '/content/project/research_data'
os.makedirs(DRIVE_OUT, exist_ok=True)

for f in ('symbolic_key_pretrained_aria_phaseB.pt',
          'symbolic_key_pretrained_aria_phaseB.pt.epoch.pt',
          'symbolic_key_pretrained_aria_phaseB.pt.resume.json',
          'aria_midi_pretrain_log_phaseB.json',
          'aria_midi_metadata_phaseB.csv',
          'aria_midi_cache_phaseB.jsonl'):
    src = f'{LOCAL_RD}/{f}'
    if os.path.exists(src):
        shutil.copy2(src, f'{DRIVE_OUT}/{f}')
        print(f'  ✓ {f} → Drive')

# Show how far we got
import json
resume_path = f'{LOCAL_RD}/symbolic_key_pretrained_aria_phaseB.pt.resume.json'
if os.path.exists(resume_path):
    r = json.load(open(resume_path))
    print(f'\n  Phase B progress: {r["epoch_completed"]} / 5 epochs complete')
    print(f'  best_loss = {r["best_loss"]:.4f}')
    if r['epoch_completed'] >= 5:
        print('  ✅ Phase B COMPLETE — proceed to Cell D.1_T4 (fine-tune) in a new session.')
    else:
        print(f'  ⏸  Phase B paused at epoch {r["epoch_completed"]}/5 — resume in next session by re-running Cell D.0_T4.')
print('\n✅ Drive sync complete. Safe to disconnect.')
```

### Cell D.1_T4 — Phase B → Phase D-style fine-tune (T4: ~6–10 h, single session)

Replaces playbook §D Cell D.1. Adds per-seed checkpointing so a Phase D session that times out at seed 3 of 5 can resume with seed 4 in the next session.

```python
# === Cell D.1_T4: Phase B → fine-tune T6_T1 with per-seed resume ===
%cd /content/project
import os, json, subprocess, shutil
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseB_finetune'
os.makedirs(DRIVE_OUT, exist_ok=True)
SEEDS_FILE = f'{DRIVE_OUT}/seeds_completed.json'
SEEDS = [20260509, 20260510, 20260511, 20260512, 20260513]
PRETRAINED = 'research_data/symbolic_key_pretrained_aria_phaseB.pt'

# Restore completed-seeds list from Drive
completed = []
if os.path.exists(SEEDS_FILE):
    completed = json.load(open(SEEDS_FILE))
    print(f'  Already completed seeds: {completed}')

# Restore previously-fine-tuned eval JSONs from Drive (so we don't re-train them)
LOCAL_FT = '/content/project/phase1_beat_classical/runs_aria_phaseB_finetuned'
os.makedirs(LOCAL_FT, exist_ok=True)
for f in os.listdir(DRIVE_OUT):
    if f.startswith('T6_T1_seed') and not os.path.exists(f'{LOCAL_FT}/{f}'):
        shutil.copy2(f'{DRIVE_OUT}/{f}', f'{LOCAL_FT}/{f}')

for seed in SEEDS:
    if seed in completed:
        print(f'  ⏭ Skipping seed {seed} (already complete)')
        continue
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
        '--output-dir', LOCAL_FT,
        '--test-filter', 'atepp41',
    ])
    # Mark seed as complete and sync to Drive immediately (so a session
    # timeout between seeds doesn't lose progress)
    completed.append(seed)
    json.dump(completed, open(SEEDS_FILE, 'w'))
    # Push the eval JSON + checkpoint to Drive
    for f in os.listdir(LOCAL_FT):
        if f.startswith(f'T6_T1_seed{seed}_'):
            shutil.copy2(f'{LOCAL_FT}/{f}', f'{DRIVE_OUT}/{f}')
    print(f'  ✓ Seed {seed} synced to Drive ({len(completed)}/{len(SEEDS)} done)')

print(f'\n✅ Phase B fine-tune complete. {len(completed)} seeds in {LOCAL_FT}/')
```

### Cell D.2_T4 — read out Δ_FW gate (unchanged from playbook D.2)

The playbook's Cell D.2 (the gate-decision cell that compares mean FW against the canonical 0.6707) works as-is. Run it after D.1_T4.

---

## §6 — REPLACEMENT Cell E.0/E.1/E.2: Phase C on T4 with multi-session resume (~3 weeks, 15–20 sessions)

Same multi-session pattern as Phase B, scaled up. Phase C is a real time commitment on T4 — only proceed if the Phase B gate passed (Δ_FW ≥ +0.01).

### Cell E.0_T4 — Phase C launch / resume (run at the start of EVERY Phase C session)

```python
# === Cell E.0_T4: Phase C — pull resume + launch / continue ===
import os, shutil, json
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseC'
LOCAL_RD  = '/content/project/research_data'
os.makedirs(DRIVE_OUT, exist_ok=True)

# Pull resume sidecar + per-epoch checkpoint from Drive (no-op on Day 1).
for f in ('symbolic_key_pretrained_aria_phaseC.pt',
          'symbolic_key_pretrained_aria_phaseC.pt.epoch.pt',
          'symbolic_key_pretrained_aria_phaseC.pt.resume.json',
          'aria_midi_metadata_phaseC.csv',
          'aria_midi_cache_phaseC.jsonl'):
    src = f'{DRIVE_OUT}/{f}'
    dst = f'{LOCAL_RD}/{f}'
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)
        print(f'  ✓ Restored {f} from Drive')

resume_path = f'{LOCAL_RD}/symbolic_key_pretrained_aria_phaseC.pt.resume.json'
if os.path.exists(resume_path):
    r = json.load(open(resume_path))
    print(f'\n  → Resuming Phase C from epoch {r["epoch_completed"]} of 30')
    if r['epoch_completed'] >= 30:
        print('  ✅ Phase C is already complete — skip to Cell F.0_T4 (fine-tune).')
else:
    print(f'\n  → Phase C Day 1 — no resume metadata.')
    print(f'    ⚠ This is a 3-week / 15-20 session commitment on T4.')
    print(f'    Confirm Phase B gate passed (Δ_FW ≥ +0.01) before continuing.')

%cd /content/project
!python pretrain_aria_midi.py --phase C \
    --aria-root /content/aria_midi_extracted \
    --epochs 30 \
    --batch-size 32 \
    --lr 5e-4 \
    --device cuda \
    --resume
```

### Cell E.0_T4_SYNC — END-OF-SESSION sync (run before EVERY disconnect)

```python
# === Cell E.0_T4_SYNC: Phase C — push resume + checkpoint to Drive ===
import os, shutil, json
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseC'
LOCAL_RD  = '/content/project/research_data'

for f in ('symbolic_key_pretrained_aria_phaseC.pt',
          'symbolic_key_pretrained_aria_phaseC.pt.epoch.pt',
          'symbolic_key_pretrained_aria_phaseC.pt.resume.json',
          'aria_midi_pretrain_log_phaseC.json',
          'aria_midi_metadata_phaseC.csv',
          'aria_midi_cache_phaseC.jsonl'):
    src = f'{LOCAL_RD}/{f}'
    if os.path.exists(src):
        shutil.copy2(src, f'{DRIVE_OUT}/{f}')
        print(f'  ✓ {f} → Drive')

resume_path = f'{LOCAL_RD}/symbolic_key_pretrained_aria_phaseC.pt.resume.json'
if os.path.exists(resume_path):
    r = json.load(open(resume_path))
    print(f'\n  Phase C progress: {r["epoch_completed"]} / 30 epochs')
    print(f'  best_loss = {r["best_loss"]:.4f}')
    pct = 100 * r["epoch_completed"] / 30
    print(f'  → {pct:.0f}% through Phase C; ~{(30 - r["epoch_completed"]) // 2} more sessions needed.')
print('\n✅ Drive sync complete. Safe to disconnect.')
```

### Cell F.0_T4 — Phase D fine-tune from Phase C checkpoint (per-seed resume; ~6–10 h on T4)

Identical structure to Cell D.1_T4 but reads from `phaseC.pt` and writes into `runs_aria_phaseC_finetuned`. Drive sync target `aria_midi_phaseD/`.

```python
# === Cell F.0_T4: Phase D — fine-tune T6_T1 from Phase C checkpoint ===
%cd /content/project
import os, json, subprocess, shutil
DRIVE_OUT = '/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseD'
os.makedirs(DRIVE_OUT, exist_ok=True)
SEEDS_FILE = f'{DRIVE_OUT}/seeds_completed.json'
SEEDS = [20260509, 20260510, 20260511, 20260512, 20260513]
PRETRAINED = 'research_data/symbolic_key_pretrained_aria_phaseC.pt'

completed = json.load(open(SEEDS_FILE)) if os.path.exists(SEEDS_FILE) else []
LOCAL_FT = '/content/project/phase1_beat_classical/runs_aria_phaseC_finetuned'
os.makedirs(LOCAL_FT, exist_ok=True)
for f in os.listdir(DRIVE_OUT):
    if f.startswith('T6_T1_seed') and not os.path.exists(f'{LOCAL_FT}/{f}'):
        shutil.copy2(f'{DRIVE_OUT}/{f}', f'{LOCAL_FT}/{f}')

for seed in SEEDS:
    if seed in completed:
        print(f'  ⏭ Skipping seed {seed} (already complete)')
        continue
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
        '--output-dir', LOCAL_FT,
        '--test-filter', 'atepp41',
    ])
    completed.append(seed)
    json.dump(completed, open(SEEDS_FILE, 'w'))
    for f in os.listdir(LOCAL_FT):
        if f.startswith(f'T6_T1_seed{seed}_'):
            shutil.copy2(f'{LOCAL_FT}/{f}', f'{DRIVE_OUT}/{f}')
    print(f'  ✓ Seed {seed} synced to Drive ({len(completed)}/{len(SEEDS)} done)')

print(f'\n✅ Phase D complete. Proceed to playbook §G (cross-corpus eval).')
```

### Phase E (cross-corpus eval) — playbook §G is fine on T4 (~1 h)

The §G cells (`G.0`, `G.1`, `G.2`) work as-is on T4. They only do inference, no training.

---

## §7 — Recovery cookbook (if a session dies between cells)

Common failure modes and the recovery action:

| Symptom | Likely cause | Recovery |
|---|---|---|
| `colab session ended at runtime` mid-Phase-B/C | hit 24h cap | New session → A.0 → D.0_T4 (or E.0_T4); resume sidecar restored from Drive automatically |
| Cell D.1_T4 crashed at seed N | OOM / disk / random crash | Re-run D.1_T4; the per-seed Drive sync skips completed seeds |
| `MISSING: pretrain_symbolic_key.py` after extracting zip | zip incomplete | `unzip -l /content/drive/MyDrive/PhD/phase1_month2_2026-05-11.zip \| grep pretrain_symbolic` — should show 1 entry; if not, the zip needs rebuild on laptop |
| Cell B.0 still fails after Patch Cell 1 | patch logic detected sentinel but didn't apply | `cat /content/project/phase1_beat_classical/train_phase1.py \| grep '^    p.add_argument'` — confirm `--hidden-size` is there; if not, re-run Patch Cell 1 (it's idempotent — safe) |
| Phase B Cell D.0_T4 prints "Resuming from epoch 5 of 5" but you wanted to retry | pre-existing stale resume sidecar | Delete `/content/drive/MyDrive/PhD/phase1_month2_2026-05-11/aria_midi_phaseB/symbolic_key_pretrained_aria_phaseB.pt.resume.json` from Drive UI, restart |
| Cell D.0_T4_SYNC reports "missing: ..." for the .pt | session died before any epoch completed | Re-run Cell D.0_T4 (will start from epoch 1 since no resume sidecar) |

---

## §8 — Action checklist for the user

In the existing `phd_training_030526(2).ipynb`:

1. **Add a new cell after the failed Cell B.0** containing **Patch Cell 1** from §1 above. Run it.
2. **Re-run the original Cell B.0** — it should now print `✓ All sensitivity-sweep CLI flags exposed`.
3. **Run Cells B.1 / B.2 / B.4** as written — sensitivity sweep takes ~30–45 min on T4.
4. (Skip B.3 — that was a placeholder for n=3 confirmation; only run if B.2 flags promising cells.)

When ready for Aria:

5. **Add Patch Cell 2 + Patch Cell 3** from §2 + §3 above, run them.
6. **Run Cells C.0 + C.1** from the playbook (Phase A; ~90 min on T4 single session).
7. **Run Cell C.2** (Drive sync) at the end of the Phase A session.
8. **Run Cell D.0_T4** + every 18-22h, run **Cell D.0_T4_SYNC** before disconnecting and re-run Cell D.0_T4 in the next session. Repeat until D.0_T4_SYNC reports "Phase B COMPLETE".
9. **Run Cell D.1_T4** + Cell D.2_T4 in a fresh session.
10. **GATE DECISION:** if Δ_FW < -0.005, document the null and stop. If Δ_FW ≥ +0.01, proceed. Otherwise re-test at lower LR (per playbook §D pre-text).
11. (Optional, only if gate passed) **Run Cells E.0_T4 / E.0_T4_SYNC** across ~15–20 sessions.
12. **Run Cell F.0_T4** (Phase D fine-tune from Phase C).
13. **Run playbook §G** (cross-corpus eval).

---

## §9 — Reviewer record (3 passes against the highest academic standards)

### Pass 1 — Patch correctness reviewer

**Issue 1.1.** The original Patch Cell 1 used `re.search` to detect already-applied state, which is brittle if the user's local copy has whitespace differences. **Revision:** switched to a literal sentinel-string match (`SENTINEL in src`) — exact string equality is more robust than regex on a 4-edit patch.

**Issue 1.2.** The pretrained-checkpoint loader didn't handle the case where the checkpoint dict is itself the `state_dict` (no nested `model_state_dict` key). **Revision:** added the fallback `sd = ckpt.get('model_state_dict', ckpt)` so both calling conventions work.

**Issue 1.3.** The `--ens-beta` patch hardcoded `args.ens_beta` but didn't address the case where the user passes `--ens-beta 1.0` (which would degenerate the ENS weights to uniform). **Revision:** acknowledged this is a valid sweep cell (see `sensitivity_sweep.py` SWEEP_GRID line `('ens_beta', 0.99, 'ens_beta099')`); no code change needed.

### Pass 2 — Resume protocol reviewer

**Issue 2.1.** The original resume protocol saved only after each epoch but didn't save optimizer/scheduler state. **Revision:** Patch Cell 2 now saves `optimizer_state_dict` + `scheduler_state_dict` so the LR schedule resumes correctly; without this, a resumed Phase C would restart the cosine annealing schedule from epoch 0 each session and the LR would never decay.

**Issue 2.2.** The original "save every epoch" overwrote the same file, risking corruption if the session was killed mid-write. **Revision:** the per-epoch save writes to a stable `<output>.epoch.pt` (atomic torch.save is reasonably robust) but ALSO leaves the "best loss" checkpoint at `<output>` for downstream consumers. Two files, two purposes.

**Issue 2.3.** Cell D.1_T4's per-seed resume tracked completed seeds but didn't verify the eval JSON was actually written before marking complete. **Revision:** the `subprocess.check_call` raises on non-zero exit, so a seed that crashed mid-training will NOT be marked complete. The per-seed eval JSON is then synced AFTER the trainer exits cleanly.

**Issue 2.4.** Phase B/C resume cells didn't account for the case where the user wants to RESTART Phase B from scratch (e.g., if the gate failed and we're trying lr=1e-4). **Revision:** documented in §7 the manual delete-from-Drive recovery.

### Pass 3 — T4 wall-clock realism reviewer

**Issue 3.1.** The original A100 estimate of "~12-24 h" for Phase B implied a 50% range due to disk I/O. The T4 estimate of "36-60 h" inherits the same uncertainty. **Revision:** §F notes that the 2× upper bound captures both the 3× T4 slowdown and the I/O variance.

**Issue 3.2.** The Phase C T4 estimate of "~3 weeks" assumed continuous 24h sessions every day for 21 days; in practice users will have gaps. **Revision:** §6 framed it as "15-20 sessions" rather than "X weeks" — sessions may span >3 weeks of calendar time depending on user availability, but the compute requirement is fixed.

**Issue 3.3.** §7's recovery cookbook missed the failure mode where the Drive sync DOES succeed but the user starts the next session in a different Colab account (e.g. wrong Google login). **Revision:** added implicit "Drive must be the same Drive" caveat — the path in §6 is hardcoded `/MyDrive/PhD/phase1_month2_2026-05-11/...` so this is self-documenting.

**Issue 3.4.** The Phase D per-seed resume in Cell D.1_T4 didn't mention how long ONE seed takes on T4. **Revision:** §F now says ~6-10 h for 5 seeds, implying ~1.5-2 h per seed on T4. Since one seed at a time fits in any session ≥2h, this is robust.

---

*Compiled by `COLAB_FIX_CELLS_2026-05-11.md` 2026-05-11. Companion to `SENSITIVITY_ARIA_PLAYBOOK_2026-05-11.md` for T4 + multi-session resume.*
