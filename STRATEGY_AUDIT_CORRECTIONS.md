# Research Strategy Audit Corrections

**Audit date:** 3 April 2026
**Document audited:** `RESEARCH_STRATEGY_3_CONTRIBUTIONS.md` (generated 2 April 2026)
**Auditor:** Automated code-level verification against codebase state at commit `6aa4dea`

---

## Summary

Five factual claims in the research strategy were verified against the codebase. Three claims are confirmed correct; two claims contain errors; one claim is mis-characterised. All corrections are documented below with exact line numbers and code evidence.

---

## Correction 1: Line Number Error (Minor)

**Strategy claim (Section 1.1):**
> `musicxml_score_parser.py` (line 107) defaults `current_mode` to `'major'`

**Actual finding:**
The default is at **line 106**, not 107. Line 107 is blank.

```python
# musicxml_score_parser.py
105:    current_fifths = 0
106:    current_mode = 'major'    # <-- HERE (not line 107)
107:
108:    for measure_index, measure in enumerate(part.findall(...)):
```

Additionally, line 124 contains a second default that reinforces the major bias:
```python
124:    mode = _get_text(key_node, namespace, 'mode', 'major') or 'major'
```

This double-default means that even when a `<key>` element IS present in the MusicXML but the `<mode>` sub-element is absent, the parser forces `'major'`.

**Impact:** Minor line-number correction. The described behaviour is accurate.

---

## Correction 2: Equivariance Loss Complexity (Significant)

**Strategy claim (Section 2.3, Step 2, "Known performance issue"):**
> The current `symbolic_equivariance_loss()` [...] computes per-item transposition in a Python loop over the batch, resulting in O(B^2) complexity.

**Actual finding:**
The loss function itself (`pretrain_symbolic_key.py`, lines 213-259) is **fully vectorised** using torch tensor operations on `(batch,)` shaped tensors. It is O(B), not O(B^2).

The training loop (lines 518-530) does iterate per-item:
```python
518:    for idx in range(batch_size_actual):
519:        out_A_i = {k: v[idx:idx+1] for k, v in out_A.items()}
520:        out_B_i = {k: v[idx:idx+1] for k, v in out_B.items()}
521:        pcp_A_i = batch_A['pcp'][idx:idx+1]
522:        c_i = c_values[idx]
523:        loss_i, det_i = self_supervised_loss(
524:            out_A_i, out_B_i,
525:            pcp_A=pcp_A_i,
526:            transposition_c=c_i,
...
534:    loss = sum(item_losses) / len(item_losses)
```

This loop is **O(B) sequential calls** (one iteration per batch item), not O(B^2). Each iteration processes one item in O(1) tensor operations. The total work is O(B), but the sequential execution prevents GPU parallelism.

**Correct characterisation:** "The per-item loop at lines 518-534 prevents batched GPU computation because each item has a different transposition value `c_i`. Vectorising `c_values` as a `(B,)` tensor and broadcasting through the loss function would eliminate the loop and enable full GPU parallelism."

**Recommendation to vectorise remains valid** despite the incorrect complexity claim. Expected speedup: proportional to batch size (up to ~128x for batch_size=128).

---

## Correction 3: Ablation Config Table Error (Significant)

**Strategy claim (Section 2.3, Step 2, ablation table):**

| Config | lambda_equiv | lambda_mode | lambda_batch |
|--------|-------------|-------------|-------------|
| equiv-only | 1.0 | 0.0 | **0.0** |

**Actual code (`pretrain_symbolic_key.py`, line 590):**
```python
590:    {'lambda_equiv': 1.0, 'lambda_mode': 0.0, 'lambda_batch': 15.0, 'tag': 'equiv-only'},
```

The `lambda_batch` value is **15.0**, not 0.0.

**Why the code is correct:** Batch balance regularisation (`lambda_batch`) prevents mode collapse in the KSP (key signature profile) output by encouraging approximately equal predictions of major vs minor. This is beneficial even when the mode pseudo-label loss is ablated (`lambda_mode=0.0`), because without batch balance the KSP output can degenerate to a single mode. The equiv-only config isolates the equivariance loss contribution while still maintaining healthy KSP output distribution.

**All other 5 configs verified correct:**
- skey-default: (1.0, 1.5, 15.0) -- line 588 matches
- mode-only: (0.0, 1.5, 15.0) -- line 592 matches
- high-mode: (1.0, 3.0, 15.0) -- line 594 matches
- low-batch: (1.0, 1.5, 5.0) -- line 596 matches
- equal: (1.0, 1.0, 1.0) -- line 598 matches

---

## Correction 4: CommaDriftTracker Characterisation (Moderate)

**Strategy claim (Section 3.2, Gap 3):**
> In `js/tuning-core.js`, the `CommaDriftTracker` accumulates drift per pitch class on every note event. This is conceptually incorrect [...]

**Actual finding:**
The implementation (`js/tuning-core.js`, lines 168-222) follows a per-pitch-class accumulation approach with threshold reset:

```javascript
183:    applyWithDriftCorrection(midiNote, keyName) {
184:        const pc = midiNote % 12;
185:        const rawCents = calculateJICentsForNote(midiNote, keyName);
187:        this.cumulativeDrift[pc] += rawCents;
192:        if (Math.abs(this.cumulativeDrift[pc]) >= this.thresholdCents) {
194:            this.cumulativeDrift[pc] = 0.0;
```

This is a **valid approach**, referenced by Stange et al. (Computer Music Journal 42(3), 2018, arXiv:1706.04338). The per-PC method tracks how far each pitch class has drifted from its 12-TET reference, which is a reasonable proxy for audible comma accumulation.

**Correct characterisation:** The interval-sequential tracking proposed in the strategy (monitoring cumulative deviation along the actual sequence of harmonic intervals) would be **more musically accurate** because it models the true source of comma drift: chains of pure intervals where each step accumulates ~2 cents. However, the current per-PC approach is not "conceptually incorrect" -- it is a valid simplification that catches the most common drift scenario (repeated visits to pitch classes that consistently deviate in the same direction).

**Recommendation:** Frame as an **enhancement** ("improving comma drift tracking from per-PC to interval-sequential for greater musical accuracy") rather than a **bug fix**.

---

## Correction 5: Major-Only Labels (Confirmed)

**Strategy claim (Section 1.1):**
> All 803,877 notes across 319 unique compositions in your current label files are labeled as major keys.

**Verified by direct data inspection:**
```
Total label files: 319
Total notes: 803,877
Major notes: 803,877  (100%)
Minor notes: 0        (0%)
Key change mode distribution: {'major': 683, 'none': 6}
```

Both confusion matrices (`transformer_eval.json`, `harmonic_context_eval.json`) have rows 12-23 (all 12 minor keys) entirely zeros -- confirmed.

**This claim is correct and remains the single most critical issue to fix.**

---

## Verified Claims (No Corrections Needed)

| Claim | Status |
|-------|--------|
| GRU accuracy 0.4558 / MIREX 0.6050 | Exact match in `harmonic_context_eval.json` |
| Transformer accuracy 0.4545 / MIREX 0.6082 | Exact match in `transformer_eval.json` |
| 6 ablation configs exist | All 6 present at lines 586-599 (with Correction 3 above) |
| `build_roman_numeral_labels.py` has NotImplementedError stubs | Confirmed at lines 192 and 220 |
| No DCML or When-in-Rome data in project | Confirmed (only ATEPP data present) |
| S-KEY paper reference (Kong et al., ICASSP 2025, arXiv:2501.12907) | Citation appears accurate |
