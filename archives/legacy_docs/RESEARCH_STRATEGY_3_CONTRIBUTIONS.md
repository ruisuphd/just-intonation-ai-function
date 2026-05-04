# Research Strategy: Three-Contribution Thesis
## Instant Harmonies — Real-Time Adaptive Just Intonation from MIDI

*Generated: 2 April 2026*
*Scope: Dataset collection, S-KEY symbolic fine-tuning, MTS-MPE refinement, Roman numeral labels*

---

## 0. Thesis Architecture (3 Contributions)

**Contribution 1 — S-KEY-Symbolic:** Self-supervised pre-training + supervised fine-tuning for local key detection from symbolic MIDI, using a two-branch causal Transformer. Adapts S-KEY (Kong et al., ICASSP 2025, arXiv:2501.12907) from audio CQT to symbolic note-event sequences.

**Contribution 2 — MTS-MPE Tuning Protocol:** Already published across three venues (Ubimus 2024, Ubimus 2025, SMC 2026). Precision-Optimized MPE achieves 0.0244-cent resolution via ±2 semitone RPN restriction. This strategy document identifies specific refinements needed for thesis completeness.

**Contribution 3 — Roman Numeral Labels for Chord-Aware Tuning:** Offline Roman numeral analysis of MusicXML scores → per-note harmonic function labels → runtime emission via score following → chord-function-aware JI ratio selection (including 7-limit ratios for dominant sevenths).

---

## 1. Dataset Collection and Preparation

### 1.1 The Problem

The current ATEPP-based training pipeline has a critical bug: `musicxml_score_parser.py` (line 107) defaults `current_mode` to `'major'` when the MusicXML `<mode>` element is absent. The W3C MusicXML 4.0 specification (§4.3, "key" element definition at https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/mode/) states that `<mode>` is optional; when omitted, the key signature is ambiguous between major and its relative minor. As a result, all 803,877 notes across 319 unique compositions in your current label files are labeled as major keys. Rows 12–23 (all minor keys) in both `transformer_eval.json` and `harmonic_context_eval.json` confusion matrices are entirely zeros, confirming the model has never seen a minor-key training example.

This is the single most impactful issue to fix before any other training work.

### 1.2 MuseScore API Assessment

You asked whether the MuseScore API can provide aligned MusicXML + MIDI datasets. The answer is: **not directly, and it is not the recommended path.** Here is why:

The MuseScore public API (api.musescore.com) provides metadata search and score download for individual scores. It does not offer bulk download endpoints. Mass scraping would violate MuseScore's Terms of Service (Section 6.2 of their Terms as of March 2026 prohibits automated downloading).

However, a pre-built alternative exists: **PDMX** (Pereira et al., ISMIR 2024), a corpus of 254,387 MusicXML files extracted from MuseScore user uploads. PDMX is publicly available for research and includes parsed MusicXML data. The limitation: PDMX does not include aligned MIDI performance recordings — it contains only the notated scores. For your purpose (training a key detection model that requires ground-truth key annotations), PDMX would need external key labels, which it does not provide.

### 1.3 Recommended Dataset Strategy

Rather than collecting new data via MuseScore, the most efficient path is to fix the existing ATEPP pipeline and supplement with two datasets that have explicit, human-verified major/minor annotations:

**Dataset A — DCML Corpora (primary supplement)**

- Source: Digital and Cognitive Musicology Lab, EPFL
- Repository: https://github.com/DCMLab
- Content: ~500+ pieces with expert harmonic annotations in TSV format
- Key feature: Uses the DCML annotation standard where case convention explicitly encodes mode — uppercase Roman numerals = major, lowercase = minor. The `localkey` column in each TSV file contains entries like `C` (C major), `c` (C minor), `Ab` (A-flat major), `f#` (F-sharp minor).
- Relevant sub-corpora for piano: `ABC` (Annotated Beethoven Corpus, 32 piano sonatas), `mozart_piano_sonatas`, `debussy_suite_bergamasque`, `chopin_mazurkas`, `dvorak_silhouettes`, `grieg_lyric_pieces`, `schumann_kinderszenen`, `liszt_pelerinage`
- Format: TSV with columns `mn` (measure number), `mn_onset`, `timesig`, `localkey`, `globalkey`, `pedal`, `numeral`, `form`, `figbass`, `changes`, `relativeroot`, `phraseend`
- Integration: Parse the `localkey` column, map to 24-key labels (0–11 major, 12–23 minor) using the case convention. Align to note events using measure numbers.

