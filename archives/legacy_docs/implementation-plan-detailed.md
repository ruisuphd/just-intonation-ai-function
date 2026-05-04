# Detailed Implementation Plan — AI Contributions
### Algorithm Pseudocode, Architecture Specifications, and Codebase Integration Guide

*Companion to: phd-ai-roadmap-2026.md and research-bibliography-detailed.md*
*Last updated: March 2026*

---

## Table of Contents

1. Contribution A: S-KEY-Symbolic — Self-Supervised Local Key Detection
2. Contribution B: Contrastive Hybrid Piece Identification
3. Contribution C: Roman Numeral Labels for Chord-Aware Tuning
4. Infrastructure: Score Following Upgrade
5. MTS-MPE Refinements

---

## 1. Contribution A: S-KEY-Symbolic — Self-Supervised Local Key Detection from MIDI Streams

### 1.1 Conceptual Overview

The core idea is to port the S-KEY self-supervised training methodology from the audio domain (CQT spectrograms) to the symbolic domain (MIDI note-event sequences). This requires three adaptations:

1. **Replacing the CQT input** with a symbolic note-event encoding
2. **Replacing the ChromaNet CNN** with a sequence model that respects causality
3. **Reformulating the CPSD loss** in terms of pitch-class histograms rather than spectral coefficients

The self-supervised objective has two parts:
- **Equivariance loss**: the model must produce consistent key predictions when the same piece is transposed
- **Mode disambiguation loss**: the model must distinguish major from minor using pseudo-labels derived from chroma energy comparison

### 1.2 Architecture: Two-Branch Symbolic Transformer

This architecture combines the OctaveNet two-branch idea with a lightweight causal Transformer.

**Branch 1 — Pitch-Class Profile (PCP) Branch:**
Input: 12-bin pitch-class histogram computed over a sliding window of W notes (default W = 32).
For each note event at position t, compute:
```
pcp[t][q] = Σ_{i=max(0,t-W+1)}^{t} velocity_weight[i] * 1{pitch[i] mod 12 == q}
```
Normalise: pcp[t] = pcp[t] / (||pcp[t]||₁ + ε)

This 12-dimensional vector is projected to d_model dimensions via a linear layer.

**Branch 2 — Raw Pitch Sequence Branch:**
Input: per-note features from the existing `encode_live_events` function:
- pitch_class embedding (12 → 32 dims) — reuse existing `self.pitch_embedding`
- register embedding (11 → 8 dims) — reuse existing `self.register_embedding`
- IOI bucket embedding (14 → 8 dims) — reuse existing `self.delta_embedding`
- duration bucket embedding (14 → 8 dims) — reuse existing `self.duration_embedding`
- velocity bucket embedding (17 → 8 dims) — reuse existing `self.velocity_embedding`
- active note mask projection (12 → 16 dims) — reuse existing `self.active_projection`
- Total: 80 dims, projected to d_model dims via a linear layer

**Fusion:**
The two branches are concatenated at each timestep and projected:
```
fused[t] = Linear(concat(branch1_out[t], branch2_out[t]))  # 2*d_model → d_model
```

**Causal Transformer Encoder:**
- d_model = 128
- n_heads = 4
- n_layers = 2
- feedforward_dim = 256
- dropout = 0.1
- Causal attention mask (lower triangular) to ensure the model cannot see future notes
- Positional encoding: learnable (not sinusoidal), max length 512

**Output Heads:**
- Key head: Linear(d_model → 24) for 24 key classes (12 major + 12 minor)
- Mode head: Linear(d_model → 2) for major/minor binary classification (used during self-supervised pre-training)

### 1.3 Pseudocode: Model Class

