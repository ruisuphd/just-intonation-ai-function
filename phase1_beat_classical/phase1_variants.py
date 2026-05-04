"""Phase I model variants for the beat-classical research plan.

Implements three variants of the deployable B9 GRU:

  1. **T1** — HarmonicContextGRU with GLOBAL pitch-class histogram feature
     injected via a separate projection head and concatenated onto the
     per-frame GRU hidden state before the classifier. The global PCP is
     computed once per composition from the full note set, not the short
     sliding window (distinct from Phase B's B12 short-window PCP
     feature, which failed against the B9 baseline).

  2. **T2** — HarmonicContextGRU with two parallel chord-prediction
     heads (12-class chord root, 14-class chord quality) sharing the
     same GRU backbone as the key head. Chord-loss gradient is masked
     per-batch depending on whether chord labels are present
     (ATEPP has no chord labels; DCML Strategy A has them per note).

  3. **T6+T1+T2 combined** — full stack.

These variants inherit the architecture and hyperparameters of B9
(h = 96, β_ens = 0.999, causal, val-MIREX selection, 30 epochs) and
differ ONLY in the listed extensions, so the paired contrast against
the Phase B B9 baseline isolates the effect of each technique.

Usage:
    python research_data/train_phase1.py \
        --variant T6_T1_T2 \
        --seed 20260412 \
        --epochs 30
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

import torch
from torch import nn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harmonic_context_model import (  # noqa: E402
    HarmonicContextGRU, KEY_LABELS, DELTA_BUCKETS_MS,
    DURATION_BUCKETS_MS, VELOCITY_BUCKETS,
)


N_CHORD_ROOT = 12   # pitch classes for the chord root
N_CHORD_QUALITY = 14  # M, m, dim (o), aug (+), half-dim (%), Mm7 (V7),
                      # mm7, MM7, o7, %7, +M7, mM7, None (unknown), Other


class HarmonicContextGRUPhase1(nn.Module):
    """B9 extended with optional global-PCP feature and optional chord heads.

    Backward compatible with the Phase B B9 architecture when
    use_global_pcp=False and use_chord_heads=False.
    """

    def __init__(
        self,
        hidden_size: int = 96,
        num_layers: int = 1,
        dropout: float = 0.1,
        use_global_pcp: bool = False,   # Technique #1
        use_chord_heads: bool = False,  # Technique #2
        global_pcp_hidden: int = 24,    # projection size for global PCP feature
    ):
        super().__init__()
        self.use_global_pcp = use_global_pcp
        self.use_chord_heads = use_chord_heads
        self.global_pcp_hidden = global_pcp_hidden

        # --- B9 backbone (mirror of HarmonicContextGRU, without the pcp flag) ---
        self.pitch_embedding = nn.Embedding(12, 32)
        self.register_embedding = nn.Embedding(11, 8)
        self.delta_embedding = nn.Embedding(len(DELTA_BUCKETS_MS) + 1, 8)
        self.duration_embedding = nn.Embedding(len(DURATION_BUCKETS_MS) + 1, 8)
        self.velocity_embedding = nn.Embedding(len(VELOCITY_BUCKETS) + 1, 8)
        self.active_projection = nn.Linear(12, 16)
        feature_size = 32 + 8 + 8 + 8 + 8 + 16  # = 80
        self.input_projection = nn.Linear(feature_size, hidden_size)
        self.encoder = nn.GRU(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
            bidirectional=False,    # causal per B9
        )
        self.dropout = nn.Dropout(dropout)

        # --- Technique #1: global PCP feature ---
        if use_global_pcp:
            # Global PCP = 12-dim piece-level histogram, projected up.
            self.global_pcp_projection = nn.Sequential(
                nn.Linear(12, global_pcp_hidden),
                nn.ReLU(),
                nn.Linear(global_pcp_hidden, global_pcp_hidden),
            )
            classifier_input = hidden_size + global_pcp_hidden
        else:
            classifier_input = hidden_size

        self.classifier = nn.Linear(classifier_input, len(KEY_LABELS))

        # --- Technique #2: chord heads ---
        if use_chord_heads:
            self.chord_root_head = nn.Linear(classifier_input, N_CHORD_ROOT)
            self.chord_quality_head = nn.Linear(classifier_input, N_CHORD_QUALITY)

    def forward(self, batch: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        """Return dict with:
          * 'key_logits' : (B, T, 24) always
          * 'chord_root_logits' : (B, T, 12) if use_chord_heads
          * 'chord_quality_logits' : (B, T, 14) if use_chord_heads
        """
        feature_parts = [
            self.pitch_embedding(batch['pitch_class']),
            self.register_embedding(batch['register']),
            self.delta_embedding(batch['delta_bucket']),
            self.duration_embedding(batch['duration_bucket']),
            self.velocity_embedding(batch['velocity_bucket']),
            self.active_projection(batch['active_mask']),
        ]
        features = torch.cat(feature_parts, dim=-1)
        projected = self.input_projection(features)
        encoded, _ = self.encoder(projected)
        encoded = self.dropout(encoded)  # (B, T, H)

        # Technique #1: concat the global PCP projection onto every frame's hidden.
        if self.use_global_pcp:
            global_pcp = batch['global_pcp']         # (B, 12)
            gp = self.global_pcp_projection(global_pcp)  # (B, gp_hidden)
            gp_expanded = gp.unsqueeze(1).expand(-1, encoded.shape[1], -1)
            encoded = torch.cat([encoded, gp_expanded], dim=-1)

        out: Dict[str, torch.Tensor] = {'key_logits': self.classifier(encoded)}

        # Technique #2: two chord heads over the same hidden.
        if self.use_chord_heads:
            out['chord_root_logits'] = self.chord_root_head(encoded)
            out['chord_quality_logits'] = self.chord_quality_head(encoded)

        return out

    @torch.no_grad()
    def predict_last_step(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        """Back-compat with HarmonicContextGRU.predict_last_step — returns
        key logits at the last valid frame for deployment in
        HarmonicContextRuntime.
        """
        out = self.forward(batch)
        logits = out['key_logits']
        lengths = batch['lengths']
        batch_indices = torch.arange(logits.shape[0], device=logits.device)
        last_indices = torch.clamp(lengths - 1, min=0)
        return logits[batch_indices, last_indices]


# ---------------------------------------------------------------------------
# Chord-label vocabulary: DCML chord-quality strings → 14-class index
# ---------------------------------------------------------------------------

CHORD_QUALITY_VOCAB = {
    'M': 0, 'm': 1, 'o': 2, '+': 3, '%': 4,
    'Mm7': 5, 'mm7': 6, 'MM7': 7, 'o7': 8, '%7': 9,
    '+M7': 10, 'mM7': 11, '+7': 12,
    # Inversions: fall back to their triad stem's 7th code.
    # (Handled by the vocab-lookup function in phase1_dataset.py.)
}
CHORD_QUALITY_OTHER_IDX = 13  # for unrecognised qualities
N_CHORD_QUALITIES_TOTAL = 14


def chord_quality_to_index(quality_str: str) -> int:
    """Map a DCML `chord_type` string to a 0..13 class index.
    Falls back to 'Other' (13) for unrecognised or empty strings.
    """
    if not quality_str:
        return CHORD_QUALITY_OTHER_IDX
    # Strip inversion suffix digits (e.g., Mm65, Mm43, Mm42 -> Mm7 stem).
    if quality_str.startswith('Mm') and not quality_str == 'Mm7':
        return CHORD_QUALITY_VOCAB['Mm7']
    if quality_str.startswith('mm') and not quality_str == 'mm7':
        return CHORD_QUALITY_VOCAB['mm7']
    if quality_str.startswith('MM') and not quality_str == 'MM7':
        return CHORD_QUALITY_VOCAB['MM7']
    return CHORD_QUALITY_VOCAB.get(quality_str, CHORD_QUALITY_OTHER_IDX)


def extract_chord_labels_from_dcml(notes) -> Optional[Dict]:
    """Given a list of DCML-format notes (each with chord_numeral /
    chord_figbass / chord_type / chord_relativeroot fields), produce
    per-note chord-root (0..11) and chord-quality (0..13) labels.

    Returns None if the notes do not carry chord labels (ATEPP case).
    The returned dict has two lists of ints, each the same length as notes.
    """
    if not notes or 'chord_numeral' not in notes[0]:
        return None
    # Mapping of DCML roman numerals to scale-degree offsets
    _MAJOR = {'I': 0, 'II': 2, 'III': 4, 'IV': 5, 'V': 7, 'VI': 9, 'VII': 11}
    _MINOR = {'I': 0, 'II': 2, 'III': 3, 'IV': 5, 'V': 7, 'VI': 8, 'VII': 10}
    roots = []
    qualities = []
    for n in notes:
        num = n.get('chord_numeral', '')
        # Parse accidental + roman: e.g., "bII" → -1 + 2 = +1 semitones
        acc = 0
        i = 0
        while i < len(num) and num[i] in ('#', 'b'):
            acc += 1 if num[i] == '#' else -1
            i += 1
        roman = num[i:].upper()
        # Strip digits (inversion) and form characters
        roman_clean = ''.join(c for c in roman if c in 'IVXMD')[:3]
        is_minor_numeral = False
        # Case-based inference of chord quality is mode-dependent; fall back
        # on neutral major-scale offsets unless we can't parse.
        tonic_pc = int(n.get('tonic_pc', 0))
        local_is_minor = bool(n.get('is_minor', False))
        scale_offset = (_MINOR if local_is_minor else _MAJOR).get(roman_clean)
        if scale_offset is None:
            # Unknown numeral - fall back to tonic (0)
            root_pc = tonic_pc
        else:
            root_pc = (tonic_pc + scale_offset + acc) % 12
        roots.append(int(root_pc))
        qualities.append(chord_quality_to_index(n.get('chord_type', '')))
    return {'chord_root_labels': roots, 'chord_quality_labels': qualities}


def compute_global_pcp(notes) -> list:
    """Compute 12-bin pitch-class histogram over all notes in a piece, weighted
    by duration. Returns a 12-list (normalised so the sum is 1.0).
    """
    hist = [0.0] * 12
    for n in notes:
        p = int(n.get('pitch', 0))
        d = float(n.get('duration_beat', 1.0))
        hist[p % 12] += d
    total = sum(hist)
    if total > 0:
        hist = [x / total for x in hist]
    return hist
