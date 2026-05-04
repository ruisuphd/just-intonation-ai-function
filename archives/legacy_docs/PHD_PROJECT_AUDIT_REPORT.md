# PhD Project Audit Report — Instant Harmonies
## Independent Research Audit (April 2026)

---

## 1. Scope and Methodology

This audit examines the **Instant Harmonies** project: a real-time just intonation tuning system for MIDI keyboards with AI-driven harmonic context estimation. The audit covers:

- Codebase architecture and implementation quality
- Evaluation results and their validity
- Claimed contributions versus published state of the art
- Bibliography accuracy
- Identified weaknesses with actionable remediation plans

Evidence sources: all files in the project workspace, evaluation JSON outputs, published thesis chapters, three conference papers (Ubimus 2024, Ubimus 2025, SMC 2026), the PhD AI Roadmap document, the detailed bibliography, and web searches for competing work conducted April 2026.

---

## 2. Executive Summary of Findings

### What is strong

The project has a well-engineered, modular system architecture. The MTS/MPE tuning layer is published, benchmarked, and genuinely novel as a browser-native implementation. The codebase is clean, well-documented, and the two-stage identification pipeline is architecturally sound. The roadmap demonstrates strong awareness of the relevant literature.

### What needs urgent attention

There are **four critical issues** that, if left unresolved, would significantly weaken a PhD examination:

1. **Zero minor key labels in the entire training dataset** — the most severe issue found
2. **The Transformer model does not outperform the GRU baseline** on the metric that matters most (accuracy), and the improvement on MIREX is marginal (+0.003)
3. **Three of the four planned AI contributions exist only as code scaffolds**, not completed research with validated results
4. **No perceptual evaluation** — the system's core claim (better tuning) has never been tested with human listeners

---

## 3. Critical Issue #1: Zero Minor Key Labels

### Evidence

Across all 319 score label JSON files (803,877 notes total), every note has `is_minor: false`. The key change records show 683 entries with `mode: "major"` and 6 with `mode: "none"`. Zero entries have `mode: "minor"`.

### Root Cause

The MusicXML `<mode>` element is **optional** according to the MusicXML 4.0 specification (source: W3C MusicXML 4.0 Reference, `<key>` element definition). When a score encodes a piece in A minor, the key signature is two flats (or rather, zero sharps for A minor — `<fifths>0</fifths>`), which is the same as C major. If the `<mode>` element is omitted, your parser in `musicxml_score_parser.py` defaults to `current_mode = 'major'` (line 107), treating every piece as major regardless of its actual tonality.

This is not an ATEPP-specific bug per se — it is a consequence of how many MusicXML engraving tools export key signatures. The ATEPP dataset sources its MusicXML from IMSLP and similar repositories, where encoding practices vary widely. No known ATEPP issue tracker entry exists for this specific problem.

### Impact

