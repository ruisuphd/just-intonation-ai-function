# Teaching Material: SymbolicKeyTransformer — Two-Branch Causal Architecture

## Architecture Overview

```
  PCP (12-dim)                    Raw Features (80-dim)
       |                                  |
  Linear(12, 128)               Linear(80, 128)
       |                                  |
       v                                  v
   branch1 (B,T,128)            branch2 (B,T,128)
       |                                  |
       +------ concat (B,T,256) ----------+
                      |
              Linear(256, 128)
                      |
            + pos_embedding(T, 128)
                      |
              Dropout(0.1)
                      |
        TransformerEncoder(2 layers)
           (causal masked)
                      |
            +----+----+----+
            |    |         |
         key  mode       ksp
        (24) (2)        (12)
```

## Why Each Component Exists

### Branch 1: PCP Projection

```python
self.pcp_projection = nn.Linear(12, d_model)  # 12 -> 128
```

The PCP is a 12-dimensional probability distribution over pitch classes. A simple linear projection maps this to the model's working dimension (128). This is analogous to ChromaNet's octave-folding operator `g` in STONE/S-KEY — both produce a 12-dimensional summary that is equivariant to transposition.

**Why not use an embedding?** Because PCP values are continuous floats (0.0 to 1.0), not discrete categories. Embeddings only work for integer indices.

### Branch 2: Raw Feature Projection

```python
# Same embeddings as GRU
self.pitch_embedding = nn.Embedding(12, 32)   # pitch class -> 32 dims
self.register_embedding = nn.Embedding(11, 8)  # octave -> 8 dims
self.delta_embedding = nn.Embedding(14, 8)     # IOI bucket -> 8 dims
self.duration_embedding = nn.Embedding(14, 8)  # duration bucket -> 8 dims
self.velocity_embedding = nn.Embedding(17, 8)  # velocity bucket -> 8 dims
self.active_projection = nn.Linear(12, 16)     # active note mask -> 16 dims
# Total: 32 + 8 + 8 + 8 + 8 + 16 = 80

self.raw_projection = nn.Linear(80, d_model)   # 80 -> 128
```

These are **identical** to the GRU's embeddings. The register embedding is what gives this branch its key advantage: it knows that a C2 (bass) differs from a C5 (soprano). The PCP branch loses this distinction by design.

### Fusion Layer

```python
self.fusion = nn.Linear(2 * d_model, d_model)  # 256 -> 128
```

Concatenation followed by linear projection. This is the simplest fusion strategy. Alternatives considered:

- **Additive fusion** (`branch1 + branch2`): forces both branches to share the same representational space — too constrained
- **Attention-based fusion**: too many parameters for the data size
- **Concatenation + MLP**: only marginally better than single linear, not worth the complexity

### Causal Mask

```python
causal_mask = torch.triu(torch.ones(T, T), diagonal=1).bool()
```

This creates an upper-triangular boolean matrix where `True` means "mask out":

```
F T T T T    (position 0 can only see position 0)
F F T T T    (position 1 can see 0, 1)
F F F T T    (position 2 can see 0, 1, 2)
F F F F T    (position 3 can see 0, 1, 2, 3)
F F F F F    (position 4 can see everything up to 4)
```

**Why causal?** At runtime, when a pianist plays note `t`, we don't know what note `t+1` will be. The model must make predictions using only past and present notes. The causal mask enforces this during training, so the model learns to predict without future information.

### Learnable Positional Encoding

```python
self.pos_embedding = nn.Embedding(max_seq_len, d_model)
```

Unlike the original Transformer (Vaswani et al. 2017) which uses fixed sinusoidal positions, we use learnable position embeddings. Reasons:

1. **Sequence length is bounded** (max 512 notes) — learnable embeddings are tractable
2. **Position semantics differ from language** — in music, position 100 doesn't have a fixed meaning across pieces. What matters is relative distance, which attention can learn from the embeddings
3. **Simpler implementation** — one line vs. a custom sinusoidal function