```python
class SymbolicKeyTransformer(nn.Module):
    def __init__(self, d_model=128, n_heads=4, n_layers=2, ff_dim=256, dropout=0.1):
        super().__init__()

        # Branch 1: PCP (pitch-class profile)
        self.pcp_projection = nn.Linear(12, d_model)

        # Branch 2: Raw pitch features (reuse existing embeddings)
        self.pitch_embedding = nn.Embedding(12, 32)
        self.register_embedding = nn.Embedding(11, 8)
        self.delta_embedding = nn.Embedding(14, 8)
        self.duration_embedding = nn.Embedding(14, 8)
        self.velocity_embedding = nn.Embedding(17, 8)
        self.active_projection = nn.Linear(12, 16)
        raw_feature_size = 32 + 8 + 8 + 8 + 8 + 16  # = 80
        self.raw_projection = nn.Linear(raw_feature_size, d_model)

        # Fusion
        self.fusion = nn.Linear(2 * d_model, d_model)

        # Positional encoding
        self.pos_embedding = nn.Embedding(512, d_model)

        # Causal Transformer
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=ff_dim,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)

        # Output heads
        self.key_head = nn.Linear(d_model, 24)       # 12 major + 12 minor
        self.mode_head = nn.Linear(d_model, 2)        # major vs minor

        # Octave-folded KSP head (12-dim, for equivariance loss)
        self.ksp_head = nn.Linear(d_model, 12)

    def forward(self, pcp, raw_features, lengths=None):
        """
        pcp: (batch, seq_len, 12) — pitch-class profiles
        raw_features: dict of tensors — same format as existing HarmonicContextGRU
        """
        B, T = pcp.shape[0], pcp.shape[1]

        # Branch 1
        branch1 = self.pcp_projection(pcp)  # (B, T, d_model)

        # Branch 2
        raw = torch.cat([
            self.pitch_embedding(raw_features['pitch_class']),
            self.register_embedding(raw_features['register']),
            self.delta_embedding(raw_features['delta_bucket']),
            self.duration_embedding(raw_features['duration_bucket']),
            self.velocity_embedding(raw_features['velocity_bucket']),
            self.active_projection(raw_features['active_mask']),
        ], dim=-1)
        branch2 = self.raw_projection(raw)  # (B, T, d_model)

        # Fusion
        fused = self.fusion(torch.cat([branch1, branch2], dim=-1))  # (B, T, d_model)

        # Add positional encoding
        positions = torch.arange(T, device=fused.device).unsqueeze(0).expand(B, T)
        fused = fused + self.pos_embedding(positions)

        # Causal mask
        causal_mask = torch.triu(torch.ones(T, T, device=fused.device), diagonal=1).bool()

        # Transformer
        encoded = self.transformer(fused, mask=causal_mask)  # (B, T, d_model)

        return {
            'key_logits': self.key_head(encoded),     # (B, T, 24)
            'mode_logits': self.mode_head(encoded),    # (B, T, 2)
            'ksp_logits': self.ksp_head(encoded),      # (B, T, 12)
        }
```

**Parameter Count Estimate:**
- Embeddings: ~12 × 32 + 11 × 8 + 14 × 8 + 14 × 8 + 17 × 8 + 12 × 16 = ~1,024
- Projections: 12 × 128 + 80 × 128 + 256 × 128 = ~44,544
- Transformer layers (2): 2 × (4 × 128² + 128 × 256 × 2 + 128 × 2) ≈ 2 × 196K = ~393K
- Output heads: 128 × 24 + 128 × 2 + 128 × 12 = ~4,864
- Positional: 512 × 128 = 65,536
- **Total: ~509K parameters** (0.5M — well within CPU real-time budget)

### 1.4 Pseudocode: Self-Supervised Pre-Training

**Step 1 — Transposition Pair Construction:**
```python
def create_transposition_pair(midi_notes, c):
    """
    Transpose all notes by c semitones.
    c sampled uniformly from [1, 11] (avoid c=0 trivial case).
    """
    transposed = []
    for note in midi_notes:
        new_note = dict(note)
        new_note['pitch'] = note['pitch'] + c
        # Clip to valid MIDI range [21, 108] for piano
        if 21 <= new_note['pitch'] <= 108:
            transposed.append(new_note)
    return transposed
```

**Step 2 — Symbolic KSP and Equivariance Loss:**

In S-KEY (audio), the CPSD loss compares DFTs of key signature profiles across transposed segments via a circle-of-fifths distance. For symbolic input, the equivalent is:

```python
def symbolic_equivariance_loss(ksp_A, ksp_B, transposition_c):
    """
    ksp_A: (batch, 12) — softmax of ksp_logits for segment A
    ksp_B: (batch, 12) — softmax of ksp_logits for segment B (transposed by c)
    transposition_c: int — number of semitones B was transposed relative to A

    The loss enforces: if B = transpose(A, c), then
    argmax(ksp_B) should equal (argmax(ksp_A) + c) mod 12

    Implemented as circular cross-correlation on the circle of fifths.
    """
    # DFT at circle-of-fifths frequency (omega=7)
    omega = 7
    q = torch.arange(12, device=ksp_A.device).float()

    # DFT coefficients
    basis = torch.exp(-2j * math.pi * omega * q / 12)  # complex
    fft_A = (ksp_A * basis.real).sum(dim=-1) + 1j * (ksp_A * basis.imag).sum(dim=-1)
    fft_B = (ksp_B * basis.real).sum(dim=-1) + 1j * (ksp_B * basis.imag).sum(dim=-1)

    # Cross-power spectral density
    cpsd = fft_A * fft_B.conj()

    # Target phase rotation for transposition c
    target = torch.exp(torch.tensor(-2j * math.pi * omega * transposition_c / 12))

    # Distance
    loss = 0.5 * torch.abs(target - cpsd) ** 2
    return loss.mean()
```

