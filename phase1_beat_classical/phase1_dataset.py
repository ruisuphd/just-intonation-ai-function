"""Phase I dataset and collate function — ×12 expansion + chord labels + global PCP.

Wraps the existing project dataset to add:

  * **Deterministic ×12 transposition expansion** (Technique #6). Every piece
    appears in all 12 pitch classes per epoch (vs. the baseline's random
    single-shift sampling). Each expanded replica carries its own key-label
    rotation (via `augment_transpose` from the base training script).

  * **Global pitch-class histogram feature** (Technique #1). Each batch
    item carries a `global_pcp` (12-dim) tensor computed once per piece
    (transposed along with the piece when the expansion rotates it).

  * **Chord labels with presence mask** (Technique #2). DCML Strategy A
    pieces carry per-note `chord_root_labels` / `chord_quality_labels`;
    ATEPP pieces do not. A per-batch `chord_mask` tensor (0/1 per note)
    is added so the loss function can skip unlabelled notes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Sequence

import torch
from torch.utils.data import Dataset

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from train_harmonic_context_model import (  # noqa: E402
    HarmonicLabelDataset, notes_to_training_example, augment_transpose,
)
from harmonic_context_model import (  # noqa: E402
    KEY_LABELS, key_to_index, collate_harmonic_batch, encode_live_events,
)

from phase1_beat_classical.phase1_variants import (  # noqa: E402
    extract_chord_labels_from_dcml, compute_global_pcp,
    CHORD_QUALITY_OTHER_IDX, N_CHORD_QUALITIES_TOTAL, N_CHORD_ROOT,
)


def _dcml_key_to_atepp(tonic_pc: int, is_minor: bool) -> str:
    """DCML stores minor keys as lowercase (e.g. 'b'); ATEPP expects 'Bm'."""
    return KEY_LABELS[int(tonic_pc) + (12 if is_minor else 0)]


def _normalise_dcml_record(rec: Dict) -> Dict:
    """If a record's notes use DCML key convention (lowercase for minor),
    rewrite every note's `key` field to the ATEPP canonical form.
    A no-op on ATEPP records (they already use 'Bm' form)."""
    notes = rec.get('notes', [])
    if not notes:
        return rec
    # Heuristic: DCML files carry `chord_numeral` on every note; ATEPP doesn't.
    if 'chord_numeral' not in notes[0]:
        return rec
    normalised = dict(rec)
    normalised['notes'] = []
    for n in notes:
        copy = dict(n)
        tpc = copy.get('tonic_pc')
        isminor = copy.get('is_minor', False)
        if tpc is not None:
            copy['key'] = _dcml_key_to_atepp(tpc, isminor)
        normalised['notes'].append(copy)
    return normalised


class Phase1Dataset(Dataset):
    """Phase I dataset: deterministic ×12 transposition + optional chord /
    global-PCP extras.

    The input is a list of records in the standard project format. For each
    record, this dataset emits 12 training examples — one per pitch-class
    shift in ``list(range(12))``. Set ``n_transpositions=1`` to disable the
    ×12 expansion and fall back to the baseline single-pass behaviour
    (ablation mode).
    """

    def __init__(
        self,
        records: Sequence[Dict],
        window_size: int = 256,
        window_hop: int = 128,
        use_global_pcp: bool = False,
        use_chord_labels: bool = False,
        n_transpositions: int = 12,
    ):
        # Normalise DCML records to ATEPP key convention on load.
        self.records = [_normalise_dcml_record(r) for r in records]
        self.window_size = window_size
        self.window_hop = window_hop
        self.use_global_pcp = use_global_pcp
        self.use_chord_labels = use_chord_labels
        self.n_transpositions = max(1, int(n_transpositions))

        # Pre-compute an (record_idx, shift, window_start) index map for
        # deterministic iteration.
        self._index_map: List = []
        for rec_idx, rec in enumerate(self.records):
            notes = rec.get('notes', [])
            if not notes:
                continue
            # For each of the N transpositions, emit all sliding windows.
            for shift in range(self.n_transpositions):
                # Use the window plan of the base dataset: we call
                # notes_to_training_example in __getitem__ which handles
                # the window length, so here we simply emit one key per
                # (rec, shift) pair (one-sample-per-piece, no further
                # within-piece windowing expansion; the training loop
                # uses full-piece batching).
                self._index_map.append((rec_idx, shift))

    def __len__(self) -> int:
        return len(self._index_map)

    def __getitem__(self, idx: int) -> Dict[str, object]:
        rec_idx, shift = self._index_map[idx]
        rec = self.records[rec_idx]
        raw_notes = rec['notes']
        # Apply the shift.
        if shift != 0:
            notes = augment_transpose(raw_notes, shift)
            if not notes:     # all notes fell out of MIDI range
                notes = raw_notes
        else:
            notes = raw_notes

        example = notes_to_training_example(
            notes,
            augment=False,   # deterministic shift is applied already
            composition_is_modulating=rec.get('is_modulating', False),
            modulation_upweight=1.0,
            modulation_transition_upweight=1.0,
            modulation_transition_window=0,
        )

        # Global PCP — computed on the TRANSPOSED notes so it stays
        # aligned with the (also-rotated) key labels.
        if self.use_global_pcp:
            example['global_pcp'] = compute_global_pcp(notes)
        # Chord labels — must also rotate chord root by `shift`.
        if self.use_chord_labels:
            chord = extract_chord_labels_from_dcml(notes)
            if chord is None:
                n = len(example['pitch_class'])
                example['chord_root_labels'] = [-100] * n
                example['chord_quality_labels'] = [-100] * n
                example['chord_mask'] = [0.0] * n
            else:
                # chord roots are already computed from TRANSPOSED tonic_pc
                # by augment_transpose, so no further rotation needed here.
                roots = chord['chord_root_labels']
                quals = chord['chord_quality_labels']
                # Truncate / pad to match example length.
                n = len(example['pitch_class'])
                if len(roots) != n:
                    roots = (roots + [-100] * n)[:n]
                    quals = (quals + [-100] * n)[:n]
                example['chord_root_labels'] = roots
                example['chord_quality_labels'] = quals
                example['chord_mask'] = [1.0 if r >= 0 else 0.0 for r in roots]

        return example


def collate_phase1_batch(batch: List[Dict]) -> Dict[str, torch.Tensor]:
    """Collate a Phase I batch, extending collate_harmonic_batch with
    global_pcp (B, 12) and chord labels / mask (B, T) where present."""
    base = collate_harmonic_batch(batch)

    # Global PCP
    has_gp = all('global_pcp' in item for item in batch)
    if has_gp:
        base['global_pcp'] = torch.tensor(
            [item['global_pcp'] for item in batch], dtype=torch.float32,
        )

    # Chord labels / mask
    has_cl = all('chord_root_labels' in item for item in batch)
    if has_cl:
        max_len = base['labels'].shape[1]
        import numpy as np
        root_arr = np.full((len(batch), max_len), -100, dtype=np.int64)
        qual_arr = np.full((len(batch), max_len), -100, dtype=np.int64)
        mask_arr = np.zeros((len(batch), max_len), dtype=np.float32)
        for i, item in enumerate(batch):
            rl = item['chord_root_labels']
            ql = item['chord_quality_labels']
            ml = item['chord_mask']
            L = min(len(rl), max_len)
            root_arr[i, :L] = rl[:L]
            qual_arr[i, :L] = ql[:L]
            mask_arr[i, :L] = ml[:L]
        base['chord_root_labels'] = torch.tensor(root_arr)
        base['chord_quality_labels'] = torch.tensor(qual_arr)
        base['chord_mask'] = torch.tensor(mask_arr)
    return base