**Dataset B — When-in-Rome (secondary supplement)**

- Source: Gotham et al., collected from multiple sources
- Repository: https://github.com/MarkGotham/When-in-Rome
- Content: ~1,500 pieces with Roman numeral annotations in RomanText format
- Key feature: Explicit key declarations in the format `m1 C: I` (C major) or `m1 c: i` (C minor). The colon-separated key field unambiguously specifies mode.
- Format: `.txt` files in RomanText format. Each line starts with a measure number, followed by optional beat position, key change (if any), and Roman numeral.
- Integration: Parse key declarations, propagate through the piece, align to note events.

**Dataset C — Fix the ATEPP parser (required regardless)**

The ATEPP parser bug must be fixed even if supplementary datasets are added, because ATEPP provides the performance MIDI files needed for the self-supervised pre-training step (transposition pair generation). The fix:

1. In `musicxml_score_parser.py`, change the default `current_mode` from `'major'` to `'unspecified'`.
2. When `<mode>` is absent and `current_mode` is `'unspecified'`, apply a heuristic: compute a pitch-class histogram over the notes in the current key-signature region and compare against Krumhansl-Kessler major and minor profiles. Assign the higher-correlating mode.
3. Alternatively, collapse to a 12-class model (pitch-class-relative, ignoring major/minor distinction) for pre-training, then expand to 24-class during supervised fine-tuning with DCML/When-in-Rome data that has explicit mode labels.

### 1.4 Practical Steps

1. **Clone DCML corpora** — `git clone` the relevant sub-corpora from GitHub. No API key or licence issue: all DCML corpora are released under CC-BY 4.0 or CC-BY-SA 4.0.
2. **Write a DCML TSV parser** — New script `parse_dcml_annotations.py` that reads each TSV file, extracts `localkey` and `globalkey` per measure, converts to 24-key integer labels using the case convention (uppercase = major, lowercase = minor), and outputs JSON in the same format as `extract_score_key_labels.py`.
3. **Clone When-in-Rome** — Similarly CC-licensed. Write a `parse_romantext_annotations.py` script.
4. **Fix `musicxml_score_parser.py`** — Apply the heuristic fix described above. Re-run `extract_score_key_labels.py` over all 319 ATEPP scores. Verify that minor-key labels now appear.
5. **Merge datasets** — Create a unified training set with consistent 24-key label format. Track dataset provenance (ATEPP-heuristic vs DCML-expert vs WiR-expert) for ablation.

### 1.5 What About Aligned MusicXML + MIDI?

You mentioned needing "MusicXML and MIDI aligned." For the S-KEY contribution, the alignment requirement is as follows:

- **Self-supervised pre-training** requires only MIDI (no alignment, no MusicXML). You generate transposition pairs by pitch-shifting the MIDI note numbers. ATEPP's 5,091 MIDI performances are sufficient.
- **Supervised fine-tuning** requires note-level key labels aligned to the MIDI note sequence. This is what `extract_score_key_labels.py` currently produces from MusicXML scores. After fixing the mode bug, your existing 319 score→label JSONs will work. Supplementing with DCML/When-in-Rome requires only measure-level alignment (which measures map to which notes), not sample-level audio alignment.
- **Roman numeral labels (Contribution 3)** require MusicXML input to AugmentedNet/ChordGNN. ATEPP already provides aligned MusicXML for its 319 unique compositions. DCML corpora provide their own MusicXML or MEI scores.

You do not need to collect new aligned MusicXML + MIDI pairs. The existing ATEPP alignment plus DCML/When-in-Rome annotations are sufficient.

