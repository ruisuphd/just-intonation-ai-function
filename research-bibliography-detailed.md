# Detailed Research Bibliography — Instant Harmonies AI Roadmap
### Algorithms, Architectures, and Technical Specifications from Source Papers

*Last updated: March 2026. All quotations are verbatim from the cited papers unless otherwise noted.*

---

## 1. Self-Supervised Key Estimation

### 1.1 STONE: Self-supervised Tonality Estimator

**Citation:** Kong, Y., Meseguer-Brocal, G., Lagrange, M., & Hennequin, R. (2024). STONE: Self-supervised Tonality Estimator. *Proceedings of the 25th International Society for Music Information Retrieval Conference (ISMIR 2024)*, San Francisco, USA. arXiv:2407.07408.

**Code:** https://github.com/deezer/stone (MIT licence)

**Core Architecture — ChromaNet:**
ChromaNet is a fully convolutional network with seven blocks, each containing a ConvNeXT block (maintains input resolution) and a time downsampling block (reduces temporal resolution while preserving the frequency dimension), followed by layer normalization.

Input: CQT matrix with 84 semitones (7 octaves × 12 bins/octave, center frequencies 27.5 Hz to 8.37 kHz). Output before octave collapsing: 84-dimensional vector.

**Octave Equivalence Operator *g*:**
The key architectural innovation. Rolls the log-frequency axis into a spiral making a full turn at every octave, summing coefficients across octaves for each pitch class *q*, followed by softmax normalization. This produces a 12-dimensional Key Signature Profile (KSP) vector:

```
y_θ[q] = exp(Σ_{j=0}^{J-1} f_θ(T_c x)[Q·j + q]) / Σ_{q'=0}^{Q-1} exp(Σ_{j=0}^{J-1} f_θ(T_c x)[Q·j + q'])
```

Where Q = 12 pitch classes, J = 7 octaves. All entries are non-negative and sum to one.

**Self-Supervised Pretext Task — CPSD Loss:**

Step 1: Artificial pitch transposition. Given CQT matrix **x** and integer c ≤ 15, trimming c lowest-frequency bins simulates c semitones of transposition: T_c **x**[p,t] = **x**[p-c,t].

Step 2: DFT of KSP. Compute ŷ_θ[ω] = Σ_{q=0}^{11} y_θ[q] · e^{-2πiωq/12}. For ω = 7 (circle of fifths), circular pitch shifts map to phase rotations.

Step 3: Cross-power spectral density. R̂[ω] = ŷ_A[ω] × ŷ_B*[ω].

Step 4: Distance metric. D_θ,k(**x**_A, **x**_B) = ½|e^{-2πiωk/Q} − R̂[ω]|².

Three loss components:
- L_AB (invariance): penalises distance between two transposed segments from the same key at k=0
- L_AA (equivariance): enforces pitch-shift equivariance within segment A
- L_BA (combined): links segments A and B with pitch shifts

Total: L_CPSD = L_AB + L_AA + L_BA.

**24-Key Extension (24-STONE):**
Last layer outputs two channels instead of one. Batch normalization applied per mode to prevent collapse. Output: 12×2 matrix Y_θ(**x**). λ_θ(**x**) = row sums (key signature, equivariant to transposition). μ_θ(**x**) = column sums (mode, invariant to transposition).

**Training:** 60,000 unlabeled songs, two 15-second disjoint excerpts per song. AdamW optimizer, LR 10⁻³, batch 128, 50 epochs, cosine schedule with linear warm-up.

**Calibration:** A single C major scale recording sets the absolute pitch reference via argmax lookup.

**Key Results (MIREX weighted score):**
- Semi-TONE (full GSMK supervision): 72.6%
- Supervised SOTA: 73.1%
- Semi-TONE matches Sup-TONE with 10% of labels

**Limitation:** Cannot distinguish relative keys (e.g. C major vs A minor) without supervision.

---

### 1.2 S-KEY: Self-supervised Learning of Major and Minor Keys from Audio

**Citation:** Kong, Y., Meseguer-Brocal, G., Lostanlen, V., Lagrange, M., & Hennequin, R. (2025). S-KEY: Self-supervised Learning of Major and Minor Keys from Audio. *Proceedings of IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP 2025)*. arXiv:2501.12907.

**Code:** https://github.com/deezer/s-key (MIT licence)

