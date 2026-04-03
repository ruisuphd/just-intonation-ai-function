# PhD AI Improvement Roadmap — Instant Harmonies
### Research-Grounded Development Plan (March 2026)

---

## Executive Summary

This roadmap maps four targeted AI improvements onto your existing codebase, grounded in published literature through early 2026. It addresses the three gaps you identified — (1) local key detection, (2) song identification from the ATEPP database, and (3) handling restricted MusicXML — and adds a fourth that is already implied by your thesis framing: upgrading the score-following backend to match the current state of the art. Each section states the problem precisely, names the relevant papers with full citations, identifies which files to modify, and proposes concrete implementation steps.

Your MTS-MPE layer is architecturally sound and the core of your fourth published contribution, so it is treated here as a stable foundation rather than a target for structural change. Minor refinements are noted at the end.

---

## Contribution A (Paper 2): S-KEY-Symbolic — Self-Supervised Local Key Detection from MIDI Streams

### The Gap

Your current score-free key detector in `js/key-detection.js` is a weighted ensemble of three classical pitch-class profile families: Albrecht-Shanahan (2013), Temperley (1999), and Krumhansl-Kessler (1982). The ensemble is well-implemented and already beats any single profile family. Its fundamental limitations are documented in your baseline audit:

- It cannot model tonicization or short-duration chromatic detours without treating them as modulations.
- It has no learned prior over common harmonic motion in the repertoire you care about (Beethoven, Schubert, Debussy, etc.).
- It treats all pitch classes symmetrically; it cannot exploit sequential pitch patterns, chord voicings, or metric position.
- Its score-free GRU backend (`harmonic_context_model.py`) has an 80-dimensional input, a single GRU layer of 96 hidden units, and no attention mechanism — adequate as a proof of concept but well below the current learned baseline.

The key question is: **can you build a self-supervised symbolic key detector that trains on your ATEPP corpus without requiring hand-annotated key labels, distinguishes major from minor reliably, and is causal enough to run in the browser in real time?**

### Relevant Papers

**S-KEY: Self-supervised Learning of Major and Minor Keys from Audio**
Kong, Y., Meseguer-Brocal, G., Lostanlen, V., Lagrange, M., & Hennequin, R.
ICASSP 2025. arXiv: 2501.12907. Deezer Research. Code: github.com/deezer/s-key (MIT licence).

S-KEY is the most important single paper for this contribution, but it needs adaptation because it operates on audio (constant-Q transforms), not symbolic MIDI. Its architectural innovations are fully portable to the symbolic domain. The core novelty of S-KEY is a two-part training objective:

1. A CPSD (cross-power spectral density) loss that enforces pitch-transposition equivariance — the network must produce consistent key predictions even when the same piece is transposed.
2. An auxiliary binary cross-entropy loss using pseudo-labels derived from comparing chroma energy at the root of the major key versus its relative minor, which allows S-KEY to distinguish (say) C major from A minor without any human annotation.

S-KEY trains on one million songs and achieves MIREX weighted scores of 73.2% on FMAKv2, 74.4% on GTZAN, and 90.4% on Schubert Winterreise — matching supervised deep learning with zero manual labels. Crucially, it outperforms its predecessor STONE (ISMIR 2024, same team) precisely because STONE cannot discriminate relative keys.

**STONE: Self-supervised Tonality Estimator**
Kong, Y., Meseguer-Brocal, G., Lagrange, M., & Hennequin, R.
ISMIR 2024. arXiv: 2407.07408. Code: github.com/deezer/stone (MIT licence).

STONE is the predecessor to S-KEY. Its ChromaNet architecture (a convnet with octave-equivalence structure) provides the template for building a pitch-equivariant encoder. The pretext task — predicting the pitch transposition interval between two excerpts from the same track via a circle-of-fifths metric — is the mechanism that makes the encoder tonality-aware without labels.

**Towards Robust Local Key Estimation with a Musically Inspired Neural Network (OctaveNet)**
Ding, Y. & Weiß, C.
EUSIPCO 2024. IEEE Xplore DOI: 10.1109/EUSIPCO60164.2024.10715249.