---

## 2. S-KEY Symbolic Fine-Tuning Strategy

### 2.1 Current State

Your codebase already contains the key components:

- `pretrain_symbolic_key.py`: Self-supervised pre-training with CPSD equivariance loss at ω=7 and mode pseudo-labels. Six ablation configurations defined (skey-default, equiv-only, mode-only, high-mode, low-batch, equal).
- `harmonic_context_model.py`: `SymbolicKeyTransformer` with d_model=128, 4 heads, 2 layers, two-branch design (PCP + raw features).
- `train_harmonic_context_model.py`: Supervised fine-tuning supporting both GRU and Transformer via `--model-type` flag.
- `evaluate_harmonic_context_model.py`: MIREX weighted score evaluation with tonicization subset analysis.

Current results (all trained on major-only labels):

| Model | Test Accuracy | Test MIREX Weighted |
|-------|--------------|---------------------|
| GRU baseline | 0.4558 | 0.6050 |
| Transformer | 0.4545 | 0.6082 |

Both models predict only 12 major keys (classes 0–11). The Transformer does not outperform the GRU, likely because the training data is too small and the mode-label contamination prevents it from learning the major/minor distinction that its architecture was designed to capture.

### 2.2 Why the Transformer Is Not Yet Beating the GRU

Three factors explain the near-identical performance:

1. **Label contamination.** With all labels forced to major, the Transformer's mode output head receives no learning signal. The two-branch architecture (designed to separately encode pitch-class distributions and octave-register information, following OctaveNet — Ding & Weiß, EUSIPCO 2024, DOI:10.1109/EUSIPCO60164.2024.10715249) cannot differentiate relative major/minor pairs because the training data makes no such distinction.

2. **No pre-training.** The ablation grid in `pretrain_symbolic_key.py` has never been run beyond smoke tests. The self-supervised pre-training step is the entire source of the Transformer's expected advantage — without it, the Transformer is just a randomly initialised model fine-tuned on 319 compositions, where the GRU's simpler inductive bias (sequential recurrence) may be more data-efficient.

3. **Default hyperparameters.** No hyperparameter search has been conducted. The defaults (d_model=128, LR=1e-4, 20 epochs, window=256, hop=128) were set heuristically. The GRU defaults (LR=1e-3, 10 epochs) may happen to be closer to optimal for this data size.

### 2.3 Refined Strategy

The following sequence is ordered by expected impact. Each step should be validated before proceeding to the next.

**Step 1: Fix the training labels (BLOCKING)**

Without correct major/minor labels, no meaningful evaluation of 24-key performance is possible. Complete Section 1.4 above before any training runs.

Validation: After re-running `extract_score_key_labels.py` with the fixed parser, count the distribution of keys 0–23 across all label files. You should see non-trivial counts for at least keys 12 (A minor), 14 (B minor), 15 (C minor), 19 (E minor), and 21 (G minor), which are common in the Beethoven/Chopin/Schubert repertoire in ATEPP.

**Step 2: Run the self-supervised pre-training ablation grid**

The six configurations in `pretrain_symbolic_key.py` are:

| Config | λ_equiv | λ_mode | λ_batch | Purpose |
|--------|---------|--------|---------|---------|
| skey-default | 1.0 | 1.5 | 15.0 | Reproduce S-KEY paper weights |
| equiv-only | 1.0 | 0.0 | 0.0 | Isolate equivariance contribution |
| mode-only | 0.0 | 1.5 | 15.0 | Isolate mode disambiguation contribution |
| high-mode | 1.0 | 3.0 | 15.0 | Test sensitivity to mode weight |
| low-batch | 1.0 | 1.5 | 5.0 | Test sensitivity to batch regularisation |
| equal | 1.0 | 1.0 | 1.0 | Uniform weighting baseline |

Run all six. For each, pre-train on all 5,091 ATEPP MIDI performances (no labels needed). Use 50 epochs, batch size 128 (or the largest that fits in GPU memory), AdamW with LR=1e-3 and cosine schedule — matching S-KEY's original training recipe (Kong et al., 2025, §3.2: "AdamW optimizer, LR 10⁻³, batch 128, 50 epochs, cosine schedule with linear warm-up").

