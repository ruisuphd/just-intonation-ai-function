# Changelog — Adaptive Just Intonation Tuner

## v0.9.2 — 2026-04-10 (Research Integrity Fixes + Training Improvements)

### Critical Bug Fixes (Research Integrity)

#### Bug 1: Velocity Feature Hardcoded in Training (MEDIUM)
- **Problem:** `train_harmonic_context_model.py:233` hardcoded velocity to 96 for all training examples (`sum(96 > edge ...)`). At inference, actual MIDI velocity was used via `harmonic_context_model.py:191`, creating a train-inference feature mismatch.
- **Nuance:** Current MusicXML-derived training labels lack velocity fields, so the fix has zero effect on existing data. However, it enables future velocity-aware training when MIDI performance data is used directly.
- **Fix:** Read actual velocity with fallback: `vel = int(note.get('velocity', 96))`.
- **Files:** `train_harmonic_context_model.py` (line 233)

#### Bug 2: Data Leakage — Ensemble Alpha Tuned on Test Set (CRITICAL)
- **Problem:** `ensemble_key_detector.py` grid-searched ensemble alpha (0.00–1.00 in 0.05 steps) by evaluating on the TEST set. The alpha that maximized test MIREX was selected and used to report test results — textbook data leakage inflating reported metrics.
- **Fix:** Added `--val-predictions` argument. When provided, alpha is tuned on VALIDATION predictions, then evaluated once on test with the fixed alpha. Legacy behavior preserved with a deprecation warning when `--val-predictions` is omitted.
- **Impact:** Reported ensemble MIREX will decrease (honest numbers).
- **Files:** `ensemble_key_detector.py` (new: `search_alpha_on_validation()`, modified: `evaluate_ensemble_on_compositions()` with `split_name` param)

#### Bug 3: Data Leakage — HMM Hyperparameters Tuned on Test Set (CRITICAL)
- **Problem:** `hmm_postprocessing.py` grid-searched `self_transition` × `tau` (30 combinations) using test set predictions. Best hyperparameters were selected by test delta — same leakage pattern as Bug 2.
- **Fix:** Added `--val-predictions` argument. When provided, grid search runs on validation predictions, best parameters evaluated once on test. Deprecation warning when omitted.
- **Impact:** Reported HMM MIREX will decrease (honest numbers).
- **Files:** `hmm_postprocessing.py`

### Training Improvements

#### Gradient Clipping (Pascanu et al., ICML 2013)
- Added `--clip-grad` flag (float, default 1.0, 0 to disable).
- Applies `torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)` between `loss.backward()` and `optimizer.step()`.
- Standard practice for RNNs to prevent gradient explosion during training.
- **Files:** `train_harmonic_context_model.py`

#### Circle-of-Fifths Label Smoothing (Novel — adapted from Szegedy et al., CVPR 2016)
- Added `--label-smoothing` flag (float, default 0.0, recommended 0.1).
- Instead of uniform label smoothing, distributes epsilon mass proportionally to MIREX key similarity: fifth relation = 0.5, relative key = 0.3, parallel key = 0.2, other = 0.0.
- This directly aligns the training objective with the evaluation metric — a novel contribution that encodes music-theoretic knowledge into the loss function.
- New class `MusicTheoreticLabelSmoothing` precomputes a 24×24 kernel. Compatible with class weights and focal loss.
- **Files:** `train_harmonic_context_model.py`

#### Weight Decay as Hyperparameter (Loshchilov & Hutter, ICLR 2019)
- Exposed `--weight-decay` flag (float, default 0.01) for the AdamW optimizer.
- The 67K-param GRU may benefit from lower decay (0.001). Now tunable in ablation grid.
- **Files:** `train_harmonic_context_model.py`

#### Mixed-Precision Training (Micikevicius et al., ICLR 2018)
- Added `--amp` flag for automatic mixed-precision on CUDA devices.
- Uses `torch.cuda.amp.autocast()` + `GradScaler` for ~2x speedup on T4 GPU.
- Only activates on CUDA; MPS/CPU silently ignore the flag.
- **Files:** `train_harmonic_context_model.py`

### Evaluation Improvements

#### Validation-Set Prediction Saving
- Added `--save-val-predictions` flag to `evaluate_harmonic_context_model.py`.
- Generates per-note validation predictions with softmax probabilities.
- Required by Bug 2 and Bug 3 fixes: ensemble alpha and HMM hyperparameters must be tuned on validation, not test.
- **Files:** `evaluate_harmonic_context_model.py`

#### McNemar's Test for Pairwise Model Comparison (McNemar, 1947)
- Added `--compare <prediction_file>` flag to `evaluate_harmonic_context_model.py`.
- Computes McNemar's chi-squared test with continuity correction between two models.
- Reports chi2, p-value, and significance level (*, **, ***).
- Used to test whether differences between ablation experiments (A1 vs A6, etc.) are statistically significant.
- **Files:** `evaluate_harmonic_context_model.py`

