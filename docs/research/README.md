# Research Documentation

This directory holds the research-facing documentation for the AI-enhanced real-time Just Intonation project.

## Purpose

The goal of this documentation is to keep the project reproducible, auditable, and thesis-ready while the implementation evolves.

The working rules for these documents are:

- state only what is verified by code, data, experiments, or cited papers
- label unresolved points explicitly as unknown
- keep design claims separate from implemented behavior
- record decisions at the time they are made
- preserve an audit trail for data handling, experiments, and evaluation

## Documents

- `research-charter.md`: scope, uncertainty rules, originality, licensing, and documentation standards
- `baseline-audit.md`: current system behavior and tuning decision points
- `current-evidence.md`: consolidated verified evidence from code, result files, and experiment records
- `literature-matrix.md`: focused review of 2021-2025 adjacent literature
- `dataset-protocol.md`: data governance, split strategy, label derivation, and leakage controls
- `harmonic-model.md`: first learned score-free harmonic-state model design
- `causal-harmonic-benchmark.md`: shared causal benchmark protocol for classical and learned score-free methods
- `backend-harmonic-integration.md`: first backend deployment contract for confidence-gated learned harmonic inference
- `function-label-pilot.md`: small-scale pilot plan for chord and Roman-numeral style labels
- `hybrid-retrieval.md`: hybrid known-piece identification design
- `hybrid-retrieval-study.md`: explicit evaluation design for transposition-sensitive and invariant learned coarse retrieval
- `evaluation-protocol.md`: metrics, ablations, statistics, and reporting requirements
- `thesis-contribution-framing.md`: thesis-level novelty boundary, contribution statement, and non-claims
- `research-log.md`: chronological record of research progress
- `decision-log.md`: key technical and methodological decisions
- `experiments/`: experiment registry, templates, and result summaries

## Status Convention

Each document should use the following terms consistently:

- `implemented`: present in the codebase and verified
- `designed`: specified in writing but not yet implemented
- `evaluated`: tested with recorded metrics
- `unknown`: not yet verified

## Notes On Data And Licensing

This repository contains dataset-derived material. The exact redistribution constraints for all ATEPP-derived assets and future generated labels are not yet fully verified. Until that is clarified, generated research artifacts should be treated as local research outputs unless explicitly confirmed otherwise.