**Architecture:**
Builds on ChromaNet (STONE). 2-D fully convolutional network f_θ operating on CQT with M=2 output channels and no pooling over frequency dimension. Average pooling on time dimension + batch normalization. 84 frequency bins (Q×J = 12×7) pooled to 24 outputs (Q×M = 12×2).

**The Major/Minor Disambiguation — Pseudo-Label Generation (Equation 5):**
```
ν(θ|x,c) = [1,0]  if u_maj(θ|x,c) > u_min(θ|x,c)
            [0,1]  otherwise
```
Where:
- u_maj = u(T_c x)[q_max(θ|x)] — chroma energy at the root of the predicted major key
- u_min = u(T_c x)[(q_max(θ|x) − 3) mod Q] — chroma energy at the relative minor root (3 semitones below)
- u(·) is transposition-invariant chroma energy

This rule assigns a "major" pseudo-label when the pitch class at the major-key root has higher chroma energy than the relative-minor root, without requiring any human annotation.

**Auxiliary Loss (Equation 6):**
```
L_S-KEY(θ|x,c,k) = BCE(ν(θ|x,c), μ_θ,A,c) + BCE(ν(θ|x,c), μ_θ,B,c) + BCE(ν(θ|x,c), μ_θ,A,c+k)
```

**Batch Regularisation (Equation 7):**
Penalises deviation from 50% major/minor split across the mini-batch.

**Combined Objective (Equation 8):**
Total loss = L_CPSD + λ_BCE · L_S-KEY + λ_avg · L_avg.
Weights: λ_BCE = 1.5, λ_avg = 15. (The CPSD loss has an implicit weight of 1.0. The paper names the auxiliary loss weight λ_BCE, not λ_S-KEY.)

**Training:**
- 60k corpus: batch 128, 50 epochs, AdamW LR 10⁻³, cosine schedule
- 1M corpus: batch 256, 100 epochs, same optimizer
- Transposition c sampled uniformly from [0, 15] semitones
- Interval k sampled uniformly from [−12, 12] semitones

**Key Results (1M training, MIREX weighted score):**
| Dataset | S-KEY | madmom (supervised SOTA) |
|---------|-------|--------------------------|
| FMAKv2 | 73.2% | 73.1% |
| GTZAN | 74.4% | 67.9% |
| GiantSteps | 72.1% | 71.0% |
| Schubert Winterreise (SWD) | 90.4% | 87.7% |

**Critical Limitation for This Thesis:** S-KEY operates exclusively on audio (CQT spectrograms), not symbolic MIDI. Direct deployment in a WebMIDI pipeline is not possible. The thesis contribution would be adapting the self-supervised framework to symbolic pitch-class sequences.

---

## 2. Local Key Estimation

### 2.1 OctaveNet: Towards Robust Local Key Estimation with a Musically Inspired Neural Network

**Citation:** Ding, Y. & Weiß, C. (2024). Towards Robust Local Key Estimation with a Musically Inspired Neural Network. *Proceedings of the 32nd European Signal Processing Conference (EUSIPCO 2024)*, Lyon, France. IEEE DOI:10.1109/EUSIPCO60164.2024.10715249.

**Architecture:**
OctaveNet rearranges the CQT/HCQT spectrogram in two different ways, creating two branches:
- Branch 1: Octave-folded (pitch-class) representation — collapses octave information, emphasising pitch-class distribution
- Branch 2: Sequential representation — preserves octave register information

Each branch is processed with convolutional layers followed by recurrent layers (LSTM or GRU). The two feature maps are fused before the final key prediction layer.

**Key Design Principle:** The two-branch design mirrors how human music perception integrates pitch-class identity (chroma) with register information (octave). This is directly translatable to symbolic input where pitch class and MIDI note number are separate features.

**Results:** OctaveNet achieves substantially better generalisation to unseen songs than prior single-branch models, despite having fewer parameters. The paper specifically evaluates *local* key estimation (per-segment, not per-song).

**Relevance to Thesis:** The two-branch symbolic adaptation is: Branch 1 = 12-bin pitch-class histogram over a sliding window (analogous to octave-folded CQT). Branch 2 = raw MIDI pitch sequence retaining octave information (analogous to sequential CQT). This directly maps onto a modification of the existing `HarmonicContextGRU` where the single 80-D input is replaced with two parallel encoders.

---

### 2.2 Regularisation Algorithm for Local Key Detection

**Citation:** Gedizlioğlu, Ç. & Erol, K. (2024). A Regularization Algorithm for Local Key Detection. *Psychology of Music*. DOI:10.1177/10298649241245075.