OctaveNet is important because it directly targets *local* (not global) key estimation and is designed around the musical structure of CQT frequency bins — rearranging the spectrogram into two branches (octave-folded and sequential), then fusing them with convolutional and recurrent layers. Despite having fewer parameters than previous approaches, it achieves substantially better generalisation to unseen songs. Its two-branch fusion idea transfers naturally to a symbolic input: one branch over pitch-class distributions, one over the pitch sequence with octave information retained.

**A Regularization Algorithm for Local Key Detection**
Gedizlioğlu, C. & Erol, K.
Psychology of Music, 2024. DOI: 10.1177/10298649241245075.

This is the most directly applicable paper to your symbolic/MIDI setting. It models local key detection as a segmentation-and-optimisation problem, using a modified Krumhansl-Schmuckler profile and a regularisation term that penalises superfluous modulations — specifically designed to prevent the system from interpreting tonicized chords as genuine key changes. It inputs symbolic MIDI, not audio, making it directly applicable as either a standalone improvement to your JS layer or as a training-free preprocessing step for your GRU backend.

### What Your Contribution Would Be

Your original contribution is not re-implementing S-KEY — it is the first self-supervised local key estimator designed for symbolic MIDI streams and evaluated in a real-time browser context on struck-string piano repertoire. Specifically:

You adapt S-KEY's two-part self-supervised objective to operate on note-event sequences rather than audio spectrograms:

- The pitch-equivariance pretext task becomes: given two note sequences that are transpositions of each other (easily constructed from your 5,091-performance ATEPP corpus by shifting all MIDI pitch values by a fixed interval), predict the interval of transposition via a circle-of-fifths distance loss. No labels needed.
- The major/minor disambiguation auxiliary task becomes: compute a chroma histogram from the note window; compare summed energy at the root pitch class of the candidate major key versus its relative minor; assign a soft pseudo-label using the same rule S-KEY uses.
- The architecture upgrades the current single-GRU to a lightweight causal Transformer encoder (4 heads, 2 layers, 128-dimensional hidden state), designed to run in under 3 ms per note event on a modern CPU — consistent with your latency requirements.

Adoption of the OctaveNet two-branch idea in symbolic form: one branch processes pitch-class (12-bin, octave-folded) histograms over a sliding window; the other processes the raw pitch sequence (MIDI note numbers) to retain octave information. The two branches are fused before the softmax output.

Adoption of the Gedizlioğlu regularisation for post-processing: after the learned model outputs a sequence of key predictions, a regularisation pass suppresses very short key segments below a configurable minimum duration (e.g. 4 beats), treating them as tonicizations rather than modulations.

### Files to Modify

| File | Nature of Change |
|---|---|
| `harmonic_context_model.py` | Replace GRU with lightweight causal Transformer; add two-branch input (PCP + raw pitch); expose self-supervised training objective |
| `train_harmonic_context_model.py` | Add self-supervised pre-training loop (equivariance loss + auxiliary pseudo-label loss) before supervised fine-tuning on score key labels |
| `harmonic_context_runtime.py` | Update inference wrapper for new architecture; add regularisation post-processing pass |
| `js/key-detection.js` | Optionally port the trained model to ONNX and run it via ONNX Runtime Web; keep classical ensemble as a fallback; expose a unified confidence score |
| `evaluate_harmonic_context_model.py` | Add evaluation on tonicization cases; report MIREX weighted score alongside accuracy |

### Implementation Priority

Self-supervised pre-training first on ATEPP (no labels required — just transpose the 5,091 MIDIs to generate transposition pairs). Supervised fine-tuning second on your 319 score-key label JSONs. The pre-training step is where the novelty lies; fine-tuning is the same procedure you already use.

---

## Contribution B (Paper 3): Transposition-Invariant Hybrid Piece Identification with Contrastive Symbolic Embeddings

### The Gap

Your current piece identifier in `simple_ngram_fingerprinting.py` and `hybrid_piece_identifier.py` uses absolute-pitch 4-grams as the exact reranking signal. Your baseline audit correctly identifies that this is transposition-sensitive and fragile to expressive deviations. The coarse retriever uses symbolic statistics (interval histogram, IOI buckets, register histogram) which are somewhat more robust, but the final reranking step collapses if the user plays even a few semitones away from the reference pitch.