**Step 3 — Major/Minor Pseudo-Label Generation:**

```python
def generate_mode_pseudo_labels(pcp_histogram):
    """
    pcp_histogram: (batch, 12) — normalised pitch-class histogram

    For each sample, find the pitch class with maximum energy.
    Compare energy at that pitch class (major root) vs 3 semitones below (relative minor root).
    If major root energy > minor root energy → label [1, 0] (major)
    Otherwise → label [0, 1] (minor)

    This is the symbolic equivalent of S-KEY's Equation 5.
    """
    major_root_idx = pcp_histogram.argmax(dim=-1)  # (batch,)
    minor_root_idx = (major_root_idx - 3) % 12     # relative minor is 3 semitones below

    batch_idx = torch.arange(pcp_histogram.size(0))
    major_energy = pcp_histogram[batch_idx, major_root_idx]
    minor_energy = pcp_histogram[batch_idx, minor_root_idx]

    # Pseudo-labels: [1,0] for major, [0,1] for minor
    labels = torch.zeros(pcp_histogram.size(0), 2)
    labels[major_energy > minor_energy, 0] = 1.0  # major
    labels[major_energy <= minor_energy, 1] = 1.0  # minor

    return labels
```

**Step 4 — Combined Self-Supervised Loss:**
```python
def self_supervised_loss(model_output_A, model_output_B, pcp_A, transposition_c):
    """
    Combined loss following S-KEY Equation 8.
    λ_equiv = 1.0, λ_mode = 1.5, λ_batch = 15.0
    """
    ksp_A = F.softmax(model_output_A['ksp_logits'][:, -1, :], dim=-1)  # last step
    ksp_B = F.softmax(model_output_B['ksp_logits'][:, -1, :], dim=-1)

    # 1. Equivariance loss
    L_equiv = symbolic_equivariance_loss(ksp_A, ksp_B, transposition_c)

    # 2. Mode pseudo-label loss
    pseudo_labels = generate_mode_pseudo_labels(pcp_A[:, -1, :])
    mode_probs_A = F.softmax(model_output_A['mode_logits'][:, -1, :], dim=-1)
    mode_probs_B = F.softmax(model_output_B['mode_logits'][:, -1, :], dim=-1)
    L_mode = F.binary_cross_entropy(mode_probs_A, pseudo_labels) + \
             F.binary_cross_entropy(mode_probs_B, pseudo_labels)

    # 3. Batch balance regularisation
    # Penalise deviation from 50/50 major/minor split in the batch
    batch_major_frac = mode_probs_A[:, 0].mean()
    L_batch = (batch_major_frac - 0.5) ** 2

    return 1.0 * L_equiv + 1.5 * L_mode + 15.0 * L_batch
```

**Step 5 — Pre-Training Loop:**
```python
def pretrain_epoch(model, atepp_midi_files, optimizer):
    model.train()
    for midi_path in atepp_midi_files:
        notes = load_midi_notes(midi_path)

        # Sample two non-overlapping windows from the piece
        window_A = sample_window(notes, size=256)
        window_B = sample_window(notes, size=256)

        # Sample transposition
        c = random.randint(1, 11)
        window_B_transposed = transpose_notes(window_B, c)

        # Encode both windows
        pcp_A, raw_A = encode_symbolic(window_A)
        pcp_B, raw_B = encode_symbolic(window_B_transposed)

        # Forward pass
        out_A = model(pcp_A, raw_A)
        out_B = model(pcp_B, raw_B)

        # Self-supervised loss
        loss = self_supervised_loss(out_A, out_B, pcp_A, c)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
```

### 1.5 Supervised Fine-Tuning

After pre-training, fine-tune on the 319 score-key label JSONs using the same procedure as `train_harmonic_context_model.py`:

```python
def finetune_epoch(model, labeled_loader, optimizer):
    model.train()
    loss_fn = nn.CrossEntropyLoss(ignore_index=-100)

    for batch in labeled_loader:
        out = model(batch['pcp'], batch['raw_features'])
        key_logits = out['key_logits']  # (B, T, 24)
        labels = batch['labels']         # (B, T) — key indices 0..23

        loss = loss_fn(key_logits.reshape(-1, 24), labels.reshape(-1))

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
```

Training schedule:
- Pre-training: 30 epochs, batch 64, AdamW LR 5e-4, cosine schedule
- Fine-tuning: 20 epochs, batch 8 (same as current), AdamW LR 1e-4