**Method:**
Models local key detection as a segmentation-and-optimisation problem on symbolic MIDI input.

Step 1: Divide the piece into overlapping windows of fixed duration.
Step 2: For each window, compute the Krumhansl-Schmuckler correlation score against all 24 key profiles (using a modified Krumhansl-Kessler key profile).
Step 3: Solve an optimisation problem that jointly selects:
- the key assignment per segment
- the number and placement of key boundaries

Step 4: Apply a regularisation term that penalises superfluous modulations. Short key segments below a minimum duration threshold are absorbed into their neighbours.

**The Regularisation Formulation:**
The objective minimises:
```
F(S) = Σ_i cost(segment_i, key_i) + λ · |boundaries|
```
Where λ controls the penalty for each additional key boundary. Higher λ → fewer boundaries → only genuine modulations survive. Lower λ → more key changes detected → tonicizations treated as modulations.

**Key Insight:** Tonicized chords (e.g. V/V in C major, which briefly emphasises D major) alter the perception of key for a few measures without constituting a true modulation. The regularisation explicitly distinguishes these from genuine modulations by requiring a minimum duration for a key segment to be accepted.

**Input:** Symbolic MIDI. No audio required. Directly applicable to the WebMIDI pipeline.

**Relevance to Thesis:** This is a post-processing step applicable to any key prediction sequence. It can be applied after the GRU/Transformer model outputs per-note key predictions, suppressing flickering between closely related keys. Implementation requires only a sweep over the prediction sequence with no additional model training.

---

## 3. Roman Numeral Analysis and Harmonic Function

### 3.1 ChordGNN: Roman Numeral Analysis with Graph Neural Networks

**Citation:** Karystinaios, E. & Widmer, G. (2023). Roman Numeral Analysis with Graph Neural Networks: Onset-wise Predictions from Note-wise Features. *Proceedings of the 24th International Society for Music Information Retrieval Conference (ISMIR 2023)*. arXiv:2307.03544.

**Code:** https://github.com/manoskary/chordgnn

**Graph Construction:**
Scores are represented as attributed graphs G = (V, E, X):
- **Nodes**: individual notes with features: pitch spelling, note duration, metrical position
- **Four edge types**:
  - *onset*: notes starting simultaneously (on(u) = on(v))
  - *during*: note u starts while v is sounding (on(u) > on(v) ∧ on(u) ≤ on(v) + dur(v))
  - *follow*: note u ends exactly when v starts
  - *silence*: temporal gap between note endings and next note start

**Heterogeneous GraphSAGE Convolution (per layer):**
1. Neighbour aggregation: mean pooling of neighbour embeddings per relation type r
2. Relation-specific update: concatenate node embedding with aggregated neighbours, pass through learned weight matrix W and ReLU: h_v^(l+1) = (1/|ℛ|) Σ_r σ(W · concat(h_v^l, mean_neighbours))
3. Multi-relation fusion: average across all relation types

**Edge Contraction Pooling (novel contribution):**
Converts note-level representations to onset-level:
1. Apply learned transformation: H' = H · W^(cpool)
2. Sum representations for all notes sharing an onset: h_u^(cp) = h_u + Σ_{v ∈ N_On(v)} h_v
3. Filter to keep one node per unique onset time
4. Sort resulting sequence by onset time

**Sequential Processing:**
After edge contraction, onset sequence passes through an MLP layer and 2 GRU layers for shared representation, followed by task-specific MLP heads.

**Six Jointly Predicted Tasks:**
1. Local key (categorical)
2. Primary degree (scale degree of chord root)
3. Secondary degree (tonicization target)
4. Quality (major/minor/seventh)
5. Inversion (root position, 1st, 2nd)
6. Root (absolute pitch class)

**Dynamic Task Weighting:**
```
L_tot = Σ_{t ∈ T} [L_t · 1/(2·γ_t²) + log(1 + γ_t²)]
```
Scalar weights γ_t are learned during training.

**Training:** 300 training pieces, 56 test pieces. Hidden size 256, dropout 0.5. AdamW optimizer, LR 0.0015, weight decay 0.005.

**Results (Beethoven Piano Sonatas test set):**
| Task | Accuracy |
|------|----------|
| Local Key | 82.0% |
| Degree | 71.5% |
| Quality | 74.1% |
| Inversion | 76.5% |
| Root | 82.5% |
| Roman Numeral CSR | 51.8% (full test set, with post-processing) |