In practice, digital pianos are sometimes tuned away from A=440, and users may play a transcription in a different key. Your 177 MB fingerprint database would need to be rebuilt in all 12 transpositions to be fully robust — a 2 GB overhead that is not practical.

### Relevant Papers

**CLaMP: Contrastive Language-Music Pre-training for Cross-Modal Symbolic Music Information Retrieval**
Wu, S., et al.
ISMIR 2023 (Best Student Paper Award). arXiv: 2304.11029. Code: github.com/microsoft/muzic/tree/main/clamp.

CLaMP trains a music encoder and a text encoder jointly with InfoNCE contrastive loss on 1.4 million (music, text) pairs. For your purposes, the key design element is not the text encoder — it is the music encoder: a bar-patching Transformer that reduces sequence length to under 10% of the original by representing music in bar-level patches rather than individual notes. The encoder learns pitch-class invariant representations through contrastive augmentation (including transposition augmentation during training). CLaMP 3 (arXiv: 2502.10362, February 2026) extends this to 2.6 million pairs and achieves state-of-the-art on multiple symbolic retrieval benchmarks.

The direct relevance: you can train a contrastive symbolic encoder on your 5,091 MIDI performances without any text labels, using only piece identity as the positive pair signal (two performances of the same piece are a positive pair) and transposition as an augmentation. This replaces your coarse retriever with a learned embedding that is both transposition-invariant and expressive-deviation-tolerant.

**Piano Sheet Music Identification Using Dynamic N-gram Fingerprinting**
Baptista, C., et al.
TISMIR (Transactions of ISMIR), 2021. DOI: 10.5334/tismir.70.

This paper's dynamic n-gram hashing — where the fingerprint discriminativeness is checked at construction time and only sufficiently distinctive n-grams are stored — is the state-of-the-art engineering improvement over your current static 4-gram hash. It achieves over 0.8 Mean Reciprocal Rank with sub-second runtimes on the full IMSLP database. The key improvement over your system: n-grams are constructed from relative intervals rather than absolute pitches, making them transposition-invariant by design.

**Fast Identification of Piece and Score Position via Symbolic Fingerprinting**
Dorfer, M., Goebl, W., & Widmer, G.
ISMIR 2014. Available via ResearchGate.

The foundational reference for symbolic fingerprinting in your domain. Worth citing explicitly to position your work as improving on a 12-year-old baseline.

**Online Symbolic Music Alignment with Offline Reinforcement Learning**
Peter, D., et al.
ISMIR 2024. arXiv: 2401.00466.

The RL+attention alignment approach is relevant here because early score following (the first 15-20 notes after identification) is actually a retrieval verification problem: you need to confirm the identified piece matches what the user is playing. The RL agent's attention-based position estimate can serve as a soft verification signal before committing to a score-following session.

### What Your Contribution Would Be

A two-stage identification system where:

Stage 1 (coarse retrieval, learned): A lightweight contrastive Transformer encoder trained on your ATEPP 5,091 performances with piece-identity positive pairs and transposition augmentation. This encoder produces a 128-dimensional embedding of the first N notes played. Nearest-neighbour retrieval against an embedding database (one embedding per piece, averaged over performances) returns top 20 candidates. This encoder is transposition-invariant by construction and robust to expressive deviation.

Stage 2 (exact reranking, deterministic): Relative-interval n-grams (not absolute pitch) computed from the user's first N notes matched against an interval-n-gram index for the top 20 candidates. This retains the interpretability and determinism of your current system while removing the transposition sensitivity.

The novelty claim: this is the first hybrid identification system for MIDI piano performance that combines learned transposition-invariant coarse retrieval with deterministic interval-relative reranking, evaluated on the ATEPP dataset with realistic expressive deviations.

### Files to Modify

