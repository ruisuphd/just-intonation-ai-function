# Teaching Material: Self-Supervised Pre-Training (S-KEY-Symbolic)

## The Core Idea

**Problem:** You have 5,091 MIDI performances but only 319 have key labels. Can you use the unlabeled 4,772 to improve key detection?

**S-KEY's answer:** Yes -- exploit a physical invariant of music. If you transpose a piece up by 3 semitones, the key also shifts up by 3 semitones. Train a model to predict *how much* something was transposed, and it must internally learn to represent key.

This is self-supervised learning: the "labels" come from transformations you apply to the data, not from human annotations.

## The Three Loss Components

### 1. Equivariance Loss (L_equiv) -- "Predict the transposition"

**What it does:** Given the model's Key Signature Profile (KSP) for segment A and transposed segment B, checks if the KSP shifted by exactly `c` semitones.

**How it works -- the circle of fifths trick:**

Instead of comparing KSPs directly (which would be a 12-way alignment problem), S-KEY uses the Discrete Fourier Transform at a special frequency: omega=7, the "circle of fifths" frequency.

Why omega=7? In the DFT of a 12-element vector, omega=7 corresponds to the circle of fifths -- the most musically meaningful ordering of pitch classes (C, G, D, A, E, B, F#, C#, Ab, Eb, Bb, F). Keys that are close on the circle of fifths sound similar (C major and G major share 6 of 7 notes).

**The math:**
```
DFT at omega=7:  F(KSP) = sum over q: KSP[q] * exp(-2*pi*j*7*q/12)
```

A transposition by `c` semitones becomes a phase rotation in the DFT:
```
F(transpose(KSP, c)) = F(KSP) * exp(-2*pi*j*7*c/12)
```

So we compute F(KSP_A) and F(KSP_B), compute their cross-power spectral density (CPSD), and check if it matches the expected phase rotation for transposition `c`.

**Intuition:** It's like checking if two clock hands moved by the right angle. If A points to "C major" and B should point to "Eb major" (3 semitones up), the CPSD should show a specific angle difference.

### 2. Mode Loss (L_mode) -- "Is this major or minor?"

**The problem S-KEY solves that STONE couldn't:** C major and A minor have the same 7 pitch classes (C, D, E, F, G, A, B). STONE's equivariance loss treats them identically because transposing both by the same amount produces the same KSP shift.

**S-KEY's solution:** Use a simple heuristic -- whichever pitch class has more energy (the major root or the relative minor root) determines the pseudo-label. In C major, C is usually more frequent than A. In A minor, A is usually more frequent than C.

```
major_root = argmax(pcp)              # Most common pitch class
minor_root = (major_root - 3) % 12    # 3 semitones below

if pcp[major_root] > pcp[minor_root]:
    label = [1, 0]   # "major"
else:
    label = [0, 1]   # "minor"
```

**Why this works:** In tonal music, the tonic pitch class is almost always the most frequent. If the most frequent pitch class has more energy than the pitch class 3 semitones below, the piece is likely in the major key rooted at that pitch class, not the relative minor.

**Why it's called "pseudo-labels":** These labels are noisy -- they can be wrong for pieces with ambiguous tonality (e.g., some Debussy preludes). But averaged over 5,091 performances, the signal is strong enough to train a useful mode discriminator.

### 3. Batch Balance Loss (L_batch) -- "Don't collapse"

```
L_batch = (mean(mode_probs[:, 0]) - 0.5) ^ 2
```

This penalises the model if it predicts "major" for more (or fewer) than 50% of the batch. Without this, the model might collapse to always predicting "major" (since ~60% of classical piano music is in major keys).

**Weight: 15.0** -- this is high because batch balance is a necessary condition for the mode pseudo-labels to have meaning. If the model always predicts major, the pseudo-label loss is meaningless.

## The Combined Loss

```
total = 1.0 * L_equiv + 1.5 * L_mode + 15.0 * L_batch
```

These weights come directly from S-KEY (Equation 8). The mode loss weight (1.5) is higher than the equivariance loss (1.0) because mode discrimination is the harder task -- the equivariance objective is already partially solved by the input representation (PCP is naturally equivariant to transposition).

## Data Pipeline

### Transposition Pairs

For each MIDI file:
1. Split the piece roughly in half
2. Sample a 256-note window from each half (non-overlapping to avoid trivial matching)
3. Transpose window B by `c` semitones (randomly sampled from 1-11)
4. Encode both windows into model input format

**Why non-overlapping windows?** If windows A and B were from the same section, the model could solve the equivariance task by memorising local patterns rather than learning key representation. Forcing A and B to come from different sections means the model must extract a key-level summary, not note-level details.

### MIDI Cache

Loading 5,091 MIDI files with pretty_midi takes ~20-40 minutes. We cache all note events as JSON-lines (one JSON object per line) so subsequent runs load in seconds.

**Why JSON-lines instead of binary serialization?** JSON is human-readable and auditable -- you can inspect the cache with `head -1 research_data/atepp_midi_cache.jsonl | python -m json.tool`. This aligns with the project's research documentation standard.

## Training Dynamics -- What to Watch

| Metric | Healthy Range | Problem Indicator |
|--------|--------------|-------------------|
| L_equiv | 0.1 - 0.5 | > 1.0 after epoch 5 = model not learning transposition |
| L_mode | 0.4 - 0.7 | < 0.3 = potentially overfitting pseudo-labels |
| L_batch | 0.001 - 0.05 | > 0.1 = model collapsing to one mode |
| major_frac | 0.40 - 0.60 | < 0.3 or > 0.7 = mode collapse despite L_batch |

## Connection to Your Thesis

The novelty claim for Paper 2 is: **first self-supervised local key estimator designed for symbolic MIDI streams, evaluated in real-time browser context on struck-string piano repertoire.**

The pre-training step is where this novelty lives. The fine-tuning (Phase 4) uses the same labeled data as the existing GRU -- what changes is the model's starting point. A pre-trained model has already learned:
- What a "key" looks like in terms of pitch-class distributions
- How transposition affects key representation
- Whether a passage is major or minor

These are precisely the three things the GRU baseline struggles with at 43.1% accuracy.
