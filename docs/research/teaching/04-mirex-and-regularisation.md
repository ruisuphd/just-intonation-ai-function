# Teaching Material: MIREX Weighted Score and Gedizlioglu Regularisation

## MIREX Weighted Score

### Why Raw Accuracy Is Misleading for Key Detection

Predicting G major when the true key is C major is a **much smaller error** than predicting F# minor. In music theory:
- G major is the dominant of C major (they share 6 of 7 notes)
- F# minor is harmonically distant from C major

But raw accuracy treats both errors equally (both score 0.0). The MIREX weighted metric captures musical distance:

| Relationship | Score | Example |
|-------------|-------|---------|
| Exact match | 1.0 | Predicted C major, true C major |
| Fifth | 0.5 | Predicted G major, true C major (G is the dominant of C) |
| Relative key | 0.3 | Predicted A minor, true C major (Am is the relative minor of C) |
| Parallel key | 0.2 | Predicted C minor, true C major (same root, different mode) |
| Other | 0.0 | Predicted F# minor, true C major |

### The Implementation

```python
def mirex_weighted_score(predicted_idx, true_idx):
    pred_pc = predicted_idx % 12     # pitch class (0-11)
    true_pc = true_idx % 12
    pred_minor = predicted_idx >= 12  # keys 12-23 are minor
    true_minor = true_idx >= 12
    pc_diff = (pred_pc - true_pc) % 12
```

**Key insight:** The modular arithmetic `(pred_pc - true_pc) % 12` gives the interval in semitones *upward* from true to predicted. A perfect fifth is 7 semitones up or 5 semitones down, so we check for both `pc_diff in (5, 7)`.

**Relative key check:** C major's relative minor is A minor. A is 9 semitones above C (or 3 below). So we check `pc_diff in (3, 9)`.

### Your GRU Baseline Results

| Metric | Value | Interpretation |
|--------|-------|---------------|
| Raw accuracy | 45.6% | Less than half of predictions are exactly right |
| MIREX weighted | 60.5% | But most "errors" are musically close |

The 15-point gap tells you that the GRU is already learning tonal structure -- it just struggles with fine distinctions (major vs relative minor, tonic vs dominant).

## Gedizlioglu Regularisation

### The Problem: Tonicization Flicker

When a piece in C major briefly visits the dominant key (G major) via a V/V chord:

```
Measure 1-4: C major (I - IV - V - I)
Measure 5:   G major dominant (V/V chord)  <-- tonicization
Measure 6-8: C major (I - vi - IV - V - I)
```

A per-note key detector might output:
```
[C, C, C, C, G, G, C, C, C, C]
```

But the G major segment is only 1 measure -- it's a *tonicization* (brief harmonic detour), not a genuine *modulation* (lasting key change). For JI tuning, treating this as a modulation would cause an audible glitch as the tuning system briefly resets all ratios.

### The Solution

The regularisation algorithm (from Gedizlioglu & Erol, Psychology of Music 2024):

1. Walk through the prediction sequence and identify "runs" of consecutive identical keys
2. For each run, measure its duration (in beats or note count)
3. If a run is shorter than a threshold (4 beats or 8 notes), absorb it into the preceding run

```
Before: [C, C, C, C, G, G, C, C, C, C]
After:  [C, C, C, C, C, C, C, C, C, C]   (G segment < 4 beats, absorbed)
```

### Why 4 Beats?

This is a musicologically motivated threshold. In common-practice harmony:
- Tonicizations typically last 1-3 beats (a single secondary dominant chord)
- Genuine modulations establish the new key over at least 4 beats (usually a full cadence: V-I in the new key)

The 4-beat threshold catches ~90% of tonicizations while preserving genuine modulations. It's a tunable hyperparameter -- you can evaluate different values on your validation set.

### Runtime vs Offline Behavior

**Offline** (label generation, evaluation): the full sequence is available, so regularisation uses beat positions for precise duration measurement.

**Online** (real-time runtime): notes arrive one at a time. The runtime maintains a sliding buffer of recent key predictions (last 32) and applies the note-count fallback (min 8 notes). This means a tonicization might be briefly followed before being regularised away when enough subsequent notes confirm the original key.

This creates a small perceptual effect: the tuning briefly shifts during a tonicization, then snaps back. For JI tuning of piano, this is actually *desirable* -- tonicizations create harmonic tension, and a brief tuning shift enhances this effect before resolving.
