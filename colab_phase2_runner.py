#!/usr/bin/env python3
"""
Colab Phase 2 Runner — Post-processing, ensemble, and new architecture experiments.

=== WHAT THIS SCRIPT DOES ===

Part A: Re-evaluate A1 (best GRU) to save softmax probabilities (test + validation)
Part B: HMM post-processing with grid search — tuned on validation, applied to test
Part C: Neural + Classical ensemble with alpha grid search — tuned on validation
Part D: Cascade: Ensemble + HMM (best single result)
Part E: New experiments: BiGRU (A6), GRU+PCP (A7), Focal (A8), combined (A9),
        grad-clip+smooth (A10), all-improvements (A11)
Part F: Generate complete thesis ablation table

=== DATA LEAKAGE FIXES (Research Audit) ===

- Part A now generates BOTH test and validation predictions so that
  hyperparameter tuning in Parts B/C never touches the test set.
- Part B passes --val-predictions so HMM grid search uses validation data.
- Part C passes --val-predictions so ensemble alpha search uses validation data.
- Part E adds --save-val-predictions for each experiment and supports
  new training flags: --clip-grad, --label-smoothing, --weight-decay, --amp.

=== COLAB INSTRUCTIONS ===

1. Upload the updated project zip to Google Drive:
   ```
   cd /path/to/project
   zip -r project_colab.zip . -x '.venv/*' 'ATEPP-1.2/*' '*.pyc' '__pycache__/*'
   ```
   Upload to Google Drive My Drive/PhD/

2. In Colab:
   ```python
   from google.colab import drive
   drive.mount('/content/drive')
   ```

3. Unzip and install:
   ```python
   !cd /content && rm -rf project && unzip -q /content/drive/MyDrive/PhD/project_colab.zip -d project
   !pip install torch numpy -q
   ```

4. Run Phase 2 (Parts A-D need NO GPU, Parts E needs T4):
   ```python
   # Part A-D: Post-processing (CPU-only, ~5 min)
   !cd /content/project && python colab_phase2_runner.py --parts A,B,C,D

   # Part E: New experiments (needs GPU, ~2 hours)
   !cd /content/project && python colab_phase2_runner.py --parts E

   # Part F: Generate table (CPU, ~1 sec)
   !cd /content/project && python colab_phase2_runner.py --parts F

   # Or run everything:
   !cd /content/project && python colab_phase2_runner.py --parts all
   ```

5. Results saved to research_data/ and backed up to Google Drive.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Dict, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_MANIFEST = os.path.join(BASE_DIR, 'research_data', 'unified_training_manifest.json')
DEFAULT_LABEL_DIRS = ','.join([
    os.path.join(BASE_DIR, 'research_data', 'all_key_labels'),
    os.path.join(BASE_DIR, 'research_data', 'score_key_labels'),
])
DEFAULT_SPLITS = os.path.join(BASE_DIR, 'research_data', 'composition_splits.json')
DEFAULT_LABEL_DIR = os.path.join(BASE_DIR, 'research_data', 'score_key_labels')

# Best model from Phase 1 ablation
BEST_CHECKPOINT = os.path.join(BASE_DIR, 'research_data', 'ablation_A1.pt')
BEST_PREDICTIONS = os.path.join(BASE_DIR, 'research_data', 'ablation_A1_predictions.json')

# Phase 2 experiment grid.
#
# HISTORY (2026-04-14, Phase A rigor restoration):
#   The original Phase 2 grid (A6-A11) set `weight_mode: "none"` for every cell.
#   Phase 1 had already demonstrated that `sqrt` or `ens` weighting is required
#   to keep minority-class accuracy non-degenerate (F#m=0% under 'none'), and
#   the Phase 1 planning brief (PHD_CATCHUP_BRIEFING_2026-04-08.md) explicitly
#   recommended sqrt/ens weighting plus focal loss for Phase 2. The 'none'
#   default was a regression against that plan — see PHASE2_POSTDOC_FINDINGS_2026-04-14.md §4.4.
#
#   Phase A restores the intent: grid cells default to 'sqrt' weighting. Each
#   cell still surfaces as a CLI arg (`--weight-mode` at line ~394 below), so
#   an ablation that explicitly studies weighting can override at the call site.
#   The `none` configurations are preserved in PHASE2_WEIGHT_REGRESSION_GRID
#   below ONLY for reproducing the audited (buggy) Phase 2 runs.
#
# If you want a fresh ablation that studies weighting as an axis, build a new
# grid dict; do not quietly flip values in PHASE2_GRID.
PHASE2_GRID = {
    'A6': {
        'name': 'BiGRU_aug_sqrtWeight',
        'model_type': 'gru',
        'no_augment': False,
        'weight_mode': 'sqrt',
        'epochs': 30,
        'batch_size': 8,
        'learning_rate': 1e-3,
        'bidirectional': True,  # ORACLE: non-causal, not deployable (<20ms constraint)
        'gru_pcp': False,
        'focal_loss': False,
    },
    'A7': {
        'name': 'GRU_PCP_aug_sqrtWeight',
        'model_type': 'gru',
        'no_augment': False,
        'weight_mode': 'sqrt',
        'epochs': 30,
        'batch_size': 8,
        'learning_rate': 1e-3,
        'bidirectional': False,
        'gru_pcp': True,
        'focal_loss': False,
    },
    'A8': {
        'name': 'GRU_aug_sqrtWeight_focal',
        'model_type': 'gru',
        'no_augment': False,
        'weight_mode': 'sqrt',
        'epochs': 30,
        'batch_size': 8,
        'learning_rate': 1e-3,
        'bidirectional': False,
        'gru_pcp': False,
        'focal_loss': True,
    },
    'A9': {
        'name': 'BiGRU_PCP_aug_sqrtWeight_focal',
        'model_type': 'gru',
        'no_augment': False,
        'weight_mode': 'sqrt',
        'epochs': 30,
        'batch_size': 8,
        'learning_rate': 1e-3,
        'bidirectional': True,  # ORACLE: non-causal, not deployable (<20ms constraint)
        'gru_pcp': True,
        'focal_loss': True,
    },
    'A10': {
        'name': 'GRU_aug_clip_smooth_sqrtWeight',
        'model_type': 'gru',
        'no_augment': False,
        'weight_mode': 'sqrt',
        'epochs': 30,
        'batch_size': 8,
        'learning_rate': 1e-3,
        'bidirectional': False,
        'gru_pcp': False,
        'focal_loss': False,
        'clip_grad': 1.0,
        'label_smoothing': 0.1,
        'weight_decay': 0.01,
    },
    'A11': {
        'name': 'GRU_aug_allImprove_sqrtWeight',
        'model_type': 'gru',
        'no_augment': False,
        'weight_mode': 'sqrt',
        'epochs': 30,
        'batch_size': 8,
        'learning_rate': 1e-3,
        'bidirectional': False,
        'gru_pcp': False,
        'focal_loss': False,
        'clip_grad': 1.0,
        'label_smoothing': 0.1,
        'weight_decay': 0.001,
    },
}

# Audited Phase 2 grid with weight_mode='none' preserved for reproducibility of
# the archived (buggy) runs. Do not use for new experiments.
PHASE2_WEIGHT_REGRESSION_GRID = {
    exp_id: {**cfg, 'weight_mode': 'none', 'name': cfg['name'] + '__regression'}
    for exp_id, cfg in PHASE2_GRID.items()
}


def backup_to_drive(files: List[str], drive_dir: str | None) -> None:
    """Copy files to Google Drive if available."""
    if not drive_dir:
        return
    os.makedirs(drive_dir, exist_ok=True)
    for src in files:
        if os.path.isfile(src):
            dst = os.path.join(drive_dir, os.path.basename(src))
            shutil.copy2(src, dst)
            print(f'  Backed up to {dst}')


def run_part_a(drive_backup: str | None) -> None:
    """Part A: Re-evaluate A1 with softmax probabilities (test + validation)."""
    print('\n' + '=' * 60)
    print('PART A: Re-evaluate A1 with softmax probabilities (test + val)')
    print('=' * 60)

    output_pred = os.path.join(BASE_DIR, 'research_data', 'ablation_A1_predictions_softmax.json')
    output_val_pred = os.path.join(BASE_DIR, 'research_data', 'ablation_A1_predictions_val_softmax.json')
    output_eval = os.path.join(BASE_DIR, 'research_data', 'ablation_A1_eval_softmax.json')

    # Check if A1 checkpoint exists (may be in project or need to copy from Drive)
    checkpoint = BEST_CHECKPOINT
    if not os.path.isfile(checkpoint):
        drive_ckpt = '/content/drive/MyDrive/PhD/ablation_results/ablation_A1.pt'
        if os.path.isfile(drive_ckpt):
            shutil.copy2(drive_ckpt, checkpoint)
            print(f'Copied checkpoint from Drive: {drive_ckpt}')
        else:
            print(f'ERROR: No A1 checkpoint found at {checkpoint} or {drive_ckpt}')
            return

    cmd = [
        sys.executable, os.path.join(BASE_DIR, 'evaluate_harmonic_context_model.py'),
        '--manifest', DEFAULT_MANIFEST,
        '--label-dirs', DEFAULT_LABEL_DIRS,
        '--model-type', 'gru',
        '--checkpoint', checkpoint,
        '--output', output_eval,
        '--save-predictions', output_pred,
        '--save-val-predictions', output_val_pred,
        '--bootstrap-n', '1000',
    ]

    print(f'Command: {" ".join(cmd)}\n')
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print('ERROR: Re-evaluation failed')
        return

    # Verify softmax is in the test predictions file
    with open(output_pred, 'r') as f:
        data = json.load(f)
    has_softmax = data.get('has_softmax', False)
    n_comps = len(data.get('compositions', []))
    print(f'\nTest predictions — softmax: {has_softmax}, compositions: {n_comps}')

    # Verify validation predictions file
    if os.path.isfile(output_val_pred):
        with open(output_val_pred, 'r') as f:
            val_data = json.load(f)
        val_n = len(val_data.get('compositions', []))
        print(f'Val predictions — compositions: {val_n}')
    else:
        print('WARNING: Validation predictions file was not created')

    backup_to_drive([output_pred, output_val_pred, output_eval], drive_backup)


def run_part_b(drive_backup: str | None) -> None:
    """Part B: HMM post-processing with grid search (tuned on validation)."""
    print('\n' + '=' * 60)
    print('PART B: HMM post-processing (grid search on validation)')
    print('=' * 60)

    # Prefer softmax predictions if available
    pred_file = os.path.join(BASE_DIR, 'research_data', 'ablation_A1_predictions_softmax.json')
    if not os.path.isfile(pred_file):
        pred_file = BEST_PREDICTIONS
        if not os.path.isfile(pred_file):
            drive_pred = '/content/drive/MyDrive/PhD/ablation_results/ablation_A1_predictions.json'
            if os.path.isfile(drive_pred):
                shutil.copy2(drive_pred, pred_file)
            else:
                print(f'ERROR: No prediction file found. Run Part A first.')
                return

    # Validation predictions for hyperparameter tuning (avoids test-set leakage)
    val_pred_file = os.path.join(BASE_DIR, 'research_data', 'ablation_A1_predictions_val_softmax.json')

    output = os.path.join(BASE_DIR, 'research_data', 'hmm_postprocessing_eval.json')

    cmd = [
        sys.executable, os.path.join(BASE_DIR, 'hmm_postprocessing.py'),
        '--predictions', pred_file,
        '--grid-search',
        '--output', output,
    ]

    # Pass validation predictions so grid search tunes on val, not test
    if os.path.isfile(val_pred_file):
        cmd.extend(['--val-predictions', val_pred_file])
        print(f'Using validation predictions for grid search: {val_pred_file}')
    else:
        print('WARNING: No validation predictions found — grid search will use test set')

    print(f'Command: {" ".join(cmd)}\n')
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print('ERROR: HMM post-processing failed')
        return

    backup_to_drive([output], drive_backup)


def run_part_c(drive_backup: str | None) -> None:
    """Part C: Neural + Classical ensemble with alpha grid search (tuned on validation)."""
    print('\n' + '=' * 60)
    print('PART C: Neural + Classical ensemble (alpha grid search on validation)')
    print('=' * 60)

    # Prefer softmax predictions
    pred_file = os.path.join(BASE_DIR, 'research_data', 'ablation_A1_predictions_softmax.json')
    if not os.path.isfile(pred_file):
        pred_file = BEST_PREDICTIONS

    if not os.path.isfile(pred_file):
        print(f'ERROR: No prediction file found at {pred_file}. Run Part A first.')
        return

    # Validation predictions for alpha tuning (avoids test-set leakage)
    val_pred_file = os.path.join(BASE_DIR, 'research_data', 'ablation_A1_predictions_val_softmax.json')

    output = os.path.join(BASE_DIR, 'research_data', 'ensemble_eval.json')

    cmd = [
        sys.executable, os.path.join(BASE_DIR, 'ensemble_key_detector.py'),
        '--neural-predictions', pred_file,
        '--splits', DEFAULT_SPLITS,
        '--label-dirs', DEFAULT_LABEL_DIRS,  # Phase A: ensemble must see the unified test (N=58), not ATEPP-only (N=41).
        '--output', output,
    ]

    # Pass validation predictions so alpha search tunes on val, not test
    if os.path.isfile(val_pred_file):
        cmd.extend(['--val-predictions', val_pred_file])
        print(f'Using validation predictions for alpha search: {val_pred_file}')
    else:
        print('WARNING: No validation predictions found — alpha search will use test set')

    print(f'Command: {" ".join(cmd)}\n')
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print('ERROR: Ensemble evaluation failed')
        return

    backup_to_drive([output], drive_backup)


def run_part_d(drive_backup: str | None) -> None:
    """Part D: Cascade (ensemble → HMM) — apply HMM to ensemble predictions."""
    print('\n' + '=' * 60)
    print('PART D: Cascade — HMM on ensemble output')
    print('=' * 60)

    # This requires custom code since ensemble changes the predictions
    # Load ensemble result to get best alpha, then re-run with HMM
    ensemble_file = os.path.join(BASE_DIR, 'research_data', 'ensemble_eval.json')
    if not os.path.isfile(ensemble_file):
        print('ERROR: Run Part C first to get ensemble results.')
        return

    with open(ensemble_file, 'r') as f:
        ensemble_data = json.load(f)

    best_alpha = ensemble_data.get('alpha', 0.5)
    print(f'Using ensemble alpha={best_alpha:.2f}')
    print(f'Ensemble MIREX = {ensemble_data.get("ensemble_mirex", 0):.4f}')
    print(f'\nNote: Cascade (ensemble → HMM) requires generating ensemble predictions')
    print(f'per note, then applying Viterbi. This is implemented in generate_ablation_table.py.')
    print(f'The standalone cascade will be computed during table generation (Part F).')


def run_part_e(drive_backup: str | None) -> None:
    """Part E: Train new architecture experiments (A6-A11)."""
    print('\n' + '=' * 60)
    print('PART E: Phase 2 training experiments')
    print('=' * 60)

    # Detect CUDA for --amp flag
    try:
        import torch
        has_cuda = torch.cuda.is_available()
    except ImportError:
        has_cuda = False

    all_results = []

    for exp_id, config in PHASE2_GRID.items():
        print(f'\n{"="*60}')
        print(f'EXPERIMENT {exp_id}: {config["name"]}')
        print(f'  BiGRU: {config["bidirectional"]}, PCP: {config["gru_pcp"]}, '
              f'Focal: {config["focal_loss"]}')
        if config.get('clip_grad'):
            print(f'  clip_grad: {config["clip_grad"]}, label_smooth: {config.get("label_smoothing")}, '
                  f'weight_decay: {config.get("weight_decay")}')
        print(f'{"="*60}\n')

        checkpoint = os.path.join(BASE_DIR, 'research_data', f'ablation_{exp_id}.pt')
        eval_output = os.path.join(BASE_DIR, 'research_data', f'ablation_{exp_id}_eval.json')
        pred_output = os.path.join(BASE_DIR, 'research_data', f'ablation_{exp_id}_predictions.json')
        val_pred_output = os.path.join(BASE_DIR, 'research_data', f'ablation_{exp_id}_predictions_val.json')

        # Build training command
        train_cmd = [
            sys.executable, os.path.join(BASE_DIR, 'train_harmonic_context_model.py'),
            '--manifest', DEFAULT_MANIFEST,
            '--label-dirs', DEFAULT_LABEL_DIRS,
            '--model-type', config['model_type'],
            '--weight-mode', config['weight_mode'],
            '--epochs', str(config['epochs']),
            '--batch-size', str(config['batch_size']),
            '--learning-rate', str(config['learning_rate']),
            '--checkpoint', checkpoint,
            '--patience', '10',
            '--warmup-epochs', '5',
        ]
        if config['no_augment']:
            train_cmd.append('--no-augment')
        if config['bidirectional']:
            train_cmd.append('--bidirectional')
        if config['gru_pcp']:
            train_cmd.append('--gru-pcp')
        if config['focal_loss']:
            train_cmd.append('--focal-loss')
        if config.get('clip_grad'):
            train_cmd.extend(['--clip-grad', str(config['clip_grad'])])
        if config.get('label_smoothing'):
            train_cmd.extend(['--label-smoothing', str(config['label_smoothing'])])
        if config.get('weight_decay'):
            train_cmd.extend(['--weight-decay', str(config['weight_decay'])])
        if has_cuda:
            train_cmd.append('--amp')

        start = time.time()
        print(f'Training command: {" ".join(train_cmd)}\n')
        result = subprocess.run(train_cmd, capture_output=False)
        train_time = time.time() - start
        print(f'\nTraining completed in {train_time/3600:.1f} hours')

        if result.returncode != 0:
            print(f'ERROR: Training failed for {exp_id}')
            all_results.append({'exp_id': exp_id, 'error': 'training_failed'})
            continue

        # Evaluate — save both test and validation predictions
        eval_cmd = [
            sys.executable, os.path.join(BASE_DIR, 'evaluate_harmonic_context_model.py'),
            '--manifest', DEFAULT_MANIFEST,
            '--label-dirs', DEFAULT_LABEL_DIRS,
            '--model-type', config['model_type'],
            '--checkpoint', checkpoint,
            '--output', eval_output,
            '--save-predictions', pred_output,
            '--save-val-predictions', val_pred_output,
            '--bootstrap-n', '1000',
        ]

        # Note: eval script auto-reads bidirectional/gru_pcp from checkpoint
        # metadata (evaluate_harmonic_context_model.py:366-372), no CLI flags needed.

        print(f'\nEvaluating...')
        result = subprocess.run(eval_cmd, capture_output=False)

        if result.returncode != 0:
            print(f'ERROR: Evaluation failed for {exp_id}')
            all_results.append({'exp_id': exp_id, 'error': 'evaluation_failed'})
            continue

        with open(eval_output, 'r') as f:
            eval_data = json.load(f)

        test = eval_data.get('test', {})
        ci = eval_data.get('bootstrap_ci', {})
        classes = eval_data.get('class_metrics', {})

        result_summary = {
            'exp_id': exp_id,
            'config': config,
            'mirex': test.get('mirex_weighted_score', 0),
            'accuracy': test.get('accuracy', 0),
            'mirex_ci_lower': ci.get('mirex_ci_lower', 0),
            'mirex_ci_upper': ci.get('mirex_ci_upper', 0),
            'major_accuracy': classes.get('mean_major_accuracy', 0),
            'minor_accuracy': classes.get('mean_minor_accuracy', 0),
            'total_predictions': test.get('total_predictions', 0),
            'train_time_hours': train_time / 3600,
        }

        print(f'\n--- {exp_id} Results ---')
        print(f'  MIREX: {result_summary["mirex"]:.4f} '
              f'(95% CI: {result_summary["mirex_ci_lower"]:.4f}–{result_summary["mirex_ci_upper"]:.4f})')
        print(f'  Major: {result_summary["major_accuracy"]:.4f}, Minor: {result_summary["minor_accuracy"]:.4f}')

        all_results.append(result_summary)
        backup_to_drive([checkpoint, eval_output, pred_output, val_pred_output], drive_backup)

    # Save Phase 2 summary
    summary_path = os.path.join(BASE_DIR, 'research_data', 'phase2_ablation_summary.json')
    with open(summary_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f'\nPhase 2 summary saved to {summary_path}')
    backup_to_drive([summary_path], drive_backup)


def run_part_f(drive_backup: str | None) -> None:
    """Part F: Generate complete thesis ablation table."""
    print('\n' + '=' * 60)
    print('PART F: Generate thesis ablation table')
    print('=' * 60)

    cmd = [
        sys.executable, os.path.join(BASE_DIR, 'generate_ablation_table.py'),
    ]

    print(f'Command: {" ".join(cmd)}\n')
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print('ERROR: Table generation failed')
        return

    table_file = os.path.join(BASE_DIR, 'research_data', 'ablation_table.md')
    latex_file = os.path.join(BASE_DIR, 'research_data', 'ablation_table.tex')
    backup_to_drive([f for f in [table_file, latex_file] if os.path.isfile(f)], drive_backup)


def main() -> None:
    parser = argparse.ArgumentParser(description='Phase 2: Post-processing + new experiments')
    parser.add_argument('--parts', default='all',
                        help='Comma-separated parts to run (A,B,C,D,E,F) or "all"')
    parser.add_argument('--experiments', default='all',
                        help='For Part E: comma-separated experiment IDs (A6,A7,A8,A9) or "all"')
    parser.add_argument('--drive-backup', default=None,
                        help='Google Drive backup directory')
    args = parser.parse_args()

    # Auto-detect Google Drive
    if args.drive_backup is None:
        drive_path = '/content/drive/MyDrive/PhD/phase2_results'
        if os.path.isdir('/content/drive/MyDrive'):
            args.drive_backup = drive_path
            print(f'Auto-detected Google Drive: {args.drive_backup}')

    if args.parts == 'all':
        parts = ['A', 'B', 'C', 'D', 'E', 'F']
    else:
        parts = [p.strip().upper() for p in args.parts.split(',')]

    print(f'Running parts: {", ".join(parts)}')

    part_funcs = {
        'A': run_part_a,
        'B': run_part_b,
        'C': run_part_c,
        'D': run_part_d,
        'E': run_part_e,
        'F': run_part_f,
    }

    for part in parts:
        if part in part_funcs:
            part_funcs[part](args.drive_backup)
        else:
            print(f'Unknown part: {part}')


if __name__ == '__main__':
    main()