### 1.6 Gedizlioğlu Regularisation Post-Processing

After the model outputs per-note key predictions, apply a regularisation sweep:

```python
def regularise_key_sequence(key_predictions, min_segment_beats=4.0, onset_beats=None):
    """
    Suppress short key segments (tonicizations) by absorbing them
    into the surrounding key context.

    key_predictions: list of int (key indices 0..23), one per note
    onset_beats: list of float, beat position of each note
    min_segment_beats: minimum duration for a key segment to survive
    """
    if onset_beats is None:
        # Fall back to note-count heuristic
        return regularise_by_count(key_predictions, min_count=8)

    # Step 1: Identify segments of consecutive identical keys
    segments = []
    current_key = key_predictions[0]
    segment_start_beat = onset_beats[0]
    segment_start_idx = 0

    for i in range(1, len(key_predictions)):
        if key_predictions[i] != current_key:
            duration = onset_beats[i] - segment_start_beat
            segments.append((segment_start_idx, i, current_key, duration))
            current_key = key_predictions[i]
            segment_start_beat = onset_beats[i]
            segment_start_idx = i

    # Final segment
    final_duration = onset_beats[-1] - segment_start_beat + 0.5
    segments.append((segment_start_idx, len(key_predictions), current_key, final_duration))

    # Step 2: Absorb short segments into neighbours
    regularised = list(key_predictions)
    for start, end, key, duration in segments:
        if duration < min_segment_beats:
            # Find the nearest longer segment
            # Prefer the previous segment (conservative: maintain existing key)
            if start > 0:
                fill_key = regularised[start - 1]
            elif end < len(regularised):
                fill_key = key_predictions[end] if end < len(key_predictions) else key
            else:
                fill_key = key

            for j in range(start, end):
                regularised[j] = fill_key

    return regularised
```

### 1.7 Integration Points in Existing Code

**`harmonic_context_model.py`:**
- Add `SymbolicKeyTransformer` class alongside existing `HarmonicContextGRU`
- Add `compute_pcp_features()` utility function
- Keep all existing embedding constants (DELTA_BUCKETS_MS, etc.)
- Existing `encode_live_events()`, `collate_harmonic_batch()` remain unchanged

**`train_harmonic_context_model.py`:**
- Add `--model-type` argument: `gru` (default, backward compat) or `transformer`
- Add `--pretrain-epochs` argument for self-supervised pre-training phase
- Add `pretrain_epoch()` function
- Existing `HarmonicLabelDataset` is reused; add PCP computation in `notes_to_training_example()`

**`harmonic_context_runtime.py`:**
- `HarmonicContextRuntime.__init__()` accepts a `model_type` parameter
- `predict()` method computes PCP from the deque of note events before inference
- Add `regularise_key_sequence()` as an optional post-processing step (enable via constructor flag)

**`evaluate_harmonic_context_model.py`:**
- Add `mirex_weighted_score()` metric function
- Add per-key confusion matrix output
- Add tonicization-specific evaluation subset

### 1.8 Evaluation Plan

| Experiment | Baseline | Metric | Expected Outcome |
|-----------|----------|--------|-----------------|
| Pre-train only (no labels) | Random | Equivariance accuracy (transposition prediction) | >85% |
| Pre-train + fine-tune | Current GRU | Key accuracy | +5-10% improvement |
| Pre-train + fine-tune | Classical ensemble (JS) | MIREX weighted score | +8-15% improvement |
| + Gedizlioğlu regularisation | Without regularisation | Tonicization F1 | Fewer false modulations |
| Latency | Current GRU | Inference time per note | <3 ms (both should be <3 ms) |

---

## 2. Contribution B: Contrastive Hybrid Piece Identification

### 2.1 Architecture: Contrastive Symbolic Encoder

**Input Representation:**
Each note is encoded as a vector:
- Pitch interval from previous note: embedding(25 classes for [-12..+12]) → 16 dims
- IOI bucket: embedding(10 classes) → 8 dims
- Duration bucket: embedding(10 classes) → 8 dims
- Velocity bucket: embedding(16 classes) → 8 dims
- **Total per note: 40 dims**, projected to d_model = 64

Note: pitch is represented as *interval* (relative), not absolute pitch — this makes the encoder transposition-invariant at the input level.

**Sequence Encoder:**
- Lightweight Transformer: 2 layers, 4 heads, d_model = 64, ff_dim = 128
- Mean pooling over the sequence to produce a single 64-dim embedding
- L2 normalisation of the embedding