- **The models have never been trained on minor keys.** The confusion matrix confirms this: rows 12–23 (all minor keys) contain only zeros. The model literally cannot predict minor keys.
- **The MIREX weighted score is artificially inflated.** Since the test set also contains no minor key labels, the model is never penalised for major/minor confusion — the single hardest discrimination task in key detection. Your reported MIREX of 0.605 (GRU) and 0.608 (Transformer) is incomparable to published MIREX scores (e.g., S-KEY's 73.2% on FMAKv2), which evaluate on datasets containing both major and minor keys.
- **The self-supervised pre-training's mode loss is training against incorrect pseudo-labels.** In `pretrain_symbolic_key.py`, `generate_mode_pseudo_labels()` derives major/minor labels from PCP energy. But the supervised fine-tuning labels it is being compared against are exclusively major, creating a systematic mismatch.

### Remediation Plan

**Immediate (Week 1–2):**

1. Audit a sample of 20 MusicXML scores manually. Open them in MuseScore or similar and record the actual key and mode for each key signature. Compare against your extracted labels. This establishes ground truth for the bug.

2. Fix `musicxml_score_parser.py` to handle missing `<mode>` elements. When `<mode>` is absent, you have two options:
   - Conservative: flag the key as "ambiguous" and do not assign a mode label (use a 12-class key model instead of 24-class)
   - Heuristic: use the piece's pitch-class distribution to infer mode (the Krumhansl-Kessler profiles differ for major and minor; if the minor 3rd scale degree is more prominent than the major 3rd, the piece is likely minor)

3. Re-extract all 319 label files with the corrected parser.

**Short-term (Week 3–4):**

4. Re-train both models (GRU and Transformer) on the corrected labels.
5. Report results on a proper 24-key evaluation. If the corrected dataset still has very few minor key labels (possible if most ATEPP scores genuinely lack `<mode>` tags), supplement with an external annotated dataset — the Beethoven Piano Sonatas dataset used by ChordGNN (Karystinaios & Widmer, ISMIR 2023) has manually verified key labels including minor keys.

---

## 4. Critical Issue #2: Transformer Does Not Beat GRU Baseline

### Evidence

From the evaluation JSONs:

| Metric | GRU Baseline | Transformer (pretrained + finetuned) |
|--------|-------------|--------------------------------------|
| Test Accuracy | **0.4558** | 0.4545 |
| Test MIREX | 0.6050 | **0.6082** |
| Val Accuracy | **0.4151** | 0.3456 |
| Val MIREX | **0.5794** | 0.5365 |

The Transformer (your claimed novel contribution — S-KEY-Symbolic) performs **worse** on validation and is essentially tied on test. The test MIREX improvement is +0.003, which is not statistically significant on 285,440 predictions without a proper significance test.

### Per-Key Analysis

The Transformer shows dramatic variability across keys:
- C# major: 1.9% accuracy (vs GRU's 45.2%) — near-total failure
- B major: 13.8% accuracy (vs GRU's 8.4%) — both poor
- D major: 46.9% (vs GRU's 27.1%) — Transformer wins
- G major: 57.6% (vs GRU's 45.7%) — Transformer wins

This suggests the Transformer has learned stronger representations for some keys but collapses on others, possibly due to the small fine-tuning dataset (319 compositions) being insufficient for a 2-layer Transformer with ~500K parameters.

### Impact

The Transformer is the core of Contribution A (Paper 2 in your roadmap). If it does not meaningfully outperform the GRU baseline, the contribution claim — "the first self-supervised local key estimator for symbolic MIDI" — lacks empirical support. An examiner will ask: "Why is the novel model not better than the simpler baseline?"

### Remediation Plan

1. **Acknowledge the minor-key issue contaminates these results.** Once labels are corrected, re-run and the Transformer may differentiate itself — the self-supervised pre-training with mode pseudo-labels specifically targets major/minor discrimination, which is irrelevant under the current all-major labels.

2. **Hyperparameter search.** The current Transformer uses default hyperparameters (d_model=128, n_heads=4, n_layers=2). The fine-tuning LR is 1e-4 with 20 epochs. Try:
   - Lower LR (5e-5) with more epochs (50)
   - Larger window_size (512) to give the Transformer more context
   - Unfreezing only the key_head initially, then full model (staged fine-tuning)

3. **Ablation study.** Run the ablation grid in `pretrain_symbolic_key.py` (6 configurations already defined) and report which loss component contributes most. Currently there is no evidence the ablation has been run.

4. **Statistical significance.** Use McNemar's test or a paired bootstrap test to determine whether the Transformer's MIREX improvement is statistically significant.

---

## 5. Critical Issue #3: Three Contributions Are Scaffolds, Not Results

### Evidence

| Contribution | Code Status | Training Status | Evaluation Status |
|---|---|---|---|
| A: S-KEY-Symbolic Key Detection | Model architecture implemented. Pre-training and fine-tuning scripts complete. | Smoke tests only (per your confirmation). Checkpoints exist but from limited runs. | Eval scripts exist and produce output, but on incorrect labels (no minor keys). |
| B: Contrastive Piece Identification | `AriaEmbBaselineRetriever` is a stub (`raise NotImplementedError`). No `train_contrastive_identifier.py` exists. | Not started. | Not started. |
| C: Roman Numeral Labels | `build_roman_numeral_labels.py` exists but backend calls are `raise NotImplementedError`. Both AugmentedNet and AnalysisGNN integrations are TODO stubs. | Not started. | Not started. |
| Infrastructure: Matchmaker Score Following | Not started. `two_stage_server.py` still imports Parangonar exclusively. | N/A | N/A |

### Impact

Only Contribution A has any training infrastructure in place, and even that has only been smoke-tested. Contributions B and C are at the "code scaffold" stage — the architecture is designed but no model has been trained or evaluated. For a PhD thesis claiming four research contributions, this is a significant gap between ambition and evidence.

### Remediation Plan

**Prioritise ruthlessly.** You likely do not have time for all four contributions. I recommend:

1. **Contribution A (S-KEY-Symbolic) — highest priority.** Fix the minor key issue, re-train properly, run the ablation grid. This is your most novel claim and the code is closest to complete. Target: 2–3 months.

2. **Contribution C (Roman Numeral Labels) — second priority.** Install AugmentedNet, wire up the TODO stubs in `build_roman_numeral_labels.py`, run the pilot audit on 20 scores, and integrate function labels into tuning-core.js. This directly improves the tuning quality of the deployed system and is evaluable via the Sethares roughness metric you already have. Target: 2 months.

3. **Matchmaker integration — third priority.** This is the lowest-risk, highest-certainty improvement. Matchmaker is MIT-licensed, Python-based, and Partitura-compatible. The integration is engineering, not research. Target: 2–3 weeks.

4. **Contribution B (Contrastive Piece Identification) — deprioritise.** This requires training a contrastive encoder from scratch on ATEPP. The existing interval-based n-gram fingerprinter is already transposition-invariant (you converted from absolute to relative intervals). Unless an examiner specifically objects to the current identification approach, this contribution adds the least marginal value relative to its implementation cost.

---

## 6. Critical Issue #4: No Perceptual Evaluation

### Evidence

The thesis chapters mention listening studies as "future work." The evaluation scripts (`evaluate_tuning_roughness.py`, `evaluate_harmonic_context_model.py`) measure:
- Key detection accuracy and MIREX score
- Sethares roughness (computational, not perceptual)
- Tuning protocol latency

There is no evidence of any human listening test evaluating whether JI tuning actually sounds better than 12-TET to listeners in a controlled setting.

### Impact

The thesis's central premise is that just intonation tuning improves the musical experience. Without a perceptual evaluation, this claim rests entirely on psychoacoustic theory (Sethares roughness model) rather than empirical evidence. An examiner is likely to flag this as a gap between the system's motivation and its validation.

### Remediation Plan

Design a minimal viable listening study:

1. **Stimuli:** Select 8–12 musical excerpts covering major triads, minor triads, dominant 7ths, and chromatic passages. Render each excerpt under three conditions: 12-TET, 5-limit JI, and 7-limit JI (for dominant 7th contexts). Use a consistent piano timbre (e.g., Salamander samples from your audio engine).

2. **Protocol:** A/B preference test. Present pairs of the same excerpt in two tunings (randomised order). Ask participants: "Which sounds more in-tune?" and "Which do you prefer?"

3. **Participants:** 15–20 participants is sufficient for a within-subjects design. Mix musicians and non-musicians to test whether musical training affects preference.

4. **Analysis:** Binomial test per excerpt, plus mixed-effects logistic regression with musical training as a between-subjects factor.

5. **Timeline:** 2–3 weeks for stimulus preparation, 1 week for data collection (online is acceptable), 1 week for analysis.

---

## 7. Codebase Audit: Specific Issues

### 7.1 `musicxml_score_parser.py` — Minor Key Default (SEVERITY: Critical)

Line 107: `current_mode = 'major'`. When no `<mode>` element is present, the parser assumes major. This is the root cause of Critical Issue #1.

**Fix:** Change the default to `'none'` or `'unspecified'`, and handle this downstream.

### 7.2 `extract_score_key_labels.py` — Mode Propagation Bug

Line 99: `is_minor = mode in {'minor', 'min', 'm'}`. Since `mode` is always `'major'` or `'none'` (never `'minor'`), `is_minor` is always `False`. Even if the MusicXML did contain `<mode>minor</mode>`, the logic would work — but the data never triggers this path.

### 7.3 `pretrain_symbolic_key.py` — Per-Item Loss Computation is O(B²)

Lines 518–534: The loss is computed per-item in a Python loop over the batch, then averaged. For batch_size=32, this means 32 separate forward-pass slicing operations. This is functionally correct but ~10× slower than a vectorised implementation. For smoke tests this is fine; for full training on 5,000+ MIDIs, it will be a bottleneck.

**Fix:** Vectorise the equivariance loss to accept per-item transposition values as a tensor.

### 7.4 `two_stage_server.py` — Temp File Leak Risk

Line 365: `temp_path = tempfile.mktemp(suffix='.mid')`. `mktemp` is deprecated because it creates a race condition. Use `tempfile.NamedTemporaryFile(suffix='.mid', delete=False)` instead. The cleanup logic in `attempt_identification()` is correct but depends on no exception being raised between creation and the `finally` block.

### 7.5 `simple_ngram_fingerprinting.py` — SHA-256 Overhead

Line 31: `hashlib.sha256(str(intervals).encode('ascii')).hexdigest()`. For a 3-tuple of small integers, SHA-256 is overkill. The 64-character hex string is also memory-inefficient for the 177MB database. A simpler hash (e.g., `hash(intervals)` or a 64-bit FNV) would reduce both CPU and memory cost by ~4×.

### 7.6 `hybrid_piece_identifier.py` — AriaEmb Baseline is Dead Code

Lines 102–214: `AriaEmbBaselineRetriever` raises `NotImplementedError` on every method. This is acceptable as a scaffold but should be clearly marked as such. If included in a thesis appendix or code submission, it may appear to an examiner as unfinished work rather than planned future work.

### 7.7 `harmonic_context_model.py` — Sliding Window Truncation

Lines 412–419: When sequence length exceeds `max_seq_len`, the Transformer simply truncates to the most recent 512 notes. The comment states "key detection is local" to justify this. This is defensible for inference, but during training, it means the model never sees the beginning of long pieces — only the tail end of each window. Since the label distribution may differ between piece beginnings (typically in the home key) and middles (where modulations occur), this could introduce a systematic bias.

### 7.8 `tuning-core.js` — CommaDriftTracker Accumulates Per Pitch Class Incorrectly

Lines 188–199: `this.cumulativeDrift[pc] += rawCents`. The drift accumulates the JI cents offset every time a note of that pitch class is played. But the Stange et al. (2018) concept of comma drift refers to *sequential* harmonic motion accumulating deviations, not repeated notes of the same pitch class. Playing middle C ten times should not accumulate drift; playing C→G→D→A→E→B→F#→C# (a sequence of fifths) should. The current implementation conflates these two cases.

**Fix:** Track drift based on the sequence of harmonic intervals, not per-pitch-class accumulation.

### 7.9 `evaluate_tuning_roughness.py` — Only Evaluates Isolated Chords

The Sethares roughness evaluation computes roughness for isolated chords in 12 keys. It does not evaluate roughness on actual musical passages from the ATEPP dataset. An examiner may question whether isolated-chord roughness translates to perceived quality in real music.

**Fix:** Add an evaluation mode that takes a short MIDI excerpt, applies each tuning scheme note-by-note using the key detection output, and computes windowed roughness over time.

---

## 8. Bibliography Audit

### Verified Citations

| Citation | Status |
|---|---|
| S-KEY (Kong et al., ICASSP 2025, arXiv:2501.12907) | **Confirmed** — paper, venue, code repository verified. Specific MIREX numbers (73.2%, 74.4%, etc.) could not be independently verified from accessible HTML — recommend checking against the PDF. |
| Matchmaker (Park et al., ISMIR 2025, arXiv:2510.10087) | **Confirmed** — 92.8% total AR on nASAP verified. |
| CLaMP 3 (Wu et al., arXiv:2502.10362) | **Confirmed** — venue is ACL 2025 **Findings** (not main conference). Correct this in your bibliography. |
| AnalysisGNN (Karystinaios et al., arXiv:2509.06654) | **Confirmed** — CMMR 2025. |
| AriaEmb (Bradshaw et al., arXiv:2506.23869) | **Confirmed** — ISMIR 2025. Note: "AriaEmb" is the model name, not part of the paper title. The paper title is "Scaling Self-Supervised Representation Learning for Symbolic Piano Performance." |
| Ramani 2026 (arXiv:2603.29710) | **Confirmed** — submitted March 2026. |
| RNBert (Sailor, ISMIR 2024) | **Confirmed**. |

### Unverified Claims in Bibliography

The detailed bibliography document (`research-bibliography-detailed.md`) states S-KEY's loss weight is "λ_BCE = 1.5, not λ_S-KEY." This is a naming convention detail. The verification log at the bottom of that document honestly flags several items as "not independently confirmed" — this transparency is good practice.

### Missing Citation

The bibliography does not cite **Pivotuner** (Volkov, 2023, arXiv:2306.03873) in the main reference list, though it appears in the roadmap. Pivotuner is the closest direct competitor — a real-time adaptive JI plugin — and should be cited and differentiated prominently in any paper or thesis chapter on the tuning system.

---

## 9. Competitive Landscape Assessment

### Has anyone done what you propose?

Based on web searches conducted April 2026:

| Proposed Contribution | Competing Work Found? |
|---|---|
| Self-supervised symbolic (MIDI) key detection | **No.** S-KEY operates on audio CQT. STONE operates on audio. No published work adapts the S-KEY framework to symbolic MIDI input. |
| Contrastive piece identification on ATEPP | **No.** CLaMP 3 and MIDI-Zero do symbolic retrieval but not piece identification from short performance prefixes on ATEPP specifically. |
| Roman numeral analysis → real-time JI tuning | **No.** ChordGNN and AugmentedNet do Roman numeral analysis; Stange et al. and Pivotuner do adaptive JI. No published work connects the two. |
| Browser-native real-time JI with MTS/MPE | **No direct competitor in the browser.** Pivotuner is a VST3/AU plugin (native, not browser). Hermode Tuning is proprietary. |

**Conclusion:** Your novelty claims remain valid as of April 2026. The gap between audio-based self-supervised key detection and symbolic MIDI is real and unoccupied. The gap between harmonic analysis and adaptive tuning is also unoccupied. These are genuine research contributions if you can demonstrate them empirically.

---

## 10. Strengthening Plan — Prioritised Actions

### Tier 1: Must Fix (blocks thesis defensibility)

| # | Action | Effort | Impact |
|---|---|---|---|
| 1 | Fix minor key label extraction (parser + re-extract all 319 labels) | 1 week | Unblocks all model training and evaluation |
| 2 | Re-train GRU and Transformer on corrected labels | 1–2 weeks | Produces valid evaluation numbers |
| 3 | Run full self-supervised pre-training (not smoke test) on ATEPP | 2–3 weeks | Validates Contribution A |
| 4 | Run the ablation grid (6 configs in pretrain_symbolic_key.py) | 1 week (compute) | Demonstrates which loss component matters |
| 5 | Conduct basic listening study (15–20 participants, A/B preference) | 3–4 weeks | Validates the thesis's central claim |

### Tier 2: Should Do (strengthens examination significantly)

| # | Action | Effort | Impact |
|---|---|---|---|
| 6 | Wire up AugmentedNet in build_roman_numeral_labels.py | 2 weeks | Enables Contribution C |
| 7 | Run pilot audit of Roman numeral labels on 20 scores | 1 week | Quality gate for Contribution C |
| 8 | Integrate Matchmaker alongside Parangonar | 2 weeks | Upgrades score following to SOTA |
| 9 | Fix CommaDriftTracker to track sequential harmonic drift | 1 week | Corrects a conceptual error |
| 10 | Add passage-level roughness evaluation (not just isolated chords) | 1 week | Strengthens tuning quality evidence |

### Tier 3: Nice to Have (if time permits)

| # | Action | Effort | Impact |
|---|---|---|---|
| 11 | Train contrastive piece identification encoder | 4–6 weeks | Contribution B — consider deferring |
| 12 | Vectorise per-item loss in pretrain_symbolic_key.py | 2 days | Training speed improvement |
| 13 | Port Transformer to ONNX for browser inference | 2 weeks | Engineering, not research contribution |
| 14 | Supplement training data with Beethoven Piano Sonatas dataset | 1 week | Addresses potential minor-key label scarcity |

---

## 11. Questions an Examiner Will Ask

Based on the evidence reviewed, these are the questions I would ask if examining this thesis:

1. "Your key detection models were trained on labels that contain zero minor keys. How do you know your system works for minor-key pieces, which constitute roughly half of the piano repertoire?"

2. "The Transformer model does not outperform the simpler GRU baseline on accuracy. What evidence supports the claim that the S-KEY adaptation adds value over the existing approach?"

3. "You claim the system produces 'better tuning,' but the only tuning evaluation is a computational roughness metric on isolated chords. Have you tested whether listeners actually prefer the JI tuning?"

4. "Contributions B and C are described in your roadmap but the code contains TODO stubs and NotImplementedError. What is the status of these contributions, and are they part of your thesis claims?"

5. "How does your system compare to Pivotuner (Volkov, 2023), which also does real-time adaptive JI without requiring piece identification or score following?"

6. "The ATEPP dataset contains automatically transcribed performances, not studio recordings. How robust is your fingerprint identification to transcription errors in the source MIDI?"

---

## 12. Summary

Your project has a strong architectural foundation, genuine novelty in the browser-native JI pipeline, and a well-researched roadmap grounded in current literature. The competitive landscape assessment confirms that no one has occupied your proposed contribution space.

However, the thesis currently has a critical data quality issue (no minor keys), insufficient empirical evidence for its core claims (no listening study, Transformer does not beat baseline), and three of four planned AI contributions at the scaffold stage.

The single highest-impact action you can take right now is fixing the minor key label extraction and re-training your models. Everything else builds on that foundation.

---

*Report generated April 2, 2026. Based on analysis of all project files, evaluation outputs, published papers, thesis chapters, and web-verified bibliography.*