Beethoven Piano Sonatas subset: 49.1% CSR without post-processing. Full test set with post-processing: 51.8% CSR — approximately 11.6 percentage points above AugmentedNet.

**Input Format:** Accepts MusicXML. CLI: `python analyse_score.py --score_path <path>`. Output: annotated MusicXML with Roman numeral labels as harmony annotations.

---

### 3.2 AugmentedNet: Roman Numeral Analysis CRNN

**Citation:** Nápoles López, N., Gotham, M., & Fujinaga, I. (2021). AugmentedNet: A Roman Numeral Analysis Network with Synthetic Training Examples and Additional Tonal Tasks. *Proceedings of the 22nd International Society for Music Information Retrieval Conference (ISMIR 2021)*. zenodo:5624533.

**Code:** https://github.com/napulen/AugmentedNet

**Architecture:**
CRNN with two independent convolutional blocks:
- Block 1: processes spelled bass note input
- Block 2: processes spelled chroma features

Each convolutional block has 6 × 1D convolutional layers. Each layer doubles the convolution window length and halves the number of output filters. After convolution: two bidirectional GRU layers returning outputs at every timestep.

**Multitask Learning (11 tasks in AugmentedNet 11+):**
Includes key, degree, quality, inversion, root, plus additional tonal tasks (secondary degree, mode, etc.).

**Synthetic Training Examples:**
New scores are artificially generated from chord annotations and texturised with simple patterns (e.g. Alberti bass). These complement key transposition augmentation.

**Input:** MusicXML files (paired with RomanText annotations for training).

**Inference:**
```
python -m AugmentedNet.inference AugmentedNetv.hdf5 <input_file>.musicxml
```
Outputs: annotated MusicXML and CSV with timestep-by-timestep predictions.

**Pre-trained Model:** Available in repository (AugmentedNet.hdf5, v1.9.1).

**Dependencies:** Python 3, TensorFlow 2.5+.

---

## 4. Contrastive Symbolic Music Retrieval

### 4.1 CLaMP: Contrastive Language-Music Pre-training

**Citation:** Wu, S., Fang, X., Chang, Y., Yu, M., & Taylor, G.W. (2023). CLaMP: Contrastive Language-Music Pre-training for Cross-Modal Symbolic Music Information Retrieval. *Proceedings of the 24th International Society for Music Information Retrieval Conference (ISMIR 2023)* (Best Student Paper Award). arXiv:2304.11029.

**Code:** https://github.com/microsoft/muzic/tree/main/clamp

**Music Encoder — Bar Patching:**
Music in ABC notation is divided into bar-level patches. Each bar becomes a single token/patch, reducing sequence length to less than 10% of the character-level representation. This is critical for handling long pieces within the Transformer's context window.

**Masked Music Model (M3) Pre-training:**
45% of patches are randomly selected and processed: 80% masked, 10% shuffled, 10% unchanged. A decoder reconstructs original patches from noisy input via cross-entropy loss. This teaches the encoder to understand musical context and structure.

**Contrastive Loss:**
InfoNCE: for a batch of N (music, text) pairs, the model maximises cosine similarity of matching pairs while minimising similarity of non-matching pairs. Standard symmetric contrastive formulation.

**Text Dropout:** During training, text descriptions are randomly dropped with some probability, forcing the music encoder to develop robust standalone representations.

**Training Data:** 1.4M music-text pairs.

**Key Results:**
- WikiMT zero-shot classification outperforms fine-tuned baselines on several tasks
- The music encoder alone (without text) produces useful embeddings for retrieval

---

### 4.2 CLaMP 2: Multimodal Music Information Retrieval Across 101 Languages

**Citation:** Wu, S., et al. (2024). CLaMP 2: Multimodal Music Information Retrieval Across 101 Languages Using Large Language Models. *Findings of NAACL 2025*. arXiv:2410.13267.

**MIDI Text Format (MTF):**
CLaMP 2 introduces a lossless textual representation of MIDI. Raw MIDI messages are read using the mido library and converted to MTF, where each message becomes a patch. This preserves all timing and dynamics without quantisation errors.

**Architecture:**
- Patch-level encoder: 12 layers, 768 hidden size
- Character-level decoder: 3 layers, 768 hidden size
- Maximum input: 32,768 characters (512 patches × 64 characters per patch)