**Contrastive Loss (InfoNCE):**
```python
def info_nce_loss(embeddings_a, embeddings_b, temperature=0.07):
    """
    embeddings_a: (batch, d_model) — embeddings of performance excerpts
    embeddings_b: (batch, d_model) — embeddings of matching performances (same piece)

    Positive pairs: (a_i, b_i) for the same composition
    Negative pairs: all other (a_i, b_j) where i != j
    """
    # Cosine similarity matrix
    sim = torch.mm(embeddings_a, embeddings_b.t()) / temperature  # (B, B)

    # Labels: diagonal is positive
    labels = torch.arange(sim.size(0), device=sim.device)

    # Symmetric loss
    loss = (F.cross_entropy(sim, labels) + F.cross_entropy(sim.t(), labels)) / 2
    return loss
```

### 2.2 Training Data Construction from ATEPP

```python
def build_contrastive_pairs(metadata_csv, atepp_path):
    """
    Group performances by composition_id.
    For each composition with >= 2 performances, create pairs.
    Apply random transposition augmentation.
    """
    df = pd.read_csv(metadata_csv)
    pairs = []

    for comp_id, group in df.groupby('composition_id'):
        midi_paths = group['midi_path'].tolist()
        if len(midi_paths) < 2:
            continue

        # Create all pairs of performances of the same piece
        for i in range(len(midi_paths)):
            for j in range(i + 1, len(midi_paths)):
                pairs.append({
                    'anchor': os.path.join(atepp_path, midi_paths[i]),
                    'positive': os.path.join(atepp_path, midi_paths[j]),
                    'composition_id': comp_id,
                })

    return pairs


class ContrastiveDataset(Dataset):
    def __init__(self, pairs, window_size=64, transpose_range=6):
        self.pairs = pairs
        self.window_size = window_size
        self.transpose_range = transpose_range

    def __getitem__(self, idx):
        pair = self.pairs[idx]

        # Load and sample windows
        anchor_notes = load_first_n_notes(pair['anchor'], n=self.window_size)
        positive_notes = load_first_n_notes(pair['positive'], n=self.window_size)

        # Random transposition augmentation
        t = random.randint(-self.transpose_range, self.transpose_range)
        positive_notes = transpose_notes(positive_notes, t)

        # Encode as interval sequences
        anchor_encoded = encode_as_intervals(anchor_notes)
        positive_encoded = encode_as_intervals(positive_notes)

        return anchor_encoded, positive_encoded
```

### 2.3 Interval-Relative N-Gram Fingerprinting

Replace the current absolute-pitch fingerprint in `SimpleNGramFingerprinter.extract_fingerprints()`:

```python
def extract_interval_fingerprints(self, midi_file):
    """
    Instead of: pattern = tuple(notes[j].pitch for j in range(i, i + self.n))
    Use:        pattern = tuple(notes[j].pitch - notes[j-1].pitch for j in range(i+1, i + self.n))

    This makes the fingerprint transposition-invariant.
    """
    midi = pretty_midi.PrettyMIDI(midi_file)
    if not midi.instruments:
        return []

    notes = sorted(midi.instruments[0].notes, key=lambda x: x.start)
    fingerprints = []

    for i in range(len(notes) - self.n + 1):
        # Interval-based pattern: n-1 intervals from n notes
        pattern = tuple(
            int(np.clip(notes[i + j + 1].pitch - notes[i + j].pitch, -24, 24))
            for j in range(self.n - 1)
        )
        fp_hash = hash(pattern)
        fingerprints.append((fp_hash, i))

    return fingerprints
```

### 2.4 Dynamic N-Gram Filtering (from Baptista et al. 2021)

```python
def build_filtered_database(self, midi_files, min_discriminativeness=0.01):
    """
    Only store fingerprints that appear in fewer than min_discriminativeness
    fraction of pieces. Common patterns (e.g. ascending C major scale) match
    too many pieces and add noise.
    """
    # First pass: count how many pieces contain each fingerprint
    fp_piece_count = defaultdict(set)
    for midi_file in midi_files:
        fps = self.extract_interval_fingerprints(midi_file)
        piece_id = os.path.basename(midi_file)
        for fp_hash, _ in fps:
            fp_piece_count[fp_hash].add(piece_id)

    num_pieces = len(midi_files)
    max_pieces = int(num_pieces * min_discriminativeness)

    # Second pass: only store discriminative fingerprints
    for midi_file in midi_files:
        fps = self.extract_interval_fingerprints(midi_file)
        piece_id = os.path.basename(midi_file)
        for fp_hash, position in fps:
            if len(fp_piece_count[fp_hash]) <= max(max_pieces, 3):
                self.database[fp_hash][piece_id].append(position)
```