#### BiGRU Documented as Non-Causal Upper Bound
- Added docstring to `HarmonicContextGRU` in `harmonic_context_model.py` documenting that `bidirectional=True` is for offline evaluation only — not deployable in the real-time tuner pipeline.
- Ablation table (`generate_ablation_table.py`) now marks bidirectional models with a dagger footnote (†) in both Markdown and LaTeX output.
- **Files:** `harmonic_context_model.py`, `generate_ablation_table.py`

### Phase 2 Runner Updates
- **Part A:** Now generates BOTH validation and test predictions with softmax.
- **Part B:** Passes `--val-predictions` to HMM grid search (fixes data leakage).
- **Part C:** Passes `--val-predictions` to ensemble alpha search (fixes data leakage).
- **Part E:** Added experiments A10 (gradient clipping + label smoothing) and A11 (all improvements combined). Training commands now pass `--clip-grad`, `--label-smoothing`, `--weight-decay`, and `--amp` when configured.
- **Files:** `colab_phase2_runner.py`

### Research References

| Change | Reference | Year |
|--------|-----------|------|
| Gradient clipping | Pascanu, Mikolov & Bengio, "On the difficulty of training RNNs," ICML | 2013 |
| Label smoothing | Szegedy et al., "Rethinking the Inception Architecture," CVPR | 2016 |
| CoF smoothing kernel | Novel — MIREX-weighted kernel for key detection | 2026 |
| AdamW weight decay | Loshchilov & Hutter, "Decoupled Weight Decay Regularization," ICLR | 2019 |
| Mixed-precision | Micikevicius et al., "Mixed Precision Training," ICLR | 2018 |
| McNemar's test | McNemar, Psychometrika | 1947 |

---

## Files Modified (v0.9.2)

| File | Changes |
|------|---------|
| `train_harmonic_context_model.py` | Velocity fix, gradient clipping, label smoothing, weight decay, AMP |
| `ensemble_key_detector.py` | Data leakage fix: val-based alpha tuning |
| `hmm_postprocessing.py` | Data leakage fix: val-based hyperparameter tuning |
| `evaluate_harmonic_context_model.py` | Val prediction saving, McNemar's test, --compare flag |
| `harmonic_context_model.py` | BiGRU non-causal documentation |
| `generate_ablation_table.py` | BiGRU dagger footnote (Markdown + LaTeX) |
| `colab_phase2_runner.py` | Parts A-E updated for leakage fixes + new experiments |

---

## v0.9.1 — 2026-04-08 (App Fixes + S-KEY Phase 2 Preparation)

### Bug Fixes

#### Piece Identification: Silent Failure (CRITICAL)
- **Problem:** When piece identification failed (low confidence, no match), no event was emitted to the client. The UI stayed at "Connected - Ready for identification" indefinitely, giving no feedback to the user.
- **Root cause:** `handle_midi_note()` in `two_stage_server.py` only emitted `piece_identified` on success. Failed attempts were silently discarded.
- **Fix:** Added `identification_attempt` WebSocket event for failed identifications, showing buffer size, best guess (if any), and retry message.
- **Files:** `two_stage_server.py` (lines 958-970), `two_stage_client.js` (new event handler)

#### Reconnection Clears Identified Piece (HIGH)
- **Problem:** Socket.IO auto-reconnect triggered `clearAllUI()` on every reconnect, wiping identification results and score-following state.
- **Root cause:** The `connect` event handler unconditionally reset all client state.
- **Fix:** Only reset state on initial connection; reconnects preserve existing state and rely on `system_status` events for synchronization.
- **Files:** `two_stage_client.js` (connect handler)

#### No Collection Progress Feedback (MEDIUM)
- **Problem:** Users had no way to know how many notes the system had collected or whether identification was being attempted.
- **Fix:** `system_status` handler now displays collection progress ("Collecting... 15 notes (need 30 to identify)") using `buffer_size` from the server status payload.
- **Files:** `two_stage_client.js` (system_status handler)

### Security Improvements

#### CORS Wildcard Restricted (HIGH)
- **Before:** `CORS(app, resources={r"/*": {"origins": "*"}})` — any website could connect.
- **After:** Restricted to localhost origins (ports 3000, 5005, 8000) on both 127.0.0.1 and localhost.
- **Files:** `two_stage_server.py` (ALLOWED_ORIGINS)

#### innerHTML Replaced with textContent (MEDIUM)
- Replaced all `innerHTML` assignments with `textContent` or DOM construction in `two_stage_client.js` to prevent XSS vectors.
- **Functions fixed:** `clearAllUI()`, `updateIdentificationDisplay()`, `identification_attempt` handler, `system_status` collection progress.
- **Note:** Some display methods still use innerHTML where HTML structure is needed (score following, predicted notes) — these use only server-controlled data.

### Stability Improvements

#### Script Loading Order Fixed (CRITICAL)
- **Before:** `two_stage_client.js` loaded as regular `<script>` (synchronous), executing before ES modules `main.js` and `ui-controller.js` had exported `window.handleNoteOn` and `window.clearBackendHarmonicPrediction`.
- **After:** Changed to `<script defer>` ensuring it runs after DOM is ready and module scripts have initialized.
- **Files:** `index.html` (line 161)

