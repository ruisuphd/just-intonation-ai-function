# Current Evidence Audit

## Purpose

This document consolidates the currently verified evidence for the AI-enhanced Just Intonation project.

It is not a design proposal. It records what is already supported by code inspection, result files, and existing experiment notes.

## System Baseline

### Score-Free Runtime

Status: `implemented` and `evaluated`

Verified from:

- `js/main.js`
- `js/key-detection.js`
- `docs/research/baseline-audit.md`
- `research_data/score_free_baseline_benchmark.json`

Current behavior:

- the browser maintains a `2000 ms` sliding note buffer
- key detection starts after at least `8` note events
- the active score-free detector is a causal ensemble over Albrecht-Shanahan, Temperley, and Krumhansl-Kessler pitch-class profiles
- the current detector adds recency weighting, velocity weighting, active-note weighting, score smoothing, and hysteresis
- tuning remains key-relative in the score-free path

Held-out benchmark evidence:

- legacy validation accuracy: `0.2953`
- current causal ensemble validation accuracy: `0.1797`
- legacy test accuracy: `0.2540`
- current causal ensemble test accuracy: `0.2227`
- current causal ensemble predicted far fewer key changes than the legacy detector

Interpretation:

- the current classical baseline is more stable
- the current classical baseline is not yet better on note-level agreement with score-derived labels
- this is a genuine opening for learned harmonic-state inference

### Score-Aware Runtime

Status: `implemented`

Verified from:

- `two_stage_server.py`
- `two_stage_client.js`
- `docs/research/baseline-audit.md`

Current behavior:

- performed note-ons are buffered for identification
- the backend identifies a piece using exact absolute-pitch n-gram fingerprints
- if a score is available, the backend initializes Parangonar score following
- predicted upcoming notes are mapped to MusicXML key signatures
- the frontend prefers predictive note-level tuning when available and otherwise falls back to the score-free path

Main limitation:

- score-aware note-level tuning is still derived from key signature context rather than explicit chord or Roman numeral analysis

## Learned Harmonic Model

Status: `implemented`, `evaluated`, not fully live-integrated at the start of this audit

Verified from:

- `harmonic_context_model.py`
- `train_harmonic_context_model.py`
- `evaluate_harmonic_context_model.py`
- `harmonic_context_runtime.py`
- `research_data/harmonic_context_eval.json`
- `docs/research/experiments/2026-03-09-harmonic-model-smoke.md`
- `docs/research/experiments/2026-03-09-harmonic-model-eval-v1.md`

Current model properties:

- compact causal `GRU`
- event-level symbolic inputs: pitch class, register, inter-onset bucket, duration bucket, velocity bucket, active-note mask
- output target: local key label over 24 classes
- runtime wrapper only emits predictions above a confidence threshold

Held-out window evaluation:

- validation loss: `1.7587`
- validation accuracy: `0.3756`
- test loss: `1.6218`
- test accuracy: `0.4310`

Interpretation:

- the learned model produces a stronger held-out signal than the current classical score-free benchmark numbers
- the comparison is still not apples-to-apples because the model was evaluated on fixed windows while the classical baseline was evaluated as a causal state machine over full sequences
- the next valid claim must therefore come from one shared causal protocol

## Known-Piece Retrieval

Status: exact baseline `implemented`; hybrid infrastructure `implemented`; learned coarse retrieval `not yet implemented`

Verified from:

- `simple_ngram_fingerprinting.py`
- `hybrid_piece_identifier.py`
- `build_hybrid_identifier_db.py`
- `two_stage_server.py`
- `docs/research/hybrid-retrieval.md`
- `docs/research/experiments/2026-03-09-hybrid-identifier-smoke.md`

Current exact baseline:

- uses absolute-pitch `4`-gram fingerprints
- confidence is based on matched fingerprint vote share
- retrieval is deterministic and interpretable

Current hybrid scaffold:

- coarse retrieval based on lightweight symbolic statistics
- exact fingerprint reranking
- optional coarse-index loading in the backend

Current evidence level:

- smoke-test only on a small subset
- no full held-out benchmark yet

Main limitation:

- the current exact baseline is likely sensitive to transposition, expressive deviations, and partial early observations

## Dataset And Label Evidence

Status: `implemented`

Verified from:

- `docs/research/dataset-protocol.md`
- `ATEPP_JI_Dataset/README.md`
- `research_data/composition_splits.json`
- `research_data/score_key_labels/1585.json`

Dataset facts currently in scope:

- `5,091` MIDI performances
- `319` unique compositions
- `319` MusicXML scores
- `13` composers

Research split facts:

- train: `217` compositions / `3453` performances
- validation: `44` compositions / `733` performances
- test: `58` compositions / `905` performances

Current label families actually present:

- composition-level retrieval labels through `composition_id`
- score-note local-key labels
- note-level scale degree
- note-level JI ratio and cents-offset teacher targets

Important limitation:

- reliable corpus-wide harmonic-function or Roman numeral labels are not yet verified

## Real-Time Output Contribution

Status: `implemented`

Verified from:

- `js/tuning-core.js`
- `js/tuning-mts.js`
- `js/tuning-mpe.js`
- `js/tuning-midi2.js`
- `README.md`

Current contribution already present in the repository:

- MTS-MPE tuning engine for higher-resolution MIDI tuning output
- browser-side and file-export support for microtuned output
- explicit MTS vs MPE fallback path

This remains an important engineering contribution even when the AI contribution is evaluated separately.

## Literature Position

Status: `partially verified`

Verified from:

- `docs/research/literature-matrix.md`
- direct paper checks completed during roadmap preparation

Current evidence-based position:

- recent literature is strong in symbolic harmony modeling, Roman numeral analysis, symbolic representation learning, retrieval, and score alignment
- there still appears to be limited direct recent literature on AI-driven real-time adaptive Just Intonation for symbolic MIDI performance

This remains a provisional novelty position and should stay labeled that way until the fuller thesis literature review is complete.

## Main Verified Gaps

- no apples-to-apples causal benchmark yet between the learned harmonic model and the classical score-free detectors
- no first-class backend deployment path for the harmonic model was present at the start of this audit
- no reliable large-scale function-label pipeline yet
- no full retrieval benchmark for the hybrid path yet
- no perceptual evaluation protocol has been executed yet for tuning-quality claims

## Immediate Research Consequence

The strongest next claim is not direct end-to-end tuning prediction.

The strongest next claim is:

1. a causal backend harmonic-state model for unknown pieces
2. confidence-aware fallback into the existing classical detector
3. evaluated under the same causal protocol and latency constraints as the classical baseline
