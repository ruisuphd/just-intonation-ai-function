#!/usr/bin/env python3
"""
Colab Ablation Runner — Self-contained script for running the Phase 1 ablation
grid on Google Colab with T4 GPU.

=== STEP-BY-STEP COLAB INSTRUCTIONS ===

1. Upload your project to Google Drive:
   - Zip the project: `zip -r project.zip . -x '.venv/*' 'ATEPP-1.2/*' '*.pyc'`
   - Upload project.zip to Google Drive (e.g., My Drive/PhD/)

2. Open a new Colab notebook (colab.research.google.com)

3. Mount Google Drive:
   ```python
   from google.colab import drive
   drive.mount('/content/drive')
   ```

4. Unzip the project:
   ```python
   !cd /content && unzip -q /content/drive/MyDrive/PhD/project.zip -d project
   ```

5. Install dependencies:
   ```python
   !pip install torch numpy
   ```

6. Run the ablation grid:
   ```python
   !cd /content/project && python colab_ablation_runner.py --experiments all
   ```

   Or run specific experiments:
   ```python
   !cd /content/project && python colab_ablation_runner.py --experiments A0,A1
   ```

7. Results are auto-saved to research_data/ and copied to Google Drive.

=== EXPERIMENT GRID ===

| ID | Model       | Augment | Weight | Expected MIREX |
|----|-------------|---------|--------|----------------|
| A0 | GRU         | No      | none   | 0.48-0.52      |
| A1 | GRU         | Yes     | none   | 0.52-0.56      |
| A2 | GRU         | No      | sqrt   | 0.50-0.54      |
| A3 | GRU         | Yes     | sqrt   | 0.54-0.58      |
| A4 | GRU         | Yes     | ens    | 0.55-0.62      |
| A5 | Transformer | Yes     | ens    | 0.53-0.60      |

Each experiment takes ~3-5 hours on Colab T4 (30 epochs).
Run A0+A1 in one session, A2+A3 in another, A4+A5 in a third.
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

# Default paths — use relative paths so this works on both Mac and Colab.
# all_key_labels contains converted WiR/DCML note-level labels (Strategy A/B).
# score_key_labels contains the original 319 ATEPP files (real MIDI data).
# Together: 407 usable compositions (Strategy B synthetic files auto-filtered).
DEFAULT_MANIFEST = os.path.join(BASE_DIR, 'research_data', 'unified_training_manifest.json')
DEFAULT_LABEL_DIRS = ','.join([
    os.path.join(BASE_DIR, 'research_data', 'all_key_labels'),
    os.path.join(BASE_DIR, 'research_data', 'score_key_labels'),
])

ABLATION_GRID = {
    'A0': {
        'name': 'GRU_noAug_noWeight',
        'model_type': 'gru',
        'no_augment': True,
        'weight_mode': 'none',
        'epochs': 30,
        'batch_size': 8,
        'learning_rate': 1e-3,
    },
    'A1': {
        'name': 'GRU_aug_noWeight',
        'model_type': 'gru',
        'no_augment': False,
        'weight_mode': 'none',
        'epochs': 30,
        'batch_size': 8,
        'learning_rate': 1e-3,
    },
    'A2': {
        'name': 'GRU_noAug_sqrt',
        'model_type': 'gru',
        'no_augment': True,
        'weight_mode': 'sqrt',
        'epochs': 30,
        'batch_size': 8,
        'learning_rate': 1e-3,
    },
    'A3': {
        'name': 'GRU_aug_sqrt',
        'model_type': 'gru',
        'no_augment': False,
        'weight_mode': 'sqrt',
        'epochs': 30,
        'batch_size': 8,
        'learning_rate': 1e-3,
    },
    'A4': {
        'name': 'GRU_aug_ens',
        'model_type': 'gru',
        'no_augment': False,
        'weight_mode': 'ens',
        'epochs': 30,
        'batch_size': 8,
        'learning_rate': 1e-3,
    },
    'A5': {
        'name': 'Transformer_aug_ens',
        'model_type': 'transformer',
        'no_augment': False,
        'weight_mode': 'ens',
        'epochs': 50,
        'batch_size': 8,
        'learning_rate': 1e-4,
    },
}


def run_experiment(exp_id: str, config: Dict, drive_backup_dir: str | None = None) -> Dict:
    """Run a single ablation experiment."""
    print(f'\n{"="*60}')
    print(f'EXPERIMENT {exp_id}: {config["name"]}')
    print(f'  Model: {config["model_type"]}, Augment: {not config["no_augment"]}, '
          f'Weight: {config["weight_mode"]}, Epochs: {config["epochs"]}')
    print(f'{"="*60}\n')

    checkpoint = os.path.join(BASE_DIR, 'research_data', f'ablation_{exp_id}.pt')
    eval_output = os.path.join(BASE_DIR, 'research_data', f'ablation_{exp_id}_eval.json')
    pred_output = os.path.join(BASE_DIR, 'research_data', f'ablation_{exp_id}_predictions.json')

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
    if config['weight_mode'] == 'ens':
        train_cmd.extend(['--ens-beta', '0.999'])

    # Run training
    start = time.time()
    print(f'Training command: {" ".join(train_cmd)}\n')
    result = subprocess.run(train_cmd, capture_output=False)
    train_time = time.time() - start
    print(f'\nTraining completed in {train_time/3600:.1f} hours')

    if result.returncode != 0:
        print(f'ERROR: Training failed with return code {result.returncode}')
        return {'exp_id': exp_id, 'error': 'training_failed'}

    # Build evaluation command
    eval_cmd = [
        sys.executable, os.path.join(BASE_DIR, 'evaluate_harmonic_context_model.py'),
        '--manifest', DEFAULT_MANIFEST,
        '--label-dirs', DEFAULT_LABEL_DIRS,
        '--model-type', config['model_type'],
        '--checkpoint', checkpoint,
        '--output', eval_output,
        '--save-predictions', pred_output,
        '--bootstrap-n', '1000',
    ]

    # Run evaluation
    print(f'\nEvaluating...')
    result = subprocess.run(eval_cmd, capture_output=False)

    if result.returncode != 0:
        print(f'ERROR: Evaluation failed')
        return {'exp_id': exp_id, 'error': 'evaluation_failed'}

    # Load and report results
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
    print(f'  Accuracy: {result_summary["accuracy"]:.4f}')
    print(f'  Major: {result_summary["major_accuracy"]:.4f}, Minor: {result_summary["minor_accuracy"]:.4f}')

    # Backup to Google Drive if available
    if drive_backup_dir:
        os.makedirs(drive_backup_dir, exist_ok=True)
        for src in [checkpoint, eval_output, pred_output]:
            if os.path.isfile(src):
                dst = os.path.join(drive_backup_dir, os.path.basename(src))
                shutil.copy2(src, dst)
                print(f'  Backed up to {dst}')

    return result_summary


def main() -> None:
    parser = argparse.ArgumentParser(description='Run ablation experiments')
    parser.add_argument('--experiments', default='all',
                        help='Comma-separated experiment IDs (e.g., A0,A1) or "all"')
    parser.add_argument('--drive-backup', default=None,
                        help='Google Drive directory for backups (e.g., /content/drive/MyDrive/PhD/results)')
    args = parser.parse_args()

    # Auto-detect Google Drive
    if args.drive_backup is None:
        drive_path = '/content/drive/MyDrive/PhD/ablation_results'
        if os.path.isdir('/content/drive/MyDrive'):
            args.drive_backup = drive_path
            print(f'Auto-detected Google Drive, backing up to: {args.drive_backup}')

    if args.experiments == 'all':
        exp_ids = list(ABLATION_GRID.keys())
    else:
        exp_ids = [e.strip() for e in args.experiments.split(',')]

    print(f'Running {len(exp_ids)} experiments: {", ".join(exp_ids)}')
    print(f'Manifest: {DEFAULT_MANIFEST}')

    all_results = []
    for exp_id in exp_ids:
        if exp_id not in ABLATION_GRID:
            print(f'Unknown experiment: {exp_id}. Available: {", ".join(ABLATION_GRID.keys())}')
            continue
        result = run_experiment(exp_id, ABLATION_GRID[exp_id], args.drive_backup)
        all_results.append(result)

    # Summary table
    print(f'\n\n{"="*80}')
    print('ABLATION SUMMARY')
    print(f'{"="*80}')
    print(f'{"ID":<5} {"Model":<13} {"Aug":>4} {"Weight":>6} '
          f'{"MIREX":>8} {"95% CI":>18} {"Major":>7} {"Minor":>7} {"Time":>6}')
    print('-' * 80)

    for r in all_results:
        if 'error' in r:
            print(f'{r["exp_id"]:<5} ERROR: {r["error"]}')
            continue
        c = r['config']
        aug = 'Yes' if not c['no_augment'] else 'No'
        ci_str = f'{r["mirex_ci_lower"]:.3f}–{r["mirex_ci_upper"]:.3f}'
        print(f'{r["exp_id"]:<5} {c["model_type"]:<13} {aug:>4} {c["weight_mode"]:>6} '
              f'{r["mirex"]:>8.4f} {ci_str:>18} '
              f'{r["major_accuracy"]:>7.3f} {r["minor_accuracy"]:>7.3f} '
              f'{r["train_time_hours"]:>5.1f}h')

    # Save summary
    summary_path = os.path.join(BASE_DIR, 'research_data', 'ablation_summary.json')
    with open(summary_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f'\nSummary saved to {summary_path}')

    if args.drive_backup and os.path.isdir(os.path.dirname(args.drive_backup)):
        os.makedirs(args.drive_backup, exist_ok=True)
        shutil.copy2(summary_path, os.path.join(args.drive_backup, 'ablation_summary.json'))


if __name__ == '__main__':
    main()