#### setInterval Memory Leak Fixed (HIGH)
- **Before:** `ui-controller.js` used `setInterval` to poll for `window.handleNoteOn` with no timeout — if `handleNoteOn` was never defined, the interval ran forever (100ms loop).
- **After:** Added 50-retry limit (5 seconds max), then clears interval with a console warning.
- **Files:** `js/ui-controller.js` (checkAndHook)

#### Server State Reset on Reconnect (HIGH)
- **Before:** `handle_connect()` only reset IDENTIFIED and SCORE_FOLLOWING states. If a client disconnected during IDENTIFYING or ERROR state, the system would be stuck.
- **After:** Now also resets IDENTIFYING and ERROR states outside the grace period.
- **Files:** `two_stage_server.py` (handle_connect)

#### Buffer Validation (MEDIUM)
- Added input validation in `_buffer_to_midi_file()`: validates that all buffer entries have required fields (pitch, timestamp, velocity) and that at least 4 valid notes exist (minimum for n-gram fingerprinting).
- **Files:** `two_stage_server.py` (_buffer_to_midi_file)

### UI Improvements

#### Responsive Layout (MEDIUM)
- Added CSS `@media` query for screens narrower than 600px with adjusted margins, font sizes, and padding.
- **Files:** `index.html` (style block)

---

## v0.9.0 — 2026-04-08 (S-KEY Phase 1 Ablation + Phase 2 Preparation)

### S-KEY Key Detection (C1)

#### Ablation Infrastructure
- Added `--no-augment` flag to training script for controlled ablation
- Implemented ENS class weighting (Cui et al., CVPR 2019) with `--weight-mode ens` and `--ens-beta`
- Enhanced checkpoint metadata with all hyperparameters for reproducibility
- Created `colab_ablation_runner.py` — self-contained script for running 6-experiment ablation grid on Colab T4

#### Evaluation Enhancements
- Added composition-level bootstrap CI (1000 iterations) to `evaluate_harmonic_context_model.py`
- Added `--save-predictions` flag saving per-note predictions with **softmax probabilities** for HMM/ensemble post-processing
- Added per-class accuracy breakdown (major vs minor)

#### New Scripts Created
- `evaluate_classical_baseline.py` — K-K/Temperley/A-S ensemble on ATEPP-319 test set (MIREX 0.788)
- `hmm_postprocessing.py` — 24-state HMM with circle-of-fifths transition matrix + Viterbi decoding
- `ensemble_key_detector.py` — Neural+Classical softmax-blended ensemble with alpha grid search
- `bachi_chord_lookup.py` — BACHI chord quality to JI ratio mapping
- `generate_ablation_table.py` — Thesis-ready LaTeX + Markdown ablation table generator
- `colab_phase2_runner.py` — Phase 2 runner (re-eval with softmax, HMM, ensemble, new experiments)

#### Phase 1 Results (6 experiments completed)
| ID | Model | Aug | Weight | MIREX | Minor Acc |
|----|-------|-----|--------|-------|-----------|
| A0 | GRU | No | none | 0.494 | 0.105 |
| A1 | GRU | Yes | none | **0.531** | 0.211 |
| A2 | GRU | No | sqrt | 0.486 | 0.183 |
| A3 | GRU | Yes | sqrt | 0.514 | 0.278 |
| A4 | GRU | Yes | ens | 0.531 | 0.211 |
| A5 | Transformer | Yes | ens | 0.522 | 0.280 |

#### Model Architecture Improvements
- Added **bidirectional GRU** option (`--bidirectional`) — 125K params vs 67K unidirectional
- Added **PCP feature for GRU** (`--gru-pcp`) — ports Transformer's pitch-class histogram to GRU
- Implemented **focal loss** (`--focal-loss`, `--focal-gamma`) — down-weights easy examples, focuses on hard minor-key passages
- All new options save metadata in checkpoints for automatic loading during evaluation

---

## Files Modified (this session)

| File | Changes |
|------|---------|
| `two_stage_server.py` | identification_attempt event, CORS restriction, connect state reset, buffer validation |
| `two_stage_client.js` | Progress display, failed identification feedback, reconnect fix, innerHTML→textContent |
| `js/ui-controller.js` | setInterval memory leak fix with retry limit |
| `index.html` | Script loading order fix (defer), responsive CSS |
| `harmonic_context_model.py` | Bidirectional GRU, PCP feature options |
| `train_harmonic_context_model.py` | --bidirectional, --gru-pcp, --focal-loss flags, FocalLoss class |
| `evaluate_harmonic_context_model.py` | Softmax probability saving, bidirectional checkpoint loading |
| `hmm_postprocessing.py` | Auto-detect and use softmax from prediction files |
| `ensemble_key_detector.py` | Complete rewrite — softmax blending instead of one-hot voting |
| `generate_ablation_table.py` | Extended for Phase 2 experiments (A6-A9) |

## Files Created (this session)

| File | Purpose |
|------|---------|
| `colab_phase2_runner.py` | Phase 2 Colab runner (HMM + ensemble + new experiments) |
| `CHANGELOG.md` | This file |