### Three Output Heads

```python
self.key_head = nn.Linear(d_model, 24)   # supervised target
self.mode_head = nn.Linear(d_model, 2)    # self-supervised target
self.ksp_head = nn.Linear(d_model, 12)    # equivariance loss target
```

**key_head** is the final supervised target: predict one of 24 keys (C major, C minor, ..., B minor). Used during fine-tuning and at runtime.

**mode_head** distinguishes major vs minor. Used only during self-supervised pre-training with pseudo-labels from PCP energy comparison (S-KEY's Equation 5). At inference time, the key_head already encodes mode information (keys 0-11 are major, 12-23 are minor).

**ksp_head** outputs a 12-dimensional vector that, after softmax, represents the model's estimated Key Signature Profile. This is the target of the equivariance loss: if you transpose the input by `c` semitones, the KSP should rotate by `c` positions. Used only during pre-training.

## Parameter Count Breakdown

| Component | Parameters | Notes |
|-----------|-----------|-------|
| PCP projection | 12 * 128 + 128 = 1,664 | Linear(12, 128) with bias |
| Pitch embedding | 12 * 32 = 384 | No bias (Embedding) |
| Register embedding | 11 * 8 = 88 | |
| Delta embedding | 14 * 8 = 112 | |
| Duration embedding | 14 * 8 = 112 | |
| Velocity embedding | 17 * 8 = 136 | |
| Active projection | 12 * 16 + 16 = 208 | Linear(12, 16) |
| Raw projection | 80 * 128 + 128 = 10,368 | Linear(80, 128) |
| Fusion | 256 * 128 + 128 = 32,896 | Linear(256, 128) |
| Positional | 512 * 128 = 65,536 | Embedding(512, 128) |
| TransformerEncoder (2 layers) | ~266,000 | 4-head attention + FFN |
| Key head | 128 * 24 + 24 = 3,096 | |
| Mode head | 128 * 2 + 2 = 258 | |
| KSP head | 128 * 12 + 12 = 1,548 | |
| **Total** | **~381K** | |

This is ~4x the GRU (which has ~28K params) but still tiny by modern standards. A single Transformer layer has more parameters than the entire GRU because attention requires Q, K, V projection matrices (each 128x128) plus the feedforward network (128->256->128).

## Why Transformer Over GRU for This Task

The GRU processes notes sequentially: it sees note 1, updates hidden state, sees note 2, updates, etc. By note 100, information from note 1 has been compressed through 99 sequential updates. The Transformer with attention can directly compare note 100 to note 1 in a single operation.

For key detection, this matters because:

1. **Key signatures often span hundreds of notes.** A Transformer can attend to the first key-establishing chord directly, even from note 200.
2. **Tonicizations are local.** A V/V chord at note 50 affects notes 48-52 but not note 100. Attention can learn to weight recent context appropriately.
3. **The causal mask preserves sequential order** while allowing efficient parallel computation during training.

The trade-off: Transformers use O(T^2) memory for the attention matrix, while GRUs use O(T) memory. For T=256 (our window size), the attention matrix is 256 * 256 = 65K entries per head, or 260K entries for 4 heads — negligible on any modern GPU or even CPU.

## Connection to S-KEY and OctaveNet

**From S-KEY:** The three output heads mirror S-KEY's training structure:
- ChromaNet -> KSP -> CPSD loss (our ksp_head -> equivariance loss)
- ChromaNet -> mode output -> BCE loss (our mode_head -> pseudo-label loss)

**From OctaveNet:** The two-branch design mirrors OctaveNet's architecture:
- Octave-folded branch (our PCP branch)
- Sequential branch with register info (our raw pitch branch)

**Our novel combination:** No prior work combines S-KEY's self-supervised objective with OctaveNet's two-branch design in the symbolic domain. This is the thesis contribution.