| File | Nature of Change |
|---|---|
| `simple_ngram_fingerprinting.py` | Change fingerprint construction from absolute pitch to relative interval sequences; implement dynamic n-gram discriminativeness filter |
| `hybrid_piece_identifier.py` | Replace `StatisticalCoarseRetriever` with a `ContrastiveEmbeddingRetriever`; keep existing n-gram reranker but switch to interval-relative mode |
| `two_stage_server.py` | Wire the new retriever into the identification pipeline; adjust confidence thresholds for the new coarse stage |
| New file: `train_contrastive_identifier.py` | Training script for the contrastive encoder; piece-identity pairs from ATEPP metadata CSV |
| New file: `build_embedding_database.py` | Offline script to generate per-piece embeddings and save alongside the existing `.pkl` database |

---

## Contribution C: Score-Free Harmonic Context from Roman Numeral Analysis (MusicXML Fallback)

### The Gap

Your baseline audit notes two specific unknowns: (1) whether full Roman numeral labels can be derived reliably from your available MusicXML without extra tooling, and (2) whether the ATEPP performance-score alignments can support harmonic label transfer. Both of these are now resolvable with recent published tools.

The deeper issue: your current score-aware path derives tuning from key signature changes in the MusicXML file. This means a piece with one key signature (say, C major throughout) but rich chromatic modulations — Debussy's preludes are the extreme case in your dataset — will receive undifferentiated tuning for every note in the piece. Roman numeral labels resolve this: if the system knows the current chord is V/V (a secondary dominant), it can detune the third of that chord appropriately rather than tuning it to the tonic key.

Furthermore, when a MusicXML file is not available (which your audit flags as a restriction issue), a score-free Roman numeral analyser trained on the ATEPP corpus can substitute.

### Relevant Papers

**Roman Numeral Analysis with Graph Neural Networks: Onset-wise Predictions from Note-wise Features (ChordGNN)**
Karystinaios, E. & Widmer, G.
ISMIR 2023. arXiv: 2307.03544. Code available via author's GitHub.

ChordGNN operates on note-level graphs where nodes represent individual notes (features: pitch spelling, duration, metrical position) and edges encode temporal relationships (onset, during, follow, silence). A heterogeneous GraphSAGE convolution followed by an edge-contraction pooling layer produces onset-level representations, which are then passed through GRU layers and multitask MLP heads. The six jointly predicted tasks are: local key, Roman numeral degree, chord quality, inversion, root, and harmonic rhythm.

On the Beethoven Piano Sonatas dataset, ChordGNN achieves 51.8% Chord Symbol Recall (CSR) — approximately 11.6% above the AugmentedNet baseline. Critically, it predicts local key as one of its outputs, making it directly applicable to your existing key-detection pipeline while also providing the chord-function context your tuning engine currently lacks.

This is already cited in your thesis framing document, confirming it is on your radar. The gap is implementing the pipeline connection between ChordGNN's output and your JI ratio tables.

**AugmentedNet: A Roman Numeral Analysis Network with Synthetic Training Examples and Additional Tonal Tasks**
Nápoles López, N., et al.
ISMIR 2021. arXiv available via Semantic Scholar. Code: github.com/napulen/AugmentedNet.

AugmentedNet is the CRNN baseline that ChordGNN improves on. Its key practical advantage is that it trains on (MusicXML, RomanText) pairs and is available with pre-trained weights for direct inference. For your initial implementation, running AugmentedNet offline on your 319 MusicXML scores to generate per-note Roman numeral label JSON files is a viable first step — it extends your existing `extract_score_key_labels.py` pipeline to produce function-level labels, not just key-level labels.

A 2024 Springer paper (DOI: 10.1007/978-3-031-56992-0_10) has further adapted AugmentedNet to audio signals via chromagrams, which is relevant if you later want to handle the case where the user plays a piece not in your ATEPP corpus at all.

**Attend to Chords: Improving Harmonic Analysis of Symbolic Music Using Transformer-Based Models**
Chen, T. & Su, Y.
TISMIR, 2021. DOI: 10.5334/tismir.65.

The Harmony Transformer for functional harmony recognition. Uses a large vocabulary of 1,540 chords with joint chord segmentation via end-to-end sequence learning. Its multi-task formulation (chord recognition + chord change detection) is directly applicable to your need to identify when a harmonic context changes during a performance.

### What Your Contribution Would Be

A two-mode harmonic context pipeline:

