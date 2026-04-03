# Hybrid Identifier Smoke Test

## Question

Does the new hybrid identification infrastructure execute end to end on a small subset?

## Hypothesis

The hybrid identifier should build a coarse index and exact fingerprint database, then return the query piece at rank 1 for an in-database query.

## Date

2026-03-09

## Code Version

Repository state after:

- addition of `hybrid_piece_identifier.py`
- addition of `build_hybrid_identifier_db.py`
- optional coarse-index integration in `two_stage_server.py`

## Data Split

Not a formal split. Smoke test only on a small subset of `8` compositions.

## Preprocessing

- one MIDI file per composition
- metadata names used as piece ids

## Configuration

- coarse stage: statistical symbolic features
- reranking stage: exact n-gram fingerprints
- query: first item from the small subset

## Metrics

- top-1 retrieval on the smoke-test query
- basic confidence and coarse score sanity check

## Hardware

Executed locally in Python on CPU.

## Results

The query piece was returned at rank 1 with:

- confidence: `100.0`
- coverage: `100.0`
- coarse score: `1.0`

## Statistics

No formal statistics. This was only a functional smoke test.

## Interpretation

The hybrid retrieval code path is operational on a small controlled subset.

This does **not** establish retrieval quality on the full dataset.

## Decision

Keep the hybrid infrastructure and full-index build script in the repository, but treat full-scale evaluation as future work.

## Next Step

Run a full known-piece retrieval benchmark once the hybrid index is built over the complete research subset.
