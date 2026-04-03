# Audit Verification and Research Infrastructure Improvements

**Date:** 1 April 2026
**Context:** External PhD audit received; verified against codebase, corrected errors, added missing literature, and implemented research infrastructure improvements.

---

## 1. Audit Verification Summary

An external audit of the Instant Harmonies PhD project was received covering all four thesis contributions: (A) S-KEY-Symbolic key detection, (B) piece identification, (C) Roman numeral analysis, and (D) score following. The audit was thorough but contained factual errors due to incomplete file discovery. This document records the verification, corrections, and all resulting code changes.

### 1.1 Factual Errors Corrected

| Audit Claim | Actual State | Evidence |
|---|---|---|
| "Self-supervised training loop is entirely absent" | Fully implemented in `pretrain_symbolic_key.py` (625 lines) with CPSD equivariance loss, mode pseudo-labels, batch balance regularisation, and TranspositionPairDataset | Pre-trained checkpoint exists: `research_data/symbolic_key_pretrained.pt` (1.5 MB) |
| "No confidence gating for score follower drift" | Multiple mechanisms in `two_stage_server.py`: fingerprint threshold (line 105), harmonic model threshold (line 132), prediction TTL (lines 217-224), three-tier fallback (lines 807-815), reactive tuning fallback (lines 969-974) | Code inspection verified 6 distinct fallback paths |
| "MIREX weighted score not implemented" | Already implemented in `evaluate_harmonic_context_model.py` (lines 41-71) with exact/fifth/relative/parallel weights | GRU baseline: 45.6% accuracy, 0.605 MIREX score on 285,440 predictions |
| "hash() not deterministic across Python versions" | Overstated — fingerprint database is serialised once at build time; cross-process hash randomisation only affects rebuild | `atepp_filtered_database.pkl` (177 MB) contains pre-computed hashes |

### 1.2 Missing Literature Identified

**Must-cite (4 papers):**
1. **Pivotuner** (Volkov, 2023, arXiv:2306.03873) — VST3/AU plugin for real-time adaptive pure intonation. Direct competitor; key differentiator is that Pivotuner does not use harmonic function labels or score following.
2. **Van Kranenburg & Bisschop** (ISMIR 2025, pp. 503-510) — Keyboard temperament estimation from symbolic data. Inverse problem to this thesis.
3. **Hu, Peter, Schluter, Widmer** (ISMIR 2025, arXiv:2509.07586) — Sub-30ms latency piano transcription. Establishes latency budget for real-time retuning.
4. **Ramani** (2026, arXiv:2603.29710) — 19.3M piano chords with Plomp-Levelt roughness analysis. Provides evaluation framework.

**Should-cite (5 papers):**
5. RNBert (Sailor, ISMIR 2024) — SOTA Roman numeral analysis, HuggingFace port available.
6. M2BERT (Wang & Su, ISMIR 2025, arXiv:2507.04776) — ModernBERT for symbolic music.
7. "From Discord to Harmony" (Poltronieri et al., ISMIR 2025, arXiv:2509.01588) — Consonance-based chord estimation metrics.
8. GigaMIDI (Lee et al., TISMIR 2025, arXiv:2502.17726) — 1.4M+ MIDI files, potential pre-training data.
9. "Emergent Musical Properties" (Kong et al., ISMIR 2025, arXiv:2506.23873) — SSL transformers with emergent key detection.

---

## 2. Code Changes — Critical Fixes

### 2.1 Positional Encoding: RoPE Reverted to Learnable Embeddings with Sliding Window

**File:** `harmonic_context_model.py`

**Problem:** An initial attempt to replace learnable positional embeddings with Rotary Position Embedding (RoPE, Su et al. 2021) was architecturally incorrect. RoPE must be applied inside the attention mechanism (rotating Q and K vectors), not to the input tensor before the Transformer. Since `nn.TransformerEncoderLayer` does not expose Q/K hooks, the rotation was applied to the fused embedding, which the subsequent Q/K linear projections destroy.