**Training Data:** 1.5M ABC-MIDI-text triplets.

**Key Results:**
- Pianist8 classification: 89.16% accuracy (MIDI input)
- WikiMT MRR: 0.3438

**Relevance to Thesis:** The contrastive encoder concept (music → embedding → retrieval) is directly applicable even without the text modality. You can train a music-only contrastive encoder where positive pairs are two performances of the same composition from your ATEPP dataset.

---

## 5. Score Following and Alignment

### 5.1 Matchmaker: Real-Time Piano Score Following

**Citation:** Park, J., et al. (2025). Matchmaker: An Open-Source Library for Real-Time Piano Score Following and Systematic Evaluation. *Proceedings of the 26th International Society for Music Information Retrieval Conference (ISMIR 2025)*. arXiv:2510.10087.

**OLTWArzt Algorithm:**
Based on Arzt & Widmer's tempo-aware Online Time Warping. Implements a backward-forward strategy. Implemented in Cython for sub-millisecond inference. Corrects early misalignments through bidirectional processing.

**Feature Comparison (all paired with OLTWArzt):**

*Note: MAE values vary by dataset. The values below are representative from the (n)ASAP benchmark. Consult the paper's full tables for per-dataset breakdowns.*

| Feature | MAE (ms) approx. | Extraction Latency (ms) |
|---------|-------------------|------------------------|
| LSE (Log-Spectral Energy) | ~91–153 (varies by dataset) | 0.91 |
| Chroma | higher than LSE | 3.05 |
| CQT | higher than Chroma | 42.58 |
| MFCC | highest | 2.58 |

*The exact MAE figures depend on which dataset partition is used (Vienna4x22, Batik, (n)ASAP). LSE consistently outperforms other features. The original values I listed (241.85 etc.) could not be confirmed against the paper and have been removed pending re-verification against the source tables.*

**Alignment Method Latency:**
| Method | Latency per step |
|--------|-----------------|
| OLTWArzt | 0.07 ms |
| OLTWDixon | 1.22 ms |
| HMM | 3.59 ms |

**Benchmark Results (nASAP, 59 performances):**
| Method | AR @50ms | AR @100ms | AR @500ms | AR @2000ms | Total AR |
|--------|---------|----------|----------|-----------|----------|
| OLTWArzt | 44.1% | 58.3% | 84.8% | 95.1% | 92.8% |
| OLTWDixon | 40.3% | 58.5% | 82.5% | 92.0% | 89.4% |
| HMM | — | — | — | — | 43.8% |

**Partitura Integration:** Takes any symbolic music format available via Partitura (MusicXML, MIDI, MEI, etc.).

**API:**
```python
from matchmaker import Matchmaker
mm = Matchmaker(score_file="path/to/score.musicxml", input_type="audio")
for current_position in mm.run():
    print(current_position)
```

---

### 5.2 Online Symbolic Music Alignment with Offline Reinforcement Learning

**Citation:** Peter, D. & Widmer, G. (2024). Online Symbolic Music Alignment with Offline Reinforcement Learning. *Proceedings of the 25th International Society for Music Information Retrieval Conference (ISMIR 2024)*. arXiv:2401.00466.

**State Representation:**
- Score context: window of 16 pitch sets centred on last predicted score position (7 past, 8 future onsets)
- Performance context: 8 most recent notes in performance pitch sequence

**Action Space:**
16 possible actions, one for each score onset in the context window. Agent selects the most likely score onset matching the current performance note.

**Reward:** Binary — 1 if correct alignment, 0 otherwise. No discount factor (γ = 0).

**Neural Architecture:**
Attention-based Transformer: 8 heads, 6 layers, layer normalization. 157,250 total parameters. Input: 88 piano pitches + special tokens in 64-D embeddings. Pitch set embeddings created by summing individual pitch embeddings (max 7 pitches per onset).

**Training:**
Offline RL treating alignment as supervised learning. Binary cross-entropy loss. Batch size 8192, 50 epochs, ADAM with LR warm-up + sqrt decay. Augmentation: random pitch shifting (±1 octave).

**Score Following Results:**
- Median asynchrony: 15.7 ms
- 91.4% within ±25 ms
- 93.8% within ±50 ms
- 96.6% within ±100 ms
- Outperforms OLTW baseline (60.6 ms median)

**Inference Speed:** ~10 ms per note on Beethoven Op. 53 Mvt 3 (7,273 notes).

---

