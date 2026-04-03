# Score-Free Baseline V1

## Question

Does the upgraded causal ensemble baseline outperform the legacy live detector when evaluated against score-derived local-key labels on held-out compositions?

## Hypothesis

The upgraded baseline will reduce spurious key changes and improve unknown-piece key tracking quality.

## Date

2026-03-09

## Code Version

Repository state after:

- `js/key-detection.js` upgrade with recency weighting, active-note weighting, score smoothing, and hysteresis
- generation of `research_data/composition_splits.json`
- generation of `research_data/score_key_labels/`

## Data Split

- validation: 44 compositions
- test: 58 compositions

## Preprocessing

- score-derived note-level labels extracted from MusicXML using the research-side parser
- causal simulation at 120 BPM equivalent timing for note onsets and durations

## Configuration

- detector 1: legacy ensemble baseline
- detector 2: current causal ensemble baseline
- evaluation target: note-level score-derived key signature labels

## Metrics

- note-level accuracy when a key is present
- prediction coverage
- number of predicted key changes
- number of score-derived key changes

## Hardware

Executed locally via Node.js in the project workspace.

## Results

Validation:

- legacy accuracy: `0.2953`
- causal ensemble accuracy: `0.1797`
- legacy predicted key changes: `777`
- causal ensemble predicted key changes: `296`

Test:

- legacy accuracy: `0.2540`
- causal ensemble accuracy: `0.2227`
- legacy predicted key changes: `970`
- causal ensemble predicted key changes: `382`

Coverage was effectively identical for both methods at approximately `99.7%`.

## Statistics

No formal significance test was run in this first pass. This is a descriptive benchmark only.

## Interpretation

This is a negative result on note-level agreement.

- the upgraded baseline is much more stable in terms of predicted key-switch count
- the upgraded baseline does **not** beat the legacy detector on note-level agreement with score-derived key labels

This suggests at least one of the following:

- the new hysteresis settings are too conservative for this label definition
- note-level key-signature labels do not reward the same notion of stability as the upgraded detector
- score-free profile methods may simply be poorly matched to this target, which strengthens the case for a learned model

## Decision

Keep the upgraded baseline as a stability-oriented classical comparator, but do not claim it as a strict accuracy improvement.

## Next Step

Train and evaluate the first learned harmonic-state model against both the legacy and causal ensemble baselines.