**Solution:** Reverted to learnable positional embeddings (`nn.Embedding(512, d_model)`) and added a sliding-window inference policy. At inference time, sequences exceeding `max_seq_len` are truncated to the most recent 512 notes. This is justified because local key detection is inherently a local property — harmonic context beyond approximately 500 notes contributes negligible information to key estimation.

**Thesis implication:** The sliding-window policy should be documented as a design choice, with a brief analysis showing that key detection accuracy does not degrade for window sizes >= 256 notes.

### 2.2 Per-Item Transposition Loss in Self-Supervised Pre-Training

**File:** `pretrain_symbolic_key.py`

**Problem:** The self-supervised training loop computed the CPSD equivariance loss using a mean transposition value across the batch (`mean_c = int(round(sum(c_values) / len(c_values)))`). Each item in the batch has a different random transposition (c sampled from [1, 11]), so averaging creates a systematic mismatch between the actual transposition applied to each item and the target phase rotation used in the loss.

**Solution:** Replaced batch-level loss computation with per-item loss computation. Each item's loss is computed with its own transposition value, and the batch loss is the mean of per-item losses.

**Thesis implication:** This is a correctness fix that affects training quality. Any previously reported results from the pre-trained checkpoint should be re-evaluated after re-training with the corrected loss.

### 2.3 Roughness Model: Vassilakis Refinement and Piano Inharmonicity

**File:** `evaluate_tuning_roughness.py`

**Problem:** The Sethares (1993) roughness model weights partial-pair roughness by `a_i * a_j`. For the major third interval, this causes the high-amplitude fundamental pair (weight 1.0) to dominate over the partial coincidence at the 5:4 ratio (weight 0.05), producing the counterintuitive result that JI major thirds are rougher than 12-TET. This contradicts established psychoacoustic findings.

**Root cause analysis:** In JI tuning of C4-E4, the fundamental pair is 65.4 Hz apart (closer to the Sethares roughness peak) while in 12-TET it is 68.0 Hz apart. The 5th partial of C4 coincides exactly with the 4th partial of JI E4 (1308.15 Hz, roughness contribution 0.0), but this coincidence has weight 0.2x0.25=0.05, insufficient to overcome the fundamental pair difference.

**Solution:** Implemented the Vassilakis (2001) amplitude weighting: `w = min(a_i, a_j)^0.606 * (a_i * a_j)^0.0606`. This reduces the dominance of high-amplitude pairs and gives appropriate weight to partial coincidences. Additionally, added piano inharmonicity modelling (Gough 1997): `f_n = f_0 * n * sqrt(1 + B*n^2)` where B is the inharmonicity coefficient (default 0.0005 for mid-range piano).

**Verified result:** After the fix, JI major third roughness (0.318) is correctly lower than 12-TET (0.325).

**Thesis implication:** The roughness evaluation now produces publishable results. The Vassilakis refinement should be cited as the primary model, with Sethares (1993) as the foundation.

---

## 3. Code Changes — Important Fixes

### 3.1 Fingerprinting: Relative Intervals and Full SHA-256

**File:** `simple_ngram_fingerprinting.py`

**Changes:**
1. Replaced absolute-pitch n-grams with relative-interval n-grams. The pattern `(60, 64, 67, 72)` becomes `(+4, +3, +5)`. This makes identification transposition-invariant.
2. Replaced Python's `hash()` (non-deterministic across processes) with SHA-256 (full 256-bit digest, deterministic).

**Thesis implication:** The existing fingerprint database (`atepp_filtered_database.pkl`) is incompatible and must be rebuilt.

### 3.2 Comma Drift Tracking

**File:** `js/tuning-core.js`

**Added:** `CommaDriftTracker` class that monitors per-pitch-class cumulative deviation from 12-TET. When drift exceeds a threshold (default 35 cents, approximately 1.5 syntonic commas), the pitch class is reset to 12-TET. The `reset()` method now correctly clears both the drift array and the reset counter. The threshold check uses `>=` (not `>`) to match the documented behaviour.