**Mode 1 (MusicXML available):** Run AugmentedNet or ChordGNN offline over each of your 319 MusicXML scores during the database-building phase. Store note-level Roman numeral labels in extended JSON files alongside your existing key labels. At runtime, the score follower reads these labels and emits both the key-level and function-level context. The JI ratio selection in `tuning-core.js` uses the function label to resolve ambiguous intervals (e.g., a minor seventh in a dominant seventh chord gets a 7/4 or 16/9 ratio, not the default 9/5).

**Mode 2 (MusicXML unavailable or piece unidentified):** The score-free path uses your upgraded Transformer harmonic context model (from Contribution A) as the key estimator, and a lightweight version of ChordGNN (reduced to 2 graph conv layers) trained on the ATEPP labels as a secondary chord-function estimator. This second model is optional and should only be promoted once your function-label pilot audit demonstrates acceptable label quality — consistent with the gate condition already in your decision log.

The novelty claim: this is the first end-to-end pipeline connecting automatic Roman numeral analysis of piano scores to real-time adaptive JI tuning, with a graceful degradation path for unidentified pieces.

### Files to Modify

| File | Nature of Change |
|---|---|
| `extract_score_key_labels.py` | Extend to call AugmentedNet (or ChordGNN via partitura graph construction) and write Roman numeral fields into the existing score key label JSON format |
| `musicxml_score_parser.py` | Add a `parse_roman_numerals()` function that integrates with AugmentedNet output; handle the fallback case when labels are unavailable |
| `two_stage_server.py` | Emit function labels alongside key labels in the `ji_ratios` WebSocket message |
| `js/tuning-core.js` | Add a `calculateJIPitchBendWithFunction()` path that uses the Roman numeral label to select a more specific interval ratio |
| New file: `build_roman_numeral_labels.py` | Batch script to run AugmentedNet over all 319 MusicXML scores and save extended label JSONs |

---

## Infrastructure Refinement: Score Following — Parangonar → Matchmaker

### The Gap

Your score follower is implemented via Parangonar in `two_stage_server.py`. Parangonar is a correct and well-validated choice, but the field has moved. Two papers published since your last major codebase review are directly relevant.

### Relevant Papers

**Matchmaker: An Open-Source Library for Real-Time Piano Score Following and Systematic Evaluation**
Park, J., et al.
ISMIR 2025. arXiv: 2510.10087. PDF: carloscancinochacon.com/documents/peer_reviewed/ParkEtAl-ISMIR-2025.pdf.

Matchmaker is already cited in your thesis framing document. The key benchmark result: OLTWArzt (Online Line Time Warping, Arzt variant) achieves 92.8% total alignment rate at ≤2000 ms tolerance on the nASAP dataset, with a system latency of only 0.07 ms per frame. This is directly comparable to what you need. The library is Python-based, MIT-licensed, and compatible with Partitura — meaning it can replace Parangonar in `two_stage_server.py` with relatively low engineering cost.

The `LSE` (log-spectral energy) onset-sensitive feature outperforms chroma for both accuracy and latency, which is relevant if you later move toward audio input alongside MIDI.

**Online Symbolic Music Alignment with Offline Reinforcement Learning**
Peter, D. & Widmer, G.
ISMIR 2024. arXiv: 2401.00466.

The RL-based approach that outperforms state-of-the-art DTW-based methods in offline symbolic alignment. The agent uses an attention-based neural network to estimate the current score position from local score and performance contexts, treating the problem as a simplified offline RL problem. This approach handles expressive deviations (rubato, ornaments, wrong notes) better than DTW, and it operates on the same note-level symbolic representation your system already uses.

For your purposes, this paper suggests an upgrade path beyond Matchmaker: use Matchmaker's OLTWArzt as the primary real-time follower, and the RL-based alignment as a post-hoc correction step when the follower drifts significantly.

### Files to Modify

| File | Nature of Change |
|---|---|
| `two_stage_server.py` | Replace `parangonar` import with `matchmaker`; adapt the alignment callbacks to Matchmaker's `OnlineAlignment` API; retain Parangonar as a fallback if Matchmaker init fails |
| `requirements.txt` | Add `matchmaker` dependency; version-pin for reproducibility |

---

## MTS-MPE Refinements (Published Foundation, Minor Extensions)

