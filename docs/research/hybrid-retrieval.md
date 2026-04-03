# Hybrid Retrieval Design

## Objective

The known-piece path currently relies on exact absolute-pitch n-gram fingerprinting.

That is a strong baseline, but it is likely brittle under:

- transposition
- expressive deviations
- partial early observations
- ornamentation and structural noise

The target architecture is therefore a hybrid stack:

1. coarse candidate generation
2. exact or alignment-based reranking

## Planned Architecture

### Stage A: Coarse Retrieval

The long-term target is a learned symbolic embedding model that maps short MIDI performance slices to a vector space.

Desired properties:

- tolerance to expressive timing variation
- useful early retrieval from partial observations
- optional controlled transposition robustness
- low enough cost for real-time candidate generation

### Stage B: Deterministic Reranking

The current exact matcher should remain as a verified reranking baseline.

Candidate reranking options:

- existing exact n-gram matcher
- note-alignment or sequence-alignment reranker
- hybrid confidence score combining coarse and exact evidence

## Why Hybrid Rather Than Replacement

Replacing exact retrieval with a learned model alone would make the system harder to interpret.

A hybrid system is preferable because:

- coarse retrieval improves robustness
- deterministic reranking keeps the final choice auditable
- failure analysis remains clearer

## First Implementation Rule

Until a trained embedding model is available, the code should support:

- exact retrieval as the verified baseline
- optional pluggable coarse retrieval modules
- clear fallback if no embedding index or model checkpoint is present

## Evaluation Requirements

Known-piece identification must be evaluated with:

- top-1 accuracy
- top-k accuracy
- MRR
- notes-to-identification
- robustness under timing variation
- robustness under transposition, if that is part of the retrieval objective

## Open Questions

- I do not yet know whether the final system should be transposition-invariant or merely more tolerant to expressive deviation. That depends on the intended use case for known-piece identification.
- I do not yet know whether a trained symbolic encoder will be more effective than a stronger handcrafted coarse retriever in this dataset regime.

## Implementation Status

- design: `implemented in documentation`
- retrieval baseline: `already implemented in the repository`
- hybrid infrastructure: `implemented in Python`
- backend coarse-index hook: `implemented as optional server path`
- small-subset smoke test: `completed`
