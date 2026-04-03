#!/usr/bin/env python3
"""
Runtime wrapper for the causal harmonic-state model.

Supports both GRU baseline and SymbolicKeyTransformer.
Intentionally conservative: only emits predictions above confidence threshold.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional

import torch

from harmonic_context_model import (
    HarmonicContextGRU,
    SymbolicKeyTransformer,
    collate_harmonic_batch,
    compute_pcp,
    encode_live_events,
    index_to_key,
    regularise_key_sequence,
)


class HarmonicContextRuntime:
    def __init__(
        self,
        checkpoint_path: str,
        confidence_threshold: float = 0.60,
        max_events: int = 128,
        device: str = 'cpu',
        model_type: str = 'gru',
        regularise: bool = False,
        min_segment_beats: float = 4.0,
    ):
        self.checkpoint_path = checkpoint_path
        self.confidence_threshold = confidence_threshold
        self.max_events = max_events
        self.device = torch.device(device)
        self.model_type = model_type
        self.regularise = regularise
        self.min_segment_beats = min_segment_beats

        self.model: Optional[torch.nn.Module] = None
        self.note_events: Deque[Dict[str, object]] = deque(maxlen=max_events)
        self._recent_keys: List[int] = []

    def is_available(self) -> bool:
        return self.model is not None

    def load(self) -> bool:
        try:
            checkpoint = torch.load(
                self.checkpoint_path, map_location=self.device, weights_only=True,
            )
        except FileNotFoundError:
            return False

        if self.model_type == 'transformer':
            self.model = SymbolicKeyTransformer().to(self.device)
        else:
            self.model = HarmonicContextGRU().to(self.device)

        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.eval()
        return True

    def reset(self) -> None:
        self.note_events.clear()
        self._recent_keys.clear()

    def add_note(
        self, pitch: int, velocity: int, time_ms: float, active_notes: List[int],
    ) -> None:
        self.note_events.append({
            'note': int(pitch),
            'velocity': int(velocity),
            'time_ms': float(time_ms),
            'active_notes': list(active_notes),
        })

    @torch.no_grad()
    def predict(self) -> Optional[Dict[str, object]]:
        if self.model is None or not self.note_events:
            return None

        encoded = encode_live_events(list(self.note_events))
        encoded['labels'] = [0] * len(encoded['pitch_class'])

        if self.model_type == 'transformer':
            encoded['pcp'] = compute_pcp(encoded['pitch_class'], window_size=32)

        batch = collate_harmonic_batch([encoded])
        batch = {
            key: value.to(self.device) if isinstance(value, torch.Tensor) else value
            for key, value in batch.items()
        }

        logits = self.model.predict_last_step(batch)
        probabilities = torch.softmax(logits, dim=-1)[0]
        confidence, index = torch.max(probabilities, dim=0)

        raw_key_idx = int(index.item())
        confidence_value = float(confidence.item())

        if self.regularise:
            self._recent_keys.append(raw_key_idx)
            if len(self._recent_keys) > 32:
                self._recent_keys = self._recent_keys[-32:]
            regularised = regularise_key_sequence(
                self._recent_keys, min_segment_notes=8,
            )
            final_key_idx = regularised[-1]
        else:
            final_key_idx = raw_key_idx

        if confidence_value < self.confidence_threshold:
            return None

        return {
            'key': index_to_key(final_key_idx),
            'confidence': confidence_value,
            'source': 'harmonic_context_model_' + self.model_type,
        }
