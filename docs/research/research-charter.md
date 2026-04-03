# Research Charter

## Project Scope

This project investigates AI-enhanced real-time Just Intonation for MIDI performance.

The working problem is not "how to change the JI ratios." The ratio tables are largely fixed. The core problem is how to estimate the right **harmonic context** at the right time so the tuning system can select the correct ratio with minimal latency and maximal musical stability.

The project therefore has two operating modes:

1. `score-aware mode`
   For pieces that can be identified and tracked against a score, use score-derived information to drive tuning decisions.
2. `score-free mode`
   For unknown pieces or low-confidence retrieval, estimate harmonic state causally from the performed MIDI stream.

## Research Questions

The current research questions are:

1. Can a stronger score-free classical baseline outperform the existing real-time ensemble key detector for unknown pieces?
2. Can a compact learned harmonic-state model improve unknown-piece local-key tracking while staying within live latency constraints?
3. Can a hybrid known-piece identification stack improve robustness over the current exact absolute-pitch n-gram matcher?
4. Does richer harmonic context, such as chord or function, improve tuning quality beyond key-only adaptation?

## Evidence Rules

The project follows a strict uncertainty policy.

- If a claim is verified by code inspection, it may be documented as implemented behavior.
- If a claim is verified by an experiment, it must include enough detail to reproduce the result.
- If a claim is supported by a paper, the paper must be cited directly in the relevant document.
- If a claim is plausible but not verified, it must be labeled `unknown` or `hypothesis`.
- If I do not know something, I will state that directly.

## Originality And Copyright

All new code for this project should be original and human-authored.

- No copying from papers, repositories, tutorials, or model cards.
- No copying benchmark implementations unless you explicitly request that and the license allows it.
- No inclusion of code or assets with unclear ownership.

## Dependency Policy

Permissive licenses are required by default.

Preferred licenses:

- `MIT`
- `Apache-2.0`
- `BSD`
- `ISC`

If a new dependency is proposed, it must be checked for:

- license compatibility
- maintenance status
- actual need
- reproducibility impact

## Dataset Governance

The repository already includes ATEPP-derived material. The exact redistribution and publication terms for every derived artifact are not fully verified yet.

Until that is clarified:

- generated labels should be treated as research outputs, not automatically publishable assets
- checkpoints trained on dataset-derived labels should be treated cautiously
- documentation must distinguish between local research assets and intended open-source deliverables

## Reproducibility Standard

Every experiment should capture:

- research question
- hypothesis
- data split
- preprocessing version
- seed
- model configuration
- metrics
- statistical method
- hardware context
- main conclusion

## Documentation Standard

This project should be documented as a research programme, not just a software build.

Required written artifacts:

- baseline audit
- literature matrix
- dataset protocol
- evaluation protocol
- research log
- decision log
- experiment registry

## Current Boundaries

The following are outside the current verified scope:

- claiming perfect tuning for score-aware mode
- claiming robust automatic Roman numeral labels for the full dataset
- claiming browser-side learned inference is necessary
- claiming dataset-derived research artifacts are all redistributable

These points remain open until verified.