Since you have already published on MTS-MPE, this section identifies only the refinements that are directly motivated by your new AI contributions above.

**Comma drift.** In extended chromatic passages, sequential 5-limit JI adjustments can accumulate syntonic comma drift (21.5 cents). Your current system does not detect or correct this. A simple correction is to track the cumulative deviation from 12TET and trigger a reset when it exceeds a threshold (e.g., ±35 cents from the nominal pitch class). This is a deterministic algorithm, not an AI contribution, but it is worth documenting as a system improvement in your MTS-MPE paper.

**7-limit ratios.** Your current `tuning-core.js` uses exclusively 5-limit ratios. For dominant seventh chords, the 7/4 ratio (969 cents, −31 cents from 12TET) produces a markedly purer seventh than the 5-limit 9/5 (1017 cents, +17 cents). Once your Roman numeral analysis pipeline can identify dominant seventh chords (Contribution C), enabling 7-limit ratios for those specific contexts is a natural extension. This does require the chord-function output from Contribution C to be available at runtime.

**MPE channel starvation.** Your LRU channel allocator in `tuning-mpe.js` allocates across channels 1–15. For dense polyphony (e.g., Liszt or Ravel), 15 channels can be exhausted. Adding a channel-stealing policy with priority based on note velocity and duration improves worst-case behaviour. This is an engineering fix rather than a research contribution, but it prevents degraded tuning during the evaluation pieces you care about most.

---

## Implementation Sequence and Timeline

The following sequence is designed to produce a submittable paper from each major contribution before the next one begins, which matches your thesis structure in `thesis-contribution-framing.md`.

### Phase 1 (Months 1–4): S-KEY-Symbolic Adaptation

1. Construct transposition pairs from ATEPP MIDI (automated, no manual work).
2. Implement the two-branch symbolic encoder (PCP branch + raw pitch branch) as an upgrade to `harmonic_context_model.py`.
3. Implement the self-supervised pre-training loop: CPSD-equivalent loss for symbolic (cross-correlation of pitch-class histograms across transposition) + auxiliary binary cross-entropy on major/minor pseudo-labels.
4. Fine-tune on your 319 score-key label JSONs. Compare against: (a) current ensemble baseline, (b) pure classical KK/Temperley/AS, (c) current GRU model.
5. Add Gedizlioğlu-style regularisation as post-processing.
6. Evaluate on a held-out test set with tonicization-heavy pieces (Schubert and Debussy subsets of your ATEPP dataset are ideal).
7. Submit as Paper 2.

### Phase 2 (Months 3–6, overlapping): Contrastive Piece Identification

1. Build the contrastive encoder training script for `train_contrastive_identifier.py`.
2. Train on ATEPP performance pairs (positive: two performances of the same composition; negative: different compositions; augmentation: random transposition ±6 semitones).
3. Replace the statistical coarse retriever in `hybrid_piece_identifier.py` with the learned embedding retriever.
4. Switch fingerprint construction from absolute pitch to relative intervals in `simple_ngram_fingerprinting.py`.
5. Evaluate: Mean Reciprocal Rank at k=1, 3, 10; identification speed in notes required; robustness to ±2 semitone transposition.
6. Submit as Paper 3.

### Phase 3 (Months 5–8): Roman Numeral Labels and Chord-Aware Tuning

1. Run the function-label pilot audit: apply AugmentedNet to 20 representative MusicXML scores; manually verify label quality against score.
2. If quality is acceptable (consistent with your decision-log gate condition), run `build_roman_numeral_labels.py` over all 319 scores.
3. Extend `extract_score_key_labels.py` to include function fields.
4. Update `two_stage_server.py` to emit function labels.
5. Update `tuning-core.js` to use function labels for 7-limit dominant seventh contexts.
6. Evaluate tuning improvement using perceptual roughness metrics (e.g., Sethares roughness model) on held-out pieces.

### Phase 4 (Months 7–9): Score Following Upgrade

1. Install and integrate Matchmaker alongside existing Parangonar.
2. Run A/B comparison on nASAP subset of your dataset: Parangonar DualDTW vs Matchmaker OLTWArzt.
3. Report alignment rate and latency.
4. If RL alignment (Peter & Widmer 2024) improves on drift recovery, implement it as a post-hoc correction layer.