## 6. Symbolic Music Fingerprinting

### 6.1 Dynamic N-gram Fingerprinting for Piano Sheet Music

**Citation:** Baptista, C., et al. (2021). Piano Sheet Music Identification Using Dynamic N-gram Fingerprinting. *Transactions of the International Society for Music Information Retrieval (TISMIR)*. DOI:10.5334/tismir.70.

**Key Innovation over Static N-grams:**
Dynamic n-gram hashing checks fingerprint discriminativeness at construction time. Only sufficiently distinctive n-grams are stored, eliminating common patterns that would match many pieces.

**Interval-Based Construction:**
N-grams are constructed from relative intervals rather than absolute pitches, making them transposition-invariant by design. This directly addresses the transposition sensitivity of the current `SimpleNGramFingerprinter`.

**Results:** Over 0.8 Mean Reciprocal Rank with sub-second runtimes on the IMSLP database.

---

## 7. Piano Performance Datasets

### 7.1 ATEPP: A Dataset of Automatically Transcribed Expressive Piano Performance

**Citation:** Zhang, J., et al. (2022). ATEPP: A Dataset of Automatically Transcribed Expressive Piano Performance. *Proceedings of the 23rd International Society for Music Information Retrieval Conference (ISMIR 2022)*. archives.ismir.net/ismir2022/paper/000053.pdf.

**Dataset:** 11,742 expressive piano performances by 49 virtuoso pianists, 1000 hours. Transcribed by a neural piano transcription model trained jointly with pedals and keys.

**Current Project Usage:** Distilled to 5,091 performances across 319 unique compositions (43.6% of full ATEPP), filtered to pieces with MusicXML score coverage.

---

## 8. Adaptive Just Intonation

### 8.1 Playing Music in Just Intonation: A Dynamically Adaptive Tuning Scheme

**Citation:** Stange, K., Wick, C., & Hinrichsen, H. (2018). Playing Music in Just Intonation: A Dynamically Adaptive Tuning Scheme. *Computer Music Journal*, 42(3), 47–62. MIT Press. DOI:10.1162/comj_a_00478. arXiv:1706.04338.

**Method:** Solves a system of linear equations at each timestep to determine optimal tuning for each sounding note, given the constraint that all simultaneous intervals should be as close as possible to just intonation ratios. When not all intervals can be pure simultaneously (e.g. in diminished chords), the system produces a tempered compromise automatically.

**Relevance:** This is the primary prior art for adaptive JI. The thesis differs by focusing on the harmonic-context estimation problem (knowing *which* key/chord context to tune to) rather than the tuning-optimisation problem itself (computing optimal cent offsets given a known context).

---

---

## Verification Log (March 2026)

The following claims were cross-checked against the original papers via arXiv HTML versions:

**Confirmed:** S-KEY MIREX weighted scores (73.2/74.4/72.1/90.4%), S-KEY training configuration (60k/128/50ep and 1M/256/100ep), STONE training config (AdamW/1e-3/128/50/cosine), ChordGNN metrics (Local Key 82.0%, CSR 51.8%, hidden 256, dropout 0.5, LR 0.0015), Peter & Widmer RL agent (157,250 params, 15.7ms median, 8 heads, 6 layers), Matchmaker OLTWArzt (0.07ms/step, 92.8% AR), CLaMP Best Student Paper, CLaMP 1.4M pairs, CLaMP 2 1.5M triplets, CLaMP 2 Pianist8 89.16%, CLaMP 2 WikiMT MRR 0.3438, ATEPP 11,742 performances, Stange et al. CMJ 42(3) 47-62.

**Corrected:** S-KEY loss weight naming (λ_BCE not λ_S-KEY, value 1.5 is correct). Matchmaker LSE MAE values removed (original 241.85ms could not be confirmed; paper reports dataset-dependent values in the 91-153ms range). ChordGNN CSR table clarified (49.1% is BPS without post-processing; 51.8% is full test set with post-processing).

**Not independently confirmed (insufficient detail in accessible text):** S-KEY pseudo-label rule's exact formulation (described based on the paper's Equation 5 but the full derivation was not accessible in fetched HTML). CLaMP 2 specific architecture parameters (12 layers, 768 hidden). Baptista et al. interval-relative n-gram claim (dynamic filtering confirmed, but relative vs. absolute pitch representation could not be independently verified from accessible sources — verify against full PDF).

*Document status: research reference for internal use. Not for publication.*