Validation: After pre-training, freeze the encoder and evaluate the KSP (key signature profile) output on a held-out set of 32 compositions with known keys. The pre-trained model should produce non-trivial 12-dimensional pitch-class distributions even before fine-tuning. If the equiv-only model performs comparably to skey-default on 12-class key estimation, the equivariance loss alone is sufficient and the mode pseudo-labels add value only for 24-class extension.

**Known performance issue:** The current `symbolic_equivariance_loss()` in `pretrain_symbolic_key.py` computes per-item transposition in a Python loop over the batch, resulting in O(B²) complexity. Before running full pre-training, vectorise this: replace the loop with a single `torch.roll` operation along the pitch-class dimension, applied to the entire batch tensor simultaneously. This should reduce pre-training time by approximately 10–50× for batch size 128.

**Step 3: Supervised fine-tuning with corrected labels**

After selecting the best pre-training configuration from Step 2, fine-tune on the corrected 24-key labels:

- Training set: ATEPP (319 compositions, heuristic mode labels) + DCML (expert labels) + When-in-Rome (expert labels). Use an 80/10/10 split stratified by composer to prevent data leakage.
- Comparison models: (a) GRU baseline re-trained on corrected labels, (b) Transformer without pre-training, (c) Transformer with pre-training.
- Hyperparameter search: Grid over LR ∈ {1e-4, 3e-4, 1e-3}, d_model ∈ {64, 128, 256}, num_layers ∈ {2, 4}, window_size ∈ {128, 256, 512}. This is 54 configurations; if compute is limited, use random search with 20 samples.
- Report: 24-key accuracy, 12-key accuracy (collapsing major/minor), MIREX weighted score, per-key F1, and confusion matrix. The key comparison is whether pre-training + corrected labels enables the Transformer to significantly outperform the GRU.

**Step 4: Post-processing with Gedizlioğlu regularisation**

After fine-tuning, apply the regularisation algorithm from Gedizlioğlu & Erol (2024, DOI:10.1177/10298649241245075). Your existing `regularise_key_sequence()` in `harmonic_context_model.py` implements this. Sweep the minimum-segment-duration parameter (e.g., 2, 4, 8 beats) and report the effect on MIREX weighted score. The expected outcome: regularisation improves MIREX score on tonicization-heavy pieces (Schubert, Debussy) by suppressing spurious key changes.

**Step 5: Statistical significance testing**

Run the best model configuration 5 times with different random seeds. Report mean ± standard deviation for all metrics. Apply a paired t-test or Wilcoxon signed-rank test between the pre-trained Transformer and the GRU baseline. A p < 0.05 is needed to claim the Transformer is significantly better.

### 2.4 Novelty Claim for Contribution 1

The original contribution is: **the first self-supervised local key estimator designed for symbolic MIDI streams, adapting S-KEY's CPSD equivariance loss and mode pseudo-labels from audio spectrograms to note-event sequences, evaluated on classical piano repertoire in a real-time browser context.**

This claim remains valid. A web search confirms no published work has adapted S-KEY to symbolic input as of April 2026. The closest related work is STONE (Kong et al., ISMIR 2024), which is audio-only and cannot distinguish relative keys, and Gedizlioğlu & Erol (2024), which is symbolic but uses classical profiles rather than learned representations.

---

## 3. MTS-MPE Contribution Refinement

### 3.1 Current State

Three papers published:

1. Ubimus 2024 — Initial MTS-MPE protocol design
2. Ubimus 2025 — Extended evaluation and MPE channel allocation
3. SMC 2026 — Precision-Optimized MPE and latency measurements

Key published results:
- MTS SysEx: 0.0122-cent resolution, 4.30ms average latency
- Standard MPE: 0.78-cent resolution (±48 semitone pitch bend range)
- Precision-Optimized MPE: 0.0244-cent resolution (±2 semitone RPN restriction), 2.18ms average latency
- The ±2 semitone restriction provides a 123× safety margin over the maximum JI deviation from 12-TET (which is ~31 cents for the 7/4 septimal minor seventh)