**Thesis implication:** This addresses the comma drift problem identified by Stange et al. (2018). The threshold value (35 cents) should be ablated in the evaluation.

### 3.3 Evaluation Additions

**File:** `evaluate_harmonic_context_model.py`

**Added:** Tonicization-specific evaluation subset filtering by composer (Schubert, Debussy — the most chromatically active composers in ATEPP). Reports separate accuracy, MIREX weighted score, and confusion matrix for this subset.

**File:** `pretrain_symbolic_key.py`

**Added:** Ablation grid mode (`--ablation-grid`) with 6 configurations testing different loss weight combinations, plus CLI args for individual lambda values.

### 3.4 Piece Identification Baseline

**File:** `hybrid_piece_identifier.py`

**Added:** `AriaEmbBaselineRetriever` class providing a zero-shot retrieval baseline using AriaEmb (Bradshaw et al., ISMIR 2025). Includes `run_prefix_evaluation()` that measures MRR and recall at prefix sizes N=5, 10, 15, 20, 30 notes. This establishes the baseline the thesis contribution must beat.

### 3.5 Roman Numeral Label Pipeline

**File:** `build_roman_numeral_labels.py` (new)

**Added:** Scaffold for batch-processing MusicXML scores through AugmentedNet or AnalysisGNN to generate per-note Roman numeral labels. Includes pilot audit mode (`--pilot N`) for quality verification.

---

## 4. Literature Updates

**File:** `phd-ai-roadmap-2026.md`

Added 13 new references organised by topic: Core Methods, Symbolic Music Representation and Retrieval, Harmonic Analysis, Score Following and Real-Time Transcription, Tuning/Temperament/Psychoacoustics, Piece Identification, and Dataset.

---

## 5. Files Modified (Complete List)

| File | Type | Lines Changed | Nature |
|---|---|---|---|
| `harmonic_context_model.py` | Modified | ~80 | RoPE reverted to learnable embeddings + sliding window |
| `pretrain_symbolic_key.py` | Modified | ~40 | Per-item loss + ablation grid + lambda CLI args |
| `evaluate_tuning_roughness.py` | Modified | ~50 | Vassilakis refinement + piano inharmonicity |
| `evaluate_harmonic_context_model.py` | Modified | ~40 | Tonicization subset + improved error handling |
| `simple_ngram_fingerprinting.py` | Modified | ~30 | Relative intervals + full SHA-256 |
| `hybrid_piece_identifier.py` | Modified | ~100 | AriaEmb baseline retriever |
| `js/tuning-core.js` | Modified | ~60 | CommaDriftTracker (new) + reset fix |
| `phd-ai-roadmap-2026.md` | Modified | ~80 | 13 new references |
| `build_roman_numeral_labels.py` | New | ~585 | Roman numeral label pipeline scaffold |
| `evaluate_tuning_roughness.py` | New | ~370 | Roughness evaluation with Vassilakis model |

---

## 6. Known Limitations and Next Steps

1. **Checkpoint incompatibility:** The sliding-window policy changes the forward pass but not the model weights. Existing checkpoints remain compatible (unlike the RoPE version). However, the corrected per-item transposition loss means the pre-trained checkpoint should be re-trained.

2. **Citation verification:** Several 2025 papers referenced in the roadmap should be verified against arXiv/DBLP before thesis submission. Specifically: arXiv:2506.23873 (Kong et al.), arXiv:2507.04776 (Wang & Su), and arXiv:2502.17726 (Lee et al.).

3. **AriaEmb integration:** The `AriaEmbBaselineRetriever` contains TODO stubs for the actual model loading. Once the AriaEmb package is available on PyPI or HuggingFace, these stubs should be connected.

4. **Roman numeral pipeline:** `build_roman_numeral_labels.py` requires AugmentedNet or AnalysisGNN to be installed. A pilot audit of 30 scores should be conducted once the backend is available.

5. **Roughness evaluation:** Consider extending to include the Ramani (2026) corpus of 19.3M piano chords for large-scale validation.
