# Literature Matrix

## Scope

This matrix focuses on adjacent work from 2021-2025 relevant to the project:

- symbolic harmony and function modeling
- local-key estimation from symbolic music
- symbolic representation learning
- retrieval and identification
- score following and alignment

The project still needs a fuller literature review before any novelty claim is finalized. The entries below are verified from paper abstracts or paper text reviewed during planning.

## Matrix

| Area | Paper | Year | Modality | Main Idea | Direct Relevance |
| --- | --- | --- | --- | --- | --- |
| Symbolic harmony | Su and Chen, *Attend to Chords: Improving Harmonic Analysis of Symbolic Music Using Transformer-Based Models* | 2021 | Symbolic | Transformer-based chord and functional harmony recognition | Strong reference for chord and function modeling beyond simple key detection |
| Symbolic pretraining | Zeng et al., *MusicBERT: Symbolic Music Understanding with Large-Scale Pre-Training* | 2021 | Symbolic | Large-scale pretraining for symbolic music understanding | Useful as a representation-learning reference for future retrieval or harmonic-state models |
| Symbolic pretraining | Chou et al., *MidiBERT-Piano: Large-scale Pre-training for Symbolic Music Understanding* | 2021 | Symbolic piano MIDI | BERT-style pretraining for symbolic piano tasks | Relevant for compact symbolic encoders under limited labels |
| Retrieval | Yang et al., *Large-Scale Multimodal Piano Music Identification Using Marketplace Fingerprinting* | 2022 | Sheet, MIDI, audio | Large-scale retrieval with efficient multimodal fingerprinting | Important retrieval baseline and design reference for known-piece identification |
| Roman numeral analysis | Karystinaios and Widmer, *Roman Numeral Analysis with Graph Neural Networks: Onset-wise Predictions from Note-wise Features* | 2023 | Symbolic | GNN-based Roman numeral analysis from note-wise inputs | Strong evidence that richer harmonic labels are feasible from symbolic note structure |
| Local key estimation | Bouquillard and Jacquemard, *Engraving Oriented Joint Estimation of Pitch Spelling and Local and Global Keys* | 2024 | MIDI / symbolic | Dynamic-programming method for pitch spelling and local/global key estimation | High-value baseline reference for non-neural local-key tracking |
| Score-note alignment | Peter and Widmer, *TheGlueNote: Learned Representations for Robust and Flexible Note Alignment* | 2024 | Symbolic MIDI | Transformer-based note alignment robust to structural mismatches | Relevant for robust sequence matching and possible reranking in hybrid retrieval |
| Score following | Pillay, *A Neural Score Follower for Computer Accompaniment of Polyphonic Musical Instruments* | 2024 | Score following | Neural score-following exploration with explicit discussion of limitations | Useful cautionary reference: neural alignment does not automatically beat classical methods |
| Symbolic representation learning | Bradbury et al., *Scaling Self-Supervised Representation Learning for Symbolic Piano Performance* | 2025 | Symbolic piano performance | Large-scale pretrained and contrastive symbolic performance representations | Important reference for learned coarse retrieval and future embedding work |
| Score following benchmark | Park et al., *Matchmaker: An Open-Source Library for Real-Time Piano Score Following and Systematic Evaluation* | 2025 | Score following | Benchmarking framework for real-time piano alignment | Valuable for evaluation methodology and reporting discipline |
| Symbolic chord recognition | Yao et al., *BACHI: Boundary-Aware Symbolic Chord Recognition Through Masked Iterative Decoding on Pop and Classical Music* | 2025 | Symbolic | Boundary-aware symbolic chord recognition with strong performance | Supports the case for chord-aware harmonic-state estimation |

## Reading Notes

### Harmony And Function

- The 2021 and 2023 symbolic harmony papers suggest that chord and Roman numeral modeling are realistic research targets in symbolic music.
- They are relevant because the current JI system only uses tonic and mode in the live path and MusicXML key signatures in the score-aware path.

### Local Key

- The 2024 dynamic-programming local-key paper is especially important because it offers a rigorous symbolic baseline that does not depend on a learned model.
- This is directly useful for the unknown-piece path, where a stronger classical baseline should be built before claiming a neural improvement.

### Retrieval

- Marketplace fingerprinting and large-scale symbolic embedding work both matter for the known-piece path.
- The current repository uses exact absolute-pitch n-grams, so there is a clear gap between the existing system and newer retrieval ideas.

### Alignment

- TheGlueNote and Matchmaker are useful because they make the alignment discussion more rigorous.
- The neural score-following thesis is important because it reports limitations openly, which is a useful reminder not to assume that a neural replacement is automatically better in a live system.

## Current Literature-Based Position

My current evidence-based position is:

- there is strong adjacent literature on symbolic harmony, representation learning, retrieval, and alignment
- there appears to be limited recent direct literature on AI-driven real-time adaptive Just Intonation for symbolic MIDI performance

This is promising for novelty, but it should remain a provisional assessment until the literature review is expanded further.

## Unknowns

- I have not yet completed a full Google Scholar sweep for every variant of "adaptive intonation", "dynamic tuning", and "just intonation" combined with symbolic MIR terminology.
- I do not yet know whether there are very recent niche workshop papers that narrow the novelty gap further.