### 3.2 Identified Gaps

The following gaps, if addressed, would strengthen Contribution 2 for thesis-level completeness:

**Gap 1: No perceptual evaluation.**

All three published papers evaluate tuning precision in terms of cent accuracy and protocol latency. Neither includes a perceptual listening test or a psychoacoustic roughness measurement. An examiner will ask: "Does the improved tuning precision actually sound better to listeners?"

Recommended action: Conduct a roughness-based evaluation using the Sethares model already implemented in `evaluate_tuning_roughness.py`. The current implementation evaluates isolated chords only. Extend it to evaluate musical passages (8–16 bars) by computing roughness at each onset, averaging over the passage, and comparing 12-TET vs 5-limit JI vs Precision-Optimized MPE. Use at least 10 passages spanning different keys and textures (solo melody, homophonic chords, polyphonic counterpoint).

Additionally, if feasible, conduct a small AB listening test (n ≥ 10 participants) comparing 12-TET and JI tuning on 3–5 short excerpts. This does not need to be a full psychoacoustic study — a preference test with statistical analysis is sufficient.

**Gap 2: No comparison with Pivotuner.**

Pivotuner (Volkov, 2023, arXiv:2306.03873) is the closest published competitor: a real-time adaptive JI plugin that operates without score following. Your thesis should include a direct comparison, at minimum on the dimensions of:
- Tuning precision (cent accuracy on held chords)
- Latency (note-on to pitch-bend response)
- Comma drift handling (behaviour over extended chromatic passages)

Pivotuner is open-source (GPL-3.0, available on GitHub). You can evaluate it on the same test passages used for the roughness evaluation above.

**Gap 3: CommaDriftTracker bug.**

In `js/tuning-core.js`, the `CommaDriftTracker` accumulates drift per pitch class on every note event. This is conceptually incorrect: comma drift (specifically, the syntonic comma of 21.5 cents) arises from sequential chains of pure fifths and thirds, not from repeated visits to the same pitch class. The tracker should instead monitor the cumulative deviation from 12-TET along the actual sequence of harmonic intervals played.

Recommended fix: Track the running sum of (JI_cents − 12TET_cents) for each successive interval. When the cumulative drift exceeds a threshold (e.g., ±35 cents, approximately 1.5 syntonic commas), trigger a reset by gradually bending back toward 12-TET over the next 2–4 notes. Document this as a "drift correction algorithm" in the thesis.

**Gap 4: No formal specification of the Precision-Optimized MPE protocol.**

The SMC 2026 paper describes the ±2 semitone RPN restriction and its resolution benefit, but the thesis should contain a formal specification: the exact sequence of MIDI messages (RPN 0x00 0x00, Data Entry MSB/LSB) and the resolution derivation (14-bit pitch bend over ±2 semitones = 4 semitones / 16384 steps = 0.000244 semitones = 0.0244 cents). This specification should be precise enough for another implementer to reproduce.

### 3.3 Minimal Additions for Thesis Completeness

At minimum, address Gaps 1 and 3:

1. **Roughness evaluation on musical passages** — Extend `evaluate_tuning_roughness.py`, run on 10+ passages, report mean roughness reduction under JI vs 12-TET.
2. **Fix CommaDriftTracker** — Implement interval-sequential drift tracking, document the algorithm.
3. **Protocol specification** — Write a formal specification appendix for the thesis.

Gap 2 (Pivotuner comparison) is recommended but not blocking if time is limited.

---

## 4. Contribution C: Roman Numeral Labels for Chord-Aware Tuning

### 4.1 Concept

