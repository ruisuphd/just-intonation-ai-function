# Hybrid Retrieval Study

## Objective

Evaluate whether a learned symbolic coarse retriever improves known-piece identification over the current exact absolute-pitch fingerprint baseline.

The study must compare two explicit learned variants:

- transposition-sensitive coarse retrieval
- transposition-invariant coarse retrieval

Both variants keep exact fingerprints as the deterministic reranking stage.

## Why This Study Matters

The current exact matcher is already useful and auditable, but its limitations are clear:

- exact pitch dependence
- sensitivity to early partial observations
- brittleness under expressive deviation

Recent adjacent work supports a stronger first stage:

- Yang et al. (2022) show that smarter candidate generation can improve retrieval efficiency and accuracy
- Bradbury et al. (2025) show that contrastive symbolic piano embeddings are now realistic at scale
- TheGlueNote (2024) shows that mismatch-oriented augmentations matter when symbolic sequences diverge structurally

## Existing Repo Baseline

Already implemented:

- `simple_ngram_fingerprinting.py`
- `hybrid_piece_identifier.py`
- `build_hybrid_identifier_db.py`
- `two_stage_server.py`

Current coarse stage:

- lightweight statistical retrieval

Current reranking stage:

- exact n-gram fingerprints

This means the codebase already has the right architecture for the study. The missing piece is the learned coarse encoder.

## Evaluation Questions

1. Does learned coarse retrieval improve top-k candidate quality over the current exact-first path?
2. Does it reduce notes-to-identification?
3. Is transposition invariance helpful or harmful for this project’s use case?
4. Does deterministic reranking preserve interpretability while capturing most of the gain?

## Candidate Representation

The coarse retriever should embed short symbolic performance slices, not full pieces at once.

Recommended per-event features:

- pitch class
- register bucket
- inter-onset interval bucket
- duration bucket when available
- velocity bucket when available
- active-note pitch-class mask
- active-note count

This stays aligned with the current harmonic-model feature philosophy and avoids introducing an unrelated representation.

## Training Setup

### Positive Pairs

Use different slices from performances of the same composition.

Positive pairs should vary by:

- performer
- local position within the piece
- tempo
- expressive timing

### Negative Pairs

Use slices from different compositions.

Hard negatives should be included where possible:

- same composer
- similar texture
- similar local key
- similar note density

## Variant A: Transposition-Sensitive

Training rule:

- do not normalize away absolute pitch
- allow ordinary tempo and expression augmentation
- do not apply pitch-shift augmentation

Hypothesis:

- this variant may preserve information that helps early identification in the original performed key
- it may also help handoff into harmonic-context reasoning because retrieved candidates remain key-specific

Risk:

- it may stay too close to the brittleness of the current exact baseline

## Variant B: Transposition-Invariant

Training rule:

- apply pitch-shift augmentation during contrastive training
- evaluate same-piece retrieval under controlled transpositions

Hypothesis:

- this variant should improve robustness when a piece is performed in another key
- it may also improve tolerance to some symbolic mismatch cases by focusing on interval and contour structure

Risk:

- it may discard musically useful key-specific evidence and increase confusion among structurally similar pieces

## Recommended Model Family

First learned coarse model:

- compact sequence encoder
- GRU or small Transformer
- contrastive objective over short slices

Do not start with a giant pretrained model inside the runtime path.

Use large pretrained encoders only as optional offline baselines if needed later.

## Augmentations

Both learned variants should use:

- tempo scaling
- note dropout
- onset jitter
- duration jitter
- velocity jitter
- short insertions or deletions

The transposition-invariant variant additionally uses pitch-shift augmentation.

The augmentation design should stay explicit and reproducible because it directly shapes what “robustness” means.

## Reranking Rule

The final choice must remain auditable.

Required retrieval stack:

1. learned coarse top-k candidate generation
2. exact fingerprint reranking
3. optional hybrid confidence score combining:
   - coarse similarity
   - exact fingerprint vote share
   - fingerprint coverage

Do not replace the exact stage with a learned score alone in the first thesis study.

## Metrics

Primary:

- top-1 accuracy
- top-k accuracy
- MRR
- notes-to-identification

Robustness probes:

- partial early observation
- tempo variation
- ornamentation or note dropout
- transposition

The transposition probe is mandatory because it is one of the explicit study questions.

## Recommended Experimental Conditions

At minimum compare:

1. exact fingerprints only
2. current statistical coarse retrieval plus exact reranking
3. learned transposition-sensitive coarse retrieval plus exact reranking
4. learned transposition-invariant coarse retrieval plus exact reranking

Optional fifth condition:

5. learned coarse retrieval only, without reranking

This optional fifth condition is useful only as an ablation, not as the preferred deployment design.

## Success Criteria

The learned hybrid path should only be treated as a meaningful improvement if it achieves both:

- better `notes-to-identification` than exact-only retrieval
- better top-k candidate quality without making failure analysis opaque

If the transposition-invariant variant only helps on synthetic transposition tests but hurts same-key early identification, that trade-off must be reported directly rather than hidden.

## Recommended Outputs

- `research_data/retrieval_splits.json` if a dedicated retrieval manifest is needed
- `research_data/hybrid_retrieval_eval_sensitive.json`
- `research_data/hybrid_retrieval_eval_invariant.json`
- `docs/research/experiments/<date>-hybrid-retrieval-v1.md`

## Deployment Rule After The Study

Choose the live coarse retriever by this rule:

1. if the transposition-sensitive model wins on the main real-use metrics, deploy that one
2. if the invariant model substantially reduces notes-to-identification without harming the main case, deploy the invariant model
3. if neither beats the current statistical stage clearly, keep the current hybrid scaffold and report the negative result

## Status

Status: `designed`

The study is now specified as a real comparison rather than a vague “use AI for fingerprinting” direction.