---

## Evaluation Protocol Additions

The papers surveyed above use the following metrics consistently; your current `evaluate_harmonic_context_model.py` and `evaluation-protocol.md` should be extended to include them.

**MIREX Weighted Score.** Used by S-KEY, STONE, and OctaveNet. Scores each key prediction as: exact match = 1.0, fifth relation = 0.5, relative key = 0.3, parallel key = 0.2, all others = 0.0. More informative than accuracy alone for the major/minor confusion case. Add this to `evaluate_harmonic_context_model.py`.

**Chord Symbol Recall (CSR).** Used by ChordGNN and AugmentedNet. The proportion of chords where the predicted Roman numeral matches the annotation within a tolerance window. Required if you promote Contribution C to a full paper claim.

**Mean Reciprocal Rank (MRR).** Standard retrieval metric; used in the Piano Sheet Music Identification paper. Already implicit in your hybrid identifier smoke test but should be formalised.

**Alignment Rate (AR) at tolerance T.** Used by Matchmaker. Percentage of aligned notes with error ≤ T ms. Report at T = 500 ms and T = 2000 ms for comparison with the ISMIR 2025 benchmark.

---

## Codebase Gaps Not Addressed Here (Scope Boundaries)

**Browser-side model inference.** Your thesis framing document explicitly states that browser-side learned inference is not a necessary contribution. Running the GRU or Transformer backend in Python/PyTorch over WebSocket is sufficient. If you later want to port to ONNX Runtime Web, the architecture changes in Contribution A (smaller Transformer rather than larger GRU) make this more practical — ONNX exports of 2-layer Transformers under 5M parameters are well-supported in the browser environment.

**7-limit and 11-limit extensions.** Not a research contribution without the function-label pipeline (Contribution C) to trigger them correctly. Defer to Phase 3 above.

**Audio input (for non-MIDI instruments).** S-KEY and OctaveNet are audio-based, which is why they cannot be used directly. If you later want to support non-MIDI struck-string instruments via audio transcription, the Mobile-AMT paper (EUSIPCO 2024) and the online AMT work at `github.com/jdasam/online_amt` are the starting points.

---

## Reference List

### Core Methods (Key Detection, Self-Supervised Learning)

Kong, Y., Meseguer-Brocal, G., Lostanlen, V., Lagrange, M., & Hennequin, R. (2025). S-KEY: Self-supervised Learning of Major and Minor Keys from Audio. *ICASSP 2025*. arXiv:2501.12907.

Kong, Y., Meseguer-Brocal, G., Lagrange, M., & Hennequin, R. (2024). STONE: Self-supervised Tonality Estimator. *ISMIR 2024*. arXiv:2407.07408.

Kong, Y., Meseguer-Brocal, G., Lagrange, M., & Hennequin, R. (2025). Emergent Musical Properties of a Transformer Under Contrastive Self-Supervised Learning. *ISMIR 2025*. arXiv:2506.23873.

Ding, Y. & Weiß, C. (2024). Towards Robust Local Key Estimation with a Musically Inspired Neural Network. *EUSIPCO 2024*. IEEE DOI:10.1109/EUSIPCO60164.2024.10715249.

Gedizlioğlu, C. & Erol, K. (2024). A Regularization Algorithm for Local Key Detection. *Psychology of Music*. DOI:10.1177/10298649241245075.

### Symbolic Music Representation and Retrieval

Bradshaw, P., et al. (2025). Scaling Self-Supervised Representation Learning for Symbolic Piano Performance. *ISMIR 2025*, pp. 451-459. arXiv:2506.23869. (AriaEmb — 60k hours SimCLR on piano MIDI.)

Su, J., et al. (2025). MIDI-Zero: A MIDI-driven Self-Supervised Learning Approach for Music Retrieval. *ACM SIGIR 2025*, pp. 348-357. DOI:10.1145/3726302.3730034.

Wu, S., et al. (2025). CLaMP 3: Universal Music Information Retrieval Across Unaligned Modalities and Unseen Languages. *ACL 2025*. arXiv:2502.10362.

