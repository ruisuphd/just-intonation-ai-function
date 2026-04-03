# Harmonic Model Smoke Training

## Question

Can the end-to-end harmonic-model pipeline execute successfully on the current machine?

## Hypothesis

The pipeline should complete one training epoch on score-derived local-key labels and save a checkpoint.

## Date

2026-03-09

## Code Version

Repository state after:

- generation of `research_data/composition_splits.json`
- generation of `research_data/score_key_labels/`
- addition of `harmonic_context_model.py`
- addition of `train_harmonic_context_model.py`

## Data Split

- train compositions from `research_data/composition_splits.json`
- validation compositions from `research_data/composition_splits.json`

## Preprocessing

- score-derived note-level key labels
- training windows of `256` notes with hop `128`
- light augmentation via note dropout and time scaling

## Configuration

- model: compact GRU harmonic-state model
- epochs: `1`
- batch size: `16`
- device: `cpu`

## Metrics

- training loss
- training accuracy
- validation loss
- validation accuracy

## Hardware

Executed locally on CPU.

## Results

- train loss: `1.8190`
- train accuracy: `0.3863`
- validation loss: `1.7587`
- validation accuracy: `0.3756`
- checkpoint saved to `research_data/harmonic_context_model.pt`

## Statistics

No formal statistics were run. This was a pipeline smoke test, not a final evaluation.

## Interpretation

The main success criterion was met:

- the split manifest loaded
- score-derived label files loaded
- training windows were built
- the model trained for one epoch
- a checkpoint was written

The reported accuracy is only a preliminary signal and should not yet be treated as a research result.

## Decision

The harmonic-model pipeline is viable enough to continue into real experiments.

## Next Step

Benchmark the trained model against the classical score-free baselines on the held-out split.
