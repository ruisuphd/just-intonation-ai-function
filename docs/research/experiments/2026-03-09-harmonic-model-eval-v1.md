# Harmonic Model Evaluation V1

## Question

How does the first saved harmonic-context checkpoint perform on the held-out split windows?

## Hypothesis

The checkpoint should achieve a usable held-out accuracy signal that justifies continuing beyond smoke-testing.

## Date

2026-03-09

## Code Version

Repository state after:

- generation of the full score-label set
- one-epoch smoke training
- addition of `evaluate_harmonic_context_model.py`

## Data Split

- validation windows from held-out validation compositions
- test windows from held-out test compositions

## Preprocessing

- score-derived local-key labels
- window size `256`
- hop `128`

## Configuration

- checkpoint: `research_data/harmonic_context_model.pt`
- evaluation device: `cpu`

## Metrics

- cross-entropy loss
- masked note-level local-key accuracy

## Hardware

Executed locally on CPU.

## Results

- validation loss: `1.7587`
- validation accuracy: `0.3756`
- test loss: `1.6218`
- test accuracy: `0.4310`

## Statistics

No formal significance test was run in this first evaluation pass.

## Interpretation

This is still an early result, but it is encouraging.

- the model trains and evaluates successfully
- held-out masked local-key accuracy is higher than the note-level agreement observed in the classical score-free baselines under the earlier benchmark

However, the comparison is not perfectly identical yet because:

- the model is evaluated on fixed windows
- the classical baselines were evaluated as full causal state machines over complete sequences

So this should be treated as a promising signal, not a final superiority claim.

## Decision

Continue developing and benchmarking the learned harmonic model.

## Next Step

Create a direct apples-to-apples evaluation where the learned model and classical baselines are compared under the same causal sequence protocol.
