# Causal Harmonic Benchmark Protocol

## Purpose

This protocol defines the first apples-to-apples comparison between:

- the legacy score-free detector
- the current causal ensemble detector
- the learned harmonic-context model

The goal is to compare all three under one shared causal sequence protocol instead of mixing windowed model evaluation with runtime detector evaluation.

## Research Question

Can the learned harmonic-context model improve unknown-piece local-key tracking over the classical score-free baselines without violating live latency constraints?

## Fairness Rules

The benchmark must obey the following rules:

- all methods must see the same note stream in the same order
- all methods must operate causally
- no future notes may be used to predict the current note label
- all methods must be evaluated on the same held-out composition split
- the learned model must be evaluated with its runtime confidence gate, not only as an offline classifier
- latency must be reported alongside accuracy

## Data

Use the existing composition-level split manifest and note-label files:

- `research_data/composition_splits.json`
- `research_data/score_key_labels/`

Primary benchmark split:

- validation
- test

Training split is used only for the learned model checkpoint, never for evaluation.

## Evaluation Stream Construction

For each composition label file:

1. sort notes by their score order as already stored in the label file
2. convert `onset_beat` to milliseconds using one fixed reference tempo for simulation
3. feed notes one by one to every benchmarked method
4. record the prediction available immediately after consuming each note

Reference tempo for the first benchmark:

- `120 BPM` equivalent timing for causal simulation

This matches the current score-free benchmark and avoids adding tempo as a confound in the first direct comparison.

## Method Interfaces

### Classical Baselines

Input per note:

- pitch
- simulated event time
- approximate active-note set

Output per note:

- current key
- confidence if available

The current causal ensemble already exposes confidence. The legacy detector does not, so its confidence should be recorded as `unknown` rather than fabricated.

### Learned Model

Input per note:

- pitch
- simulated event time
- approximate active-note set
- fixed or estimated duration proxy

Output per note:

- predicted key
- posterior confidence
- whether the runtime gate emitted a usable prediction

The learned model must be evaluated through `harmonic_context_runtime.py` or an equivalent causal wrapper, not by running full windows with access to future context.

## Active-Note Approximation

Because the live runtime does not receive exact note-off events in the current backend path, the benchmark should use one explicit approximation and keep it fixed across all methods.

First benchmark setting:

- maintain a short active-note list
- use note durations when present in label files
- clamp very short durations to a small positive minimum

If a later live benchmark uses note-on-only input, that should be reported as a separate condition rather than mixed with the first benchmark.

## Primary Metrics

### Harmonic Tracking

- note-level local-key accuracy when a prediction is present
- coverage
- accuracy at full stream level, counting abstentions explicitly
- change-point precision, recall, and F1
- predicted key-change count
- mean run length of stable segments

### Confidence And Calibration

- expected calibration error or a simple reliability-bin analysis
- accuracy above confidence thresholds such as `0.60`, `0.70`, `0.80`, `0.90`
- abstention rate as a function of confidence threshold

### Latency

- model inference time per note
- median and p95 per-note runtime
- dropped or skipped prediction count

For the learned model, latency should be measured on the actual deployment target:

- Python backend on CPU

## Reporting Outputs

The benchmark should write one machine-readable result file, for example:

- `research_data/causal_harmonic_benchmark.json`

Recommended top-level structure:

- benchmark metadata
- split-level results
- method-level metrics
- threshold sweeps
- latency summary
- calibration summary

## Ablations

At minimum, run:

1. legacy detector
2. causal ensemble detector
3. learned model without confidence gate
4. learned model with deployment gate
5. confidence-gated hybrid fallback:
   learned model when above threshold, otherwise causal ensemble

The fifth condition is especially important because it matches the intended runtime deployment claim.

## Statistical Reporting

Each major comparison should report:

- number of compositions
- number of evaluated notes
- confidence intervals
- effect size
- chosen statistical test
- caveats if the result is exploratory

Composition-level bootstrap intervals are preferable to treating every note as fully independent.

## First Success Criteria

The first backend harmonic model should be considered promising only if all three hold:

1. it improves at least one of the main accuracy or change-detection metrics over the causal ensemble
2. its latency remains compatible with live backend use on CPU
3. the confidence-gated hybrid condition is not worse than the classical fallback on the main stability measures

## Failure Conditions

The benchmark should explicitly record failure if:

- the learned model only wins in non-causal evaluation
- the gain disappears after confidence gating
- the gain is too small relative to latency cost
- the model becomes unstable under ambiguous passages

## Implementation Target

Status: `designed`

This document defines the benchmark protocol that the next experiment implementation should follow. It intentionally comes before any new superiority claim in the thesis text.