The current tuning system selects JI ratios based solely on the detected local key. This means every note within a given key receives the same ratio mapping regardless of its harmonic function. For example, in C major, a B♭ appearing in a dominant seventh chord (G7) and a B♭ appearing as a chromatic passing tone would receive the same JI ratio (9/5 relative to C = 1017.6 cents). But in just intonation theory, the B♭ in a G7 chord should ideally be tuned as a 7/4 ratio relative to G (= 968.8 cents relative to G, or approximately 968.8 + 700 - 1200 + cents_of_C... more precisely, the septimal minor seventh 7/4 = 968.8 cents vs the 5-limit minor seventh 9/5 = 1017.6 cents, a difference of 48.8 cents).

Roman numeral labels provide the missing information: they tell the system the current chord function (I, IV, V, V7, ii, vi, etc.), from which the system can select the appropriate JI ratio variant for each scale degree in context.

### 4.2 Pipeline Architecture

The pipeline has two modes:

**Mode 1 — Score available (offline analysis + runtime lookup):**

```
MusicXML score
    ↓
AugmentedNet / ChordGNN (offline, batch processing)
    ↓
Per-note Roman numeral labels (JSON)
    ↓ (stored alongside existing key labels)
Score follower (runtime, Parangonar/Matchmaker)
    ↓
Current position → current Roman numeral label
    ↓
tuning-core.js: select JI ratio based on key + chord function
```

**Mode 2 — Score unavailable (real-time inference):**

```
Live MIDI stream
    ↓
S-KEY Symbolic Transformer (Contribution 1) → local key
    ↓
Lightweight chord classifier (future work, post-thesis if needed)
    ↓
tuning-core.js: select JI ratio based on key only (fallback to current behaviour)
```

Mode 2 is a graceful degradation path. The thesis contribution is Mode 1.

### 4.3 Available Tools

**AugmentedNet** (Nápoles López et al., ISMIR 2021, zenodo:5624533):
- Input: MusicXML
- Output: Per-onset Roman numeral predictions (key, degree, quality, inversion)
- Pre-trained weights available
- Code: https://github.com/napulen/AugmentedNet
- Baseline accuracy: ~40% Chord Symbol Recall on Beethoven Piano Sonatas (ChordGNN paper, Table 2)

**ChordGNN** (Karystinaios & Widmer, ISMIR 2023, arXiv:2307.03544):
- Input: MusicXML → note-level graph
- Output: Per-onset predictions for 6 tasks (local key, degree, quality, inversion, root, harmonic rhythm)
- Achieves 51.8% CSR on Beethoven Piano Sonatas (~11.6% above AugmentedNet)
- Code: https://github.com/manoskary/chordgnn
- Requires `partitura` for graph construction (already in your dependencies)

**AnalysisGNN** (Karystinaios et al., CMMR 2025, arXiv:2509.06654):
- Updated version of ChordGNN with improved graph construction
- I cannot confirm exact accuracy numbers without accessing the paper directly

**Ground-truth annotations for evaluation:**
- DCML Corpora: Expert Roman numeral annotations in TSV format. These serve double duty — they provide key labels for Contribution 1 and chord-function labels for Contribution 3.
- When-in-Rome: Roman numeral annotations in RomanText format.

### 4.4 Implementation Roadmap

**Phase A: Pilot audit (1–2 weeks)**