### 2.5 Integration: `HybridPieceIdentifier` Upgrade

```python
class ContrastiveEmbeddingRetriever:
    """Replaces StatisticalCoarseRetriever"""

    def __init__(self, model_path, d_model=64):
        self.model = ContrastiveEncoder(d_model=d_model)
        self.model.load_state_dict(torch.load(model_path))
        self.model.eval()
        self.embeddings = {}  # piece_id → embedding vector

    def build_index(self, piece_embeddings_path):
        """Load pre-computed per-piece embeddings."""
        with open(piece_embeddings_path, 'rb') as f:
            self.embeddings = pickle.load(f)

    def retrieve(self, query_notes, top_k=20):
        """
        query_notes: list of note dicts from live performance
        Returns: ranked list of (piece_id, similarity_score)
        """
        encoded = encode_as_intervals(query_notes)
        with torch.no_grad():
            query_embedding = self.model.encode(encoded)
            query_embedding = F.normalize(query_embedding, dim=-1)

        scores = {}
        for piece_id, piece_emb in self.embeddings.items():
            scores[piece_id] = float(torch.dot(query_embedding.squeeze(), piece_emb))

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [{'piece': pid, 'coarse_score': score} for pid, score in ranked[:top_k]]
```

### 2.6 Evaluation Plan

| Experiment | Baseline | Metric | Expected Outcome |
|-----------|----------|--------|-----------------|
| Coarse retrieval (contrastive) | Statistical coarse retriever | Top-20 recall | >90% (vs ~70% estimated) |
| Full pipeline (contrastive + interval n-grams) | Current absolute n-gram | MRR@1 | >0.7 |
| Transposition robustness (±2 semitones) | Current system | MRR@1 | >0.6 (vs ~0 for absolute pitch) |
| Notes-to-identification | Current system | Median notes to correct ID | <40 notes |
| Latency | Current system | Identification time | <500 ms |

---

## 3. Contribution C: Roman Numeral Labels for Chord-Aware Tuning

### 3.1 Offline Label Generation Pipeline

**Step 1: Run AugmentedNet on all 319 MusicXML scores**

```bash
# For each score in ATEPP_JI_Dataset
for score in ATEPP_JI_Dataset/ATEPP-1.2/*/scores/*.musicxml; do
    python -m AugmentedNet.inference AugmentedNetv.hdf5 "$score"
done
```

Output: `*_annotated.csv` files with per-timestep Roman numeral predictions.

**Step 2: Parse AugmentedNet output and merge with existing score key labels**

```python
def extend_key_labels_with_roman_numerals(key_label_json, augnet_csv):
    """
    Extend existing score_key_labels/*.json with function fields.

    Adds to each note:
    - 'roman_numeral': str (e.g. 'V', 'ii', 'V/V', 'viio6')
    - 'chord_quality': str (e.g. 'major', 'minor', 'diminished', 'dominant7')
    - 'chord_root': int (0-11, pitch class)
    - 'inversion': int (0, 1, 2)
    """
    with open(key_label_json) as f:
        label_data = json.load(f)

    augnet = pd.read_csv(augnet_csv)

    # Align by onset time
    for note in label_data['notes']:
        onset = note['onset_beat']
        # Find nearest AugmentedNet timestep
        closest = augnet.iloc[(augnet['onset'] - onset).abs().argsort()[:1]]

        note['roman_numeral'] = closest['roman_numeral'].values[0]
        note['chord_quality'] = closest['quality'].values[0]
        note['chord_root'] = int(closest['root'].values[0])
        note['inversion'] = int(closest['inversion'].values[0])

    with open(key_label_json, 'w') as f:
        json.dump(label_data, f, indent=2)
```

### 3.2 Function-Aware Tuning Ratios

**Extend `tuning-core.js` to support chord-function-dependent ratios:**