Wu, S., et al. (2023). CLaMP: Contrastive Language-Music Pre-training for Cross-Modal Symbolic Music Information Retrieval. *ISMIR 2023* (Best Student Paper Award). arXiv:2304.11029.

Wang, Y. & Su, Y. (2025). M2BERT: A ModernBERT for Symbolic Music Understanding. *ISMIR 2025*. arXiv:2507.04776.

Lee, S., et al. (2025). GigaMIDI: A Large-Scale MIDI Dataset for Music Audio Synthesis, Music Understanding, and Generation. *TISMIR 2025*. arXiv:2502.17726.

### Harmonic Analysis (Roman Numerals, Chord Recognition)

Karystinaios, E., et al. (2025). AnalysisGNN: Unified Music Analysis with Graph Neural Networks. *CMMR 2025*. arXiv:2509.06654.

Karystinaios, E. & Widmer, G. (2023). Roman Numeral Analysis with Graph Neural Networks: Onset-wise Predictions from Note-wise Features. *ISMIR 2023*. arXiv:2307.03544.

Sailor, M. (2024). RNBert: Fine-tuning MusicBERT for Roman Numeral Analysis. *ISMIR 2024*. HuggingFace port released Feb 2025.

Nápoles López, N., et al. (2021). AugmentedNet: A Roman Numeral Analysis Network with Synthetic Training Examples and Additional Tonal Tasks. *ISMIR 2021*. zenodo:5624533.

Chen, T. & Su, Y. (2021). Attend to Chords: Improving Harmonic Analysis of Symbolic Music Using Transformer-Based Models. *TISMIR*. DOI:10.5334/tismir.65.

Poltronieri, A., Serra, X., & Rocamora, M. (2025). From Discord to Harmony: Consonance-based Label Smoothing for Chord Estimation. *ISMIR 2025*. arXiv:2509.01588.

### Score Following and Real-Time Transcription

Park, J., et al. (2025). Matchmaker: An Open-Source Library for Real-Time Piano Score Following and Systematic Evaluation. *ISMIR 2025*. arXiv:2510.10087.

Peter, D. & Widmer, G. (2024). Online Symbolic Music Alignment with Offline Reinforcement Learning. *ISMIR 2024*. arXiv:2401.00466.

Peter, S., et al. (2025). Pairing Real-Time Piano Transcription with Symbol-level Tracking. *SMC 2025*. arXiv:2505.05078.

Hu, P., Peter, S., Schluter, J., & Widmer, G. (2025). Exploring System Adaptations for Minimum Latency Real-Time Piano Transcription. *ISMIR 2025*, pp. 83-90. arXiv:2509.07586.

### Tuning, Temperament, and Psychoacoustics

Volkov, D. (2023). Pivotuner: Real-Time Adaptive Pure Intonation VST3/AU Plugin. arXiv:2306.03873. (Direct competitor — reactive JI without harmonic function labels or score following.)

Van Kranenburg, P. & Bisschop, G. (2025). Keyboard Temperament Estimation from Symbolic Data: A Case Study on Bach's Well-Tempered Clavier. *ISMIR 2025*, pp. 503-510. (Inverse problem: estimating temperament from scores.)

Stange, K., et al. (2018). Playing Music in Just Intonation: A Dynamically Adaptive Tuning Scheme. *Computer Music Journal 42(3)*. arXiv:1706.04338.

Ramani, M. (2026). A Comprehensive Corpus of Biomechanically Constrained Piano Chords. arXiv:2603.29710. (19.3M chords with Plomp-Levelt roughness analysis.)

Sethares, W. (1993). Local Consonance and the Relationship Between Timbre and Scale. *JASA 94(3)*, pp. 1218-1228.

### Piece Identification

Baptista, C., et al. (2021). Piano Sheet Music Identification Using Dynamic N-gram Fingerprinting. *TISMIR*. DOI:10.5334/tismir.70.

### Dataset

Zhang, J., et al. (2022). ATEPP: A Dataset of Automatically Transcribed Expressive Piano Performance. *ISMIR 2022*. archives.ismir.net/ismir2022/paper/000053.pdf.

---

*Document status: draft for internal research planning. Last updated April 2026.*