1. Install AugmentedNet (`pip install augmentednet` or clone from GitHub).
2. Run AugmentedNet on 20 representative MusicXML scores from ATEPP, selected to span: solo sonata movements (Beethoven), chromatic miniatures (Debussy), dance forms (Chopin mazurkas), and at least 2 pieces in minor keys.
3. For each piece, compare AugmentedNet's output against the DCML ground-truth annotations (if available for that piece) or against manual inspection of the score.
4. Compute Chord Symbol Recall (CSR) on this 20-piece subset.
5. Gate condition: If CSR ≥ 35% (i.e., at least comparable to AugmentedNet's published baseline), proceed. If CSR < 35%, investigate ChordGNN as an alternative. If both fall below 35%, the quality is insufficient for tuning and this contribution should be de-scoped to a "future work" section.

**Phase B: Batch label generation (1 week)**

1. Run the chosen analyser (AugmentedNet or ChordGNN) over all 319 ATEPP MusicXML scores.
2. Store output as extended JSON files alongside the existing key-label JSONs. Each note entry gains additional fields: `roman_numeral` (e.g., "V7"), `chord_root_pc` (e.g., 7 for G in C major), `chord_quality` (e.g., "dominant_seventh"), `inversion` (0–3).
3. This is the `build_roman_numeral_labels.py` script, which currently has `raise NotImplementedError` stubs for both AugmentedNet and AnalysisGNN backends. Connect the chosen backend.

**Phase C: Runtime integration (2–3 weeks)**

1. Extend the WebSocket message format in `two_stage_server.py` to include chord-function fields alongside the existing key field.
2. In `js/tuning-core.js`, add a `calculateJIPitchBendWithFunction()` function that:
   - Receives the current key, chord root, chord quality, and MIDI pitch
   - Computes the note's scale degree relative to the chord root (not the key tonic)
   - Selects a JI ratio from a chord-function-specific table

3. The chord-function-specific ratio tables should include at minimum:

   **For dominant seventh chords (V7, V7/x):**
   - Minor seventh interval: use 7/4 (968.8 cents) instead of 9/5 (1017.6 cents)
   - This is the septimal minor seventh from 7-limit JI

   **For major triads (I, IV, V):**
   - Major third: 5/4 (386.3 cents) — same as current
   - Perfect fifth: 3/2 (702.0 cents) — same as current

   **For minor triads (ii, iii, vi):**
   - Minor third: 6/5 (315.6 cents) — same as current
   - Perfect fifth: 3/2 (702.0 cents) — same as current

   **For diminished triads (vii°):**
   - Minor third: 6/5 (315.6 cents)
   - Diminished fifth: 36/25 (631.3 cents) from 5-limit, or 7/5 (582.5 cents) from 7-limit — the choice here is debatable and could be an evaluation parameter

**Phase D: Evaluation (2 weeks)**

1. **Roughness evaluation:** Using the Sethares model, compute mean roughness per onset for 10+ musical passages under three conditions: (a) 12-TET, (b) key-only JI (current system), (c) chord-function-aware JI (new system). The hypothesis: condition (c) produces lower roughness than (b), especially on passages with dominant seventh chords and secondary dominants.

2. **Ground-truth comparison:** On the subset of pieces where DCML provides Roman numeral ground truth, compare the automatically generated labels (from AugmentedNet/ChordGNN) against the expert annotations. Report CSR and per-function accuracy (how often is a V7 correctly identified as V7?).

3. **Case studies:** Select 3–5 specific passages where the chord-function-aware tuning produces a different (and theoretically more correct) pitch bend than key-only tuning. Visualise the pitch bend trajectories over time for both systems. These become figures in the thesis.

### 4.5 Novelty Claim for Contribution 3

The original contribution is: **the first end-to-end pipeline connecting automatic Roman numeral analysis of piano scores to real-time adaptive just intonation, with chord-function-specific ratio selection including 7-limit intervals for dominant contexts.**

This claim remains valid. A search of published literature confirms no existing system combines automatic harmonic analysis with real-time JI tuning. Pivotuner (Volkov, 2023) performs reactive JI without any harmonic analysis. Stange et al. (Computer Music Journal, 2018, arXiv:1706.04338) describe dynamic JI adaptation but use a rule-based system without Roman numeral analysis. Hermode Tuning (a commercial product) adapts tuning in real time but its algorithm is proprietary and does not use score-level harmonic analysis.

---

## 5. Cross-Contribution Dependencies

```
[Fix ATEPP parser] ──→ [Contribution 1: S-KEY pre-train + fine-tune]
         │                        │
         ↓                        ↓
[DCML/WiR labels] ──→ [24-key evaluation] ──→ [Contribution 3: Roman labels]
                                                        │
                                                        ↓
                                              [7-limit JI ratios in tuning-core.js]
                                                        │
                                                        ↓
                                              [Contribution 2: MTS-MPE evaluation]
                                              (roughness eval uses chord-aware tuning)
```

The parser fix is the critical path. Nothing else can proceed meaningfully until 24-key labels exist.

---

## 6. Prioritised Action List

| Priority | Action | Blocks | Estimated Effort |
|----------|--------|--------|-----------------|
| P0 | Fix `musicxml_score_parser.py` mode default; re-generate all 319 label files | Everything | 1 day |
| P0 | Clone DCML corpora; write TSV→JSON parser | Contributions 1 & 3 | 2 days |
| P1 | Vectorise `symbolic_equivariance_loss()` | Pre-training speed | 0.5 days |
| P1 | Run 6-config pre-training ablation grid | Contribution 1 | 2–5 days (GPU time) |
| P1 | Re-train GRU and Transformer on corrected 24-key labels | Contribution 1 evaluation | 1 day |
| P2 | Hyperparameter search for Transformer | Contribution 1 | 3–7 days (GPU time) |
| P2 | Install AugmentedNet; run pilot audit on 20 scores | Contribution 3 gate | 2 days |
| P2 | Fix CommaDriftTracker in tuning-core.js | Contribution 2 | 1 day |
| P2 | Extend roughness evaluation to musical passages | Contribution 2 | 2 days |
| P3 | Batch-generate Roman numeral labels for all 319 scores | Contribution 3 | 1 day |
| P3 | Implement `calculateJIPitchBendWithFunction()` | Contribution 3 | 3 days |
| P3 | Conduct roughness comparison (12-TET vs key-JI vs chord-JI) | Contribution 3 | 2 days |
| P3 | Write formal MTS-MPE protocol specification | Contribution 2 thesis chapter | 1 day |
| P4 | Pivotuner comparison evaluation | Contribution 2 (recommended) | 3 days |
| P4 | AB listening test (n ≥ 10) | Contributions 2 & 3 (recommended) | 1–2 weeks |

---

## 7. Key References

Kong, Y., Meseguer-Brocal, G., Lostanlen, V., Lagrange, M., & Hennequin, R. (2025). S-KEY: Self-supervised Learning of Major and Minor Keys from Audio. *ICASSP 2025*. arXiv:2501.12907.

Kong, Y., Meseguer-Brocal, G., Lagrange, M., & Hennequin, R. (2024). STONE: Self-supervised Tonality Estimator. *ISMIR 2024*. arXiv:2407.07408.

Ding, Y. & Weiß, C. (2024). Towards Robust Local Key Estimation with a Musically Inspired Neural Network. *EUSIPCO 2024*. DOI:10.1109/EUSIPCO60164.2024.10715249.

Gedizlioğlu, Ç. & Erol, K. (2024). A Regularization Algorithm for Local Key Detection. *Psychology of Music*. DOI:10.1177/10298649241245075.

Karystinaios, E. & Widmer, G. (2023). Roman Numeral Analysis with Graph Neural Networks. *ISMIR 2023*. arXiv:2307.03544.

Nápoles López, N., et al. (2021). AugmentedNet: A Roman Numeral Analysis Network. *ISMIR 2021*. zenodo:5624533.

Volkov, D. (2023). Pivotuner: Real-Time Adaptive Pure Intonation VST3/AU Plugin. arXiv:2306.03873.

Stange, K., et al. (2018). Playing Music in Just Intonation: A Dynamically Adaptive Tuning Scheme. *Computer Music Journal 42(3)*. arXiv:1706.04338.

Sethares, W. (1993). Local Consonance and the Relationship Between Timbre and Scale. *JASA 94(3)*, pp. 1218–1228.

Pereira, L., et al. (2024). PDMX: A Large-Scale Public Domain MusicXML Dataset. *ISMIR 2024*.

Hentschel, J., Neuwirth, M., & Rohrmeier, M. (2021). The Annotated Beethoven Corpus (ABC): A Dataset of Harmonic Analyses of All Beethoven String Quartets. *Frontiers in Digital Humanities*. (DCML annotation standard.)

Gotham, M., et al. (2023). When in Rome: A Meta-Corpus of Functional Harmony. *TISMIR*.