```javascript
// 7-limit extension for dominant seventh contexts
const JI_RATIOS_DOMINANT_7TH = {
    0: 1/1,      // Root
    4: 5/4,      // Major 3rd (pure)
    7: 3/2,      // Perfect 5th (pure)
    10: 7/4,     // Harmonic 7th (7-limit, 969 cents, -31 from 12TET)
};

export function calculateJIPitchBendWithFunction(midiNote, keyName, romanNumeral) {
    const keyRoot = getKeyRoot(keyName);
    const isMinor = isMinorKey(keyName);
    const interval = (midiNote - keyRoot + 144) % 12;

    // Default: use existing key-relative ratios
    let ratios = isMinor ? JI_RATIOS.minor : JI_RATIOS.major;

    // Override for dominant seventh chords
    if (romanNumeral && isDominantSeventh(romanNumeral)) {
        const chordRoot = getChordRootFromRomanNumeral(romanNumeral, keyRoot, isMinor);
        const intervalFromChordRoot = (midiNote - chordRoot + 144) % 12;

        if (JI_RATIOS_DOMINANT_7TH[intervalFromChordRoot] !== undefined) {
            const ratio = JI_RATIOS_DOMINANT_7TH[intervalFromChordRoot];
            return centsToPitchBend(ratioToCentsDeviation(ratio, intervalFromChordRoot));
        }
    }

    // Fallback to standard key-relative tuning
    const ratio = ratios[interval] || 1.0;
    return centsToPitchBend(ratioToCentsDeviation(ratio, interval));
}

function isDominantSeventh(romanNumeral) {
    // V7, V7/IV, V7/V, etc.
    return romanNumeral.startsWith('V7') ||
           romanNumeral.match(/^V\//) ||
           romanNumeral === 'V';
}
```

### 3.3 Server-Side Emission of Function Labels

In `two_stage_server.py`, extend the `ji_ratios` WebSocket message:

```python
# Current format:
emit('ji_ratios', {
    'note': midi_note,
    'key': current_key,
    'ratio': ji_ratio,
    'cents': cents_offset,
})

# Extended format:
emit('ji_ratios', {
    'note': midi_note,
    'key': current_key,
    'roman_numeral': roman_numeral_label,  # NEW
    'chord_quality': chord_quality,         # NEW
    'ratio': ji_ratio,
    'cents': cents_offset,
})
```

### 3.4 Pilot Audit Protocol

Before running AugmentedNet on all 319 scores, verify label quality on 20 representative pieces:

1. Select 5 Beethoven sonatas, 5 Mozart sonatas, 5 Schubert pieces, 5 Debussy pieces
2. Run AugmentedNet on each
3. Manually verify Roman numeral labels against published Schenkerian analyses or standard harmony textbook analyses
4. Report: per-key accuracy, per-chord-quality accuracy, tonicization detection rate
5. Gate condition: if per-key accuracy < 75% OR per-chord-quality accuracy < 60%, do NOT proceed to full corpus labelling

---

## 4. Infrastructure: Score Following Upgrade

### 4.1 Matchmaker Integration

Replace Parangonar in `two_stage_server.py`:

```python
# Current (lines 31-35):
try:
    import parangonar as pa
    PARANGONAR_IMPORT_ERROR = None
except Exception as exc:
    pa = None

# New:
try:
    from matchmaker import Matchmaker
    from matchmaker.features import LSEProcessor  # best-performing feature
    MATCHMAKER_IMPORT_ERROR = None
except Exception as exc:
    Matchmaker = None
    MATCHMAKER_IMPORT_ERROR = exc

# Fallback to parangonar if matchmaker unavailable
try:
    import parangonar as pa
    PARANGONAR_IMPORT_ERROR = None
except Exception as exc:
    pa = None
```

### 4.2 Matchmaker Alignment Setup

```python
def start_score_following_matchmaker(self, score_path):
    """Replace the Parangonar-based score following."""
    if Matchmaker is None:
        return self.start_score_following_parangonar(score_path)  # fallback

    self.matcher = Matchmaker(
        score_file=score_path,
        input_type="midi",  # symbolic input mode
    )

    # Start alignment in a background thread
    self.alignment_generator = self.matcher.run()
    self.state = SystemState.SCORE_FOLLOWING
```

### 4.3 RL Alignment as Drift Correction (Optional, Phase 4b)

If the OLTWArzt follower drifts beyond a threshold (e.g. 2000 ms error estimated from score-performance divergence), trigger the RL agent for correction:

```python
def check_alignment_drift(self, estimated_position, performed_notes):
    """
    If the alignment error exceeds threshold, run the RL agent
    on the recent context to re-anchor.
    """
    if self.alignment_error_ms > 2000:
        # Use Peter & Widmer (2024) RL agent for correction
        score_context = self.get_score_window(estimated_position, window=16)
        perf_context = performed_notes[-8:]

        corrected_position = self.rl_agent.predict(score_context, perf_context)
        self.matcher.reset_position(corrected_position)
```

---

## 5. MTS-MPE Refinements

### 5.1 Comma Drift Tracking

Add to `tuning-core.js`:

```javascript
let cumulativeDeviation = new Array(12).fill(0);  // per pitch class

export function trackCommaDrift(pitchClass, centsApplied) {
    cumulativeDeviation[pitchClass] += centsApplied;

    // If any pitch class has drifted more than ±35 cents from 12TET
    if (Math.abs(cumulativeDeviation[pitchClass]) > 35) {
        // Reset: gradually pull back toward 12TET
        const correction = -cumulativeDeviation[pitchClass] * 0.3;  // 30% pull-back
        cumulativeDeviation[pitchClass] += correction;
        return correction;  // Apply this correction to the next pitch bend
    }
    return 0;
}
```

### 5.2 MPE Channel Stealing

In `tuning-mpe.js`, upgrade the LRU allocator:

```javascript
function stealChannel(activeChannels, newNote) {
    // Priority: steal from the quietest, oldest note
    let bestChannel = null;
    let bestScore = Infinity;

    for (const [channel, noteInfo] of activeChannels) {
        const age = Date.now() - noteInfo.timestamp;
        const score = noteInfo.velocity * Math.exp(-age / 2000);  // decay with age
        if (score < bestScore) {
            bestScore = score;
            bestChannel = channel;
        }
    }

    return bestChannel;
}
```

---

## Appendix A: MIREX Weighted Score Implementation

Add to `evaluate_harmonic_context_model.py`:

```python
def mirex_weighted_score(predicted_key_idx, true_key_idx):
    """
    MIREX evaluation metric for key estimation.

    Scoring:
    - Exact match: 1.0
    - Perfect fifth relation: 0.5
    - Relative key (e.g. C major / A minor): 0.3
    - Parallel key (e.g. C major / C minor): 0.2
    - Other: 0.0
    """
    if predicted_key_idx == true_key_idx:
        return 1.0

    pred_pc = predicted_key_idx % 12
    true_pc = true_key_idx % 12
    pred_is_minor = predicted_key_idx >= 12
    true_is_minor = true_key_idx >= 12

    # Fifth relation: same mode, root a fifth apart
    if pred_is_minor == true_is_minor:
        if (pred_pc - true_pc) % 12 == 7 or (true_pc - pred_pc) % 12 == 7:
            return 0.5

    # Relative key: C major (0) ↔ A minor (21), i.e. minor root = major root - 3
    if pred_is_minor != true_is_minor:
        if pred_is_minor:
            # predicted minor, true major: check if pred_pc == (true_pc - 3) % 12
            if pred_pc == (true_pc + 9) % 12:
                return 0.3
        else:
            # predicted major, true minor: check if pred_pc == (true_pc + 3) % 12
            if pred_pc == (true_pc + 3) % 12:
                return 0.3

    # Parallel key: same root, different mode
    if pred_pc == true_pc and pred_is_minor != true_is_minor:
        return 0.2

    return 0.0
```

---

## Appendix B: Training Hyperparameter Summary

| Component | Parameter | Value | Source |
|-----------|-----------|-------|--------|
| S-KEY-Symbolic pre-training | batch size | 64 | Adapted from S-KEY (128 for audio, halved for symbolic) |
| S-KEY-Symbolic pre-training | learning rate | 5e-4 | Adapted from S-KEY (1e-3, reduced for smaller model) |
| S-KEY-Symbolic pre-training | epochs | 30 | Adapted from S-KEY (50 for 60k songs; fewer for 5k MIDIs) |
| S-KEY-Symbolic pre-training | optimizer | AdamW | S-KEY |
| S-KEY-Symbolic pre-training | schedule | cosine + linear warm-up | S-KEY |
| S-KEY-Symbolic pre-training | λ_equiv | 1.0 | S-KEY Equation 8 |
| S-KEY-Symbolic pre-training | λ_mode | 1.5 | S-KEY Equation 8 |
| S-KEY-Symbolic pre-training | λ_batch | 15.0 | S-KEY Equation 8 |
| S-KEY-Symbolic fine-tuning | batch size | 8 | Current `train_harmonic_context_model.py` |
| S-KEY-Symbolic fine-tuning | learning rate | 1e-4 | Reduced from pre-training |
| S-KEY-Symbolic fine-tuning | epochs | 20 | Doubled from current (10), pre-trained weights need less |
| Contrastive identifier | batch size | 128 | Standard for InfoNCE |
| Contrastive identifier | learning rate | 3e-4 | Standard for small Transformers |
| Contrastive identifier | temperature | 0.07 | CLaMP default |
| Contrastive identifier | transposition range | ±6 semitones | Design choice for ATEPP piano range |
| Contrastive identifier | epochs | 50 | CLaMP-scale on smaller dataset |
| Gedizlioğlu regularisation | min_segment_beats | 4.0 | Start value; tune on validation set |
| ChordGNN/AugmentedNet | N/A | Use pre-trained weights | No training needed |

---

*Document status: detailed implementation guide for internal use. Not for publication.*
