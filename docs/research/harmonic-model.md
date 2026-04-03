# Harmonic Model Design

## Objective

The first learned model targets the unknown-piece path.

Its job is not to predict direct cents offsets immediately. Its first job is to estimate a stable **local harmonic state** from the recent MIDI stream, with low enough latency to support live use.

## First Target

Primary output:

- `local key + mode`

Secondary output:

- calibrated confidence for the prediction

Later optional outputs:

- chord label
- Roman numeral or function
- direct tuning target

## Why This Ordering

This ordering is deliberate.

- `local key + mode` is the cleanest first target and aligns with the current system
- confidence is necessary for safe fallback behavior
- chord and function are useful, but only if label quality is good enough
- direct cents prediction should come later because it is harder to validate and easier to overclaim

## Input Representation

The model should operate causally on recent MIDI note events.

The current feature set is designed, not yet fully validated:

- pitch class
- register bucket
- inter-onset interval bucket
- duration bucket when available
- velocity bucket when available
- active-note pitch-class mask
- active-note count

The active-note context matters because purely note-on-count models miss part of the vertical harmony.

## Model Family

The first model family should stay compact and CPU-friendly.

Recommended starting point:

- small causal `GRU` or other compact recurrent model

Why:

- simple to train
- easy to reason about causality
- low inference overhead
- suitable for a first backend model before considering distillation or browser inference

## Inference Policy

The learned model should never force a risky switch when it is uncertain.

Required behavior:

- if confidence is high, provide a local-key prediction
- if confidence is low, defer to the stronger classical score-free baseline
- if the piece later becomes identified with high confidence, hand off to the score-aware path

## Training Protocol

The first training stage should rely on score-derived labels where available.

Planned approach:

1. derive note-level local-key labels from MusicXML
2. train on score-note sequences first
3. use sequence augmentations to simulate performance variability
4. evaluate on held-out compositions only

This avoids assuming a verified note-level performance-to-score alignment resource that has not yet been confirmed in this repository snapshot.

## Open Risks

- score-derived local keys may underrepresent local tonicization
- performance realism of synthetic augmentations may be limited
- label quality for function-aware extensions is still unknown

## Implementation Status

- design: `implemented in documentation`
- training code: `implemented in Python`
- runtime wrapper: `implemented in Python`
- smoke training: `completed`
- held-out window evaluation: `completed`
- live integration: `planned as optional backend inference`
