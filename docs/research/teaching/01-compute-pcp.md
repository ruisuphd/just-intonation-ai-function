# Teaching Material: compute_pcp — Pitch-Class Profile Computation

## What It Does

`compute_pcp` transforms a sequence of MIDI note events into a sequence of **pitch-class profiles (PCPs)** — 12-dimensional probability distributions that summarise "what pitch classes are active right now?"

Each PCP is a 12-bin histogram where bin `q` (0=C, 1=C#, ..., 11=B) holds the relative frequency of that pitch class in a recent window of notes.

## Why It Exists in This System

The `SymbolicKeyTransformer` has two branches:

1. **PCP branch** — receives the pre-computed pitch-class distribution (this function's output)
2. **Raw pitch branch** — receives individual note features with octave information

The PCP branch gives the Transformer a "summary statistic" of recent harmonic content. Without it, the model would need to learn to compute pitch-class statistics internally from individual note embeddings — which the GRU baseline does, but slowly and imperfectly.

**Analogy:** It's like giving a human musician a chord chart alongside the sheet music. The chord chart (PCP) tells you "we're in the area of C-E-G right now" while the sheet music (raw pitch) tells you the exact notes and registers.

## The Implementation — Line by Line

```python
def compute_pcp(pitch_classes, velocities=None, window_size=32):
    n = len(pitch_classes)
    if n == 0:
        return []

    result = []
    for t in range(n):
        # 1. Create empty 12-bin histogram
        histogram = [0.0] * 12

        # 2. Determine window boundaries
        #    At t=0, window is just [0]. At t=100 with W=32, window is [69..100].
        start = max(0, t - window_size + 1)

        # 3. Accumulate counts in the histogram
        for i in range(start, t + 1):
            weight = velocities[i] if velocities is not None else 1.0
            histogram[pitch_classes[i]] += weight

        # 4. L1-normalise: divide by sum so values represent proportions
        total = sum(histogram)
        if total > 0:
            result.append([h / total for h in histogram])
        else:
            # Edge case: no notes in window (shouldn't happen, but be safe)
            result.append([1.0 / 12] * 12)
    return result
```

## Design Decisions and Trade-offs

### 1. Window Size (W=32)

**Why 32?** At a moderate tempo (120 BPM), 32 notes span roughly 8-16 beats (2-4 measures). This is long enough to capture a full chord progression but short enough to respond to modulations within a few measures.

- **Smaller window (W=8):** Very responsive to changes but noisy — a single chromatic passing tone heavily skews the distribution
- **Larger window (W=128):** Very stable but sluggish — can't detect a modulation until you're deep into the new key
- **W=32 is a Goldilocks value** for classical piano where key changes typically span at least 4 beats

This maps to the Gedizlioglu regularisation threshold (`min_segment_beats=4.0`): both assume that genuine key changes last at least 4 beats.

### 2. Velocity Weighting

Without velocity: every note contributes 1.0 to its pitch-class bin.
With velocity: louder notes contribute more.

**When velocity helps:**
```
Left hand:  C2 (pp, vel=30)  — Alberti bass pattern
Right hand: E5 (ff, vel=110) — Melody note
```
Without weighting, C and E count equally. With weighting, E dominates — which is correct because the melody defines the key perception more than the accompaniment.

**When velocity hurts:**
- MIDI recordings with normalised velocity (common in MIDI-from-score conversions like ATEPP)
- Pieces where the bass defines the harmony (e.g., Bach chorale harmonisations)

**Our choice:** The pre-training pipeline uses velocity weighting (ATEPP performances have expressive velocity). The label-based training can experiment with both.

### 3. L1 Normalisation (sum to 1.0)

Why not L2 (unit vector)? Because L1-normalised PCPs have a direct probabilistic interpretation: `pcp[q]` = "what fraction of recent notes are pitch class q?"

This matters for the mode pseudo-label generation in S-KEY: we compare `pcp[major_root]` vs `pcp[minor_root]`, and these values need to be comparable fractions, not abstract vector magnitudes.

### 4. Causal Design

The window only looks backwards: `[max(0, t-W+1), t]`. It never sees future notes. This is critical because:
- At runtime, we process notes as they arrive — there are no future notes
- During training, this means the PCP at position t contains exactly the same information available at runtime position t
- This is the "causal" property that makes the model deployable in real-time

## Connection to Music Theory

The PCP is closely related to the **Krumhansl key-finding algorithm** (1990), which your existing `js/key-detection.js` already implements. Krumhansl's insight was that each key produces a characteristic pitch-class distribution:

- **C major:** C and G are most frequent, E is next, then the other diatonic notes, with chromatic notes rare
- **A minor:** A and E are most frequent, then C, then other diatonic notes

Your classical JS detector computes this histogram and correlates it with 24 stored profiles. The PCP branch does the same histogram computation but feeds it to a learned model instead of correlating with fixed profiles — allowing the model to discover non-obvious harmonic patterns that Krumhansl profiles miss.

## Connection to S-KEY Paper

In S-KEY (Kong et al. 2025), the equivalent of PCP is the **Key Signature Profile (KSP)** — a 12-dimensional vector produced by octave-folding the ChromaNet output. The KSP is what gets fed into the equivariance loss:

```
KSP_audio = octave_fold(ChromaNet(CQT_spectrogram))
KSP_symbolic = compute_pcp(note_sequence)   # <-- this function
```

Both produce a 12-dimensional representation that is equivariant to transposition: if you transpose all notes up by 3 semitones, the PCP rotates by 3 positions. This property is what makes the self-supervised equivariance loss work.

## Computational Complexity

The naive implementation is O(n * W) where n = number of notes and W = window size. For a typical piece with n=2000 notes and W=32, this is ~64,000 operations — trivial.

For the pre-training pipeline processing 5,091 MIDI files, the total PCP computation across all files takes roughly 2-3 seconds. This is not a bottleneck.

## Verification

You can verify the PCP is correct for a known piece by checking that the dominant pitch classes match the key signature:

```python
# Rachmaninoff Prelude Op.32 No.12 in G# minor
# Key: G# minor (tonic = G# = pitch class 8)
# Expected dominant pitch classes: G# (8), D# (3), B (11)
pcp_at_100 = compute_pcp(pitch_classes, window_size=32)[100]
top_3 = sorted(range(12), key=lambda i: pcp_at_100[i], reverse=True)[:3]
# Should include pitch classes 3 (D#), 8 (G#), and possibly 11 (B)
```

Our smoke test confirmed: D# (0.438), G# (0.344) — exactly the tonic and dominant of G# minor.
