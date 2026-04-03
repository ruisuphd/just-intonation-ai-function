# Thesis Contribution Framing

## Working Thesis Claim

This thesis investigates AI-assisted real-time harmonic-context estimation for adaptive Just Intonation in MIDI performance.

The core claim is not that the project invents new Just Intonation ratios.

The core claim is that it combines:

- a high-resolution MTS-MPE tuning engine
- causal harmonic-state estimation for unknown pieces
- hybrid known-piece identification for score-aware tuning

into one research system aimed at improving live adaptive tuning on keyboard and struck-string MIDI instruments.

## What The Thesis Is Actually Contributing

### Contribution 1: Harmonic-Context Estimation As The Central Problem

The thesis reframes adaptive JI for MIDI as a real-time harmonic-context problem.

This matters because the ratio tables are mostly fixed. The unresolved problem is selecting the correct tonal reference quickly, stably, and causally enough for live use.

### Contribution 2: Confidence-Gated Learned Harmonic Tracking

For unknown pieces, the thesis contributes a learned harmonic-state path that is:

- causal
- latency-aware
- confidence-gated
- integrated with a classical fallback

This is a more defensible claim than promising end-to-end direct tuning prediction from the start.

### Contribution 3: Hybrid Known-Piece Identification

For known pieces, the thesis contributes a hybrid identification design:

- learned or stronger coarse retrieval
- deterministic exact fingerprint reranking

This is important because it improves robustness without throwing away interpretability.

### Contribution 4: Practical Tuning Delivery

The project already contributes an MTS-MPE tuning engine that makes the adaptive-tuning research deployable on contemporary MIDI hardware.

That engineering layer is not the whole thesis, but it is a real and necessary contribution because it connects harmonic decisions to high-resolution tuning output.

## What The Thesis Is Not Claiming

The framing must stay disciplined.

The thesis is **not** claiming:

- the invention of new JI ratio systems
- the first adaptive intonation system overall
- perfect harmonic analysis from score or performance
- a general breakthrough in neural score following
- browser-side learned inference as a necessary contribution

These non-claims are important because they separate a realistic contribution from an inflated one.

## How The Thesis Differs From Prior Adaptive-Tuning Systems

### Earlier Adaptive JI Systems

Earlier adaptive-tuning work already exists, including:

- Hermode-style adaptive tuning systems
- Stange, Wick, and Hinrichsen (2018), *Playing Music in Just Intonation: A Dynamically Adaptive Tuning Scheme*
- more recent tools such as Pivotuner (2023)

These systems are important neighbors, but they are not the same research problem.

Their center of gravity is adaptive tuning behavior itself:

- tuning-center choice
- tempered compromise handling
- performer control of adaptive intonation

This thesis instead focuses on AI-assisted estimation of harmonic context from symbolic performance streams and score-linked retrieval.

## How The Thesis Differs From Recent Symbolic MIR Work

Recent MIR literature is strong in adjacent areas:

- symbolic harmony recognition
- Roman numeral analysis
- symbolic representation learning
- retrieval and alignment

Representative references:

- Su and Chen (2021), transformer-based symbolic harmony recognition
- Karystinaios and Widmer (2023), Roman numeral analysis with GNNs
- Bouquillard and Jacquemard (2024), dynamic-programming local and global key estimation
- Peter and Widmer (2024), TheGlueNote for robust symbolic note alignment
- Yang et al. (2022), marketplace fingerprinting
- Bradbury et al. (2025), large-scale symbolic piano embeddings
- Park et al. (2025), Matchmaker score-following evaluation
- Pillay (2025), a useful negative caution on neural score following

These works make the thesis feasible and academically grounded.

But none of them directly closes the loop from:

- symbolic performance input
- to real-time harmonic-context inference
- to adaptive JI tuning output
- in one MIDI-oriented system

That loop is the thesis niche.

## Defensible Novelty Statement

The most defensible novelty statement at this stage is:

> The thesis contributes an AI-assisted, real-time adaptive Just Intonation system for MIDI performance that combines causal score-free harmonic tracking, hybrid known-piece identification, and high-resolution MTS-MPE tuning delivery, while evaluating the trade-off between harmonic accuracy, robustness, and live latency.

This statement is strong enough to be interesting and narrow enough to defend.

## Recommended Paper / Chapter Structure

### Chapter Or Paper 1

Topic:

- causal harmonic-state estimation for unknown-piece adaptive JI

Main comparison:

- legacy detector vs causal ensemble vs learned model vs confidence-gated hybrid fallback

### Chapter Or Paper 2

Topic:

- hybrid symbolic retrieval for early known-piece identification

Main comparison:

- exact fingerprints vs learned coarse retrieval plus exact reranking
- transposition-sensitive vs transposition-invariant coarse retrieval

### Later Thesis Chapter

Topic:

- whether richer harmonic context beyond key-only adaptation improves tuning quality

This later chapter should only be promoted if the function-label pilot supports it.

## Recommended Abstract-Level Language

Use phrasing like:

- `AI-assisted adaptive Just Intonation`
- `harmonic-context estimation`
- `causal symbolic inference`
- `confidence-gated fallback`
- `hybrid retrieval with deterministic reranking`
- `MTS-MPE tuning delivery`

Avoid overclaiming phrases like:

- `fully intelligent tuning`
- `solves harmony`
- `perfectly consonant`
- `neural score following breakthrough`

## Bottom Line

The thesis is strongest when presented as a tightly scoped research program:

- not new tuning ratios
- not only a plugin
- not only a MIR classifier
- but a real-time symbolic AI system for choosing better tuning references and delivering them through modern MIDI tuning pathways

## Status

Status: `designed`

This framing is ready to use in thesis planning, paper outlines, and future introduction sections, subject to the fuller literature review staying consistent with the current novelty assessment.
