#!/usr/bin/env python3
"""
Runtime wrapper for the causal harmonic-state model.

Supports four model paths:

  - 'gru'           : Phase B B9 baseline (HarmonicContextGRU; deployed pre-2026-05-02)
  - 'transformer'   : SymbolicKeyTransformer (alternative architecture)
  - 'phase1_t6_t1'  : Phase I T6_T1 — best-evaluated detector by FW MIREX
                      (Su, 2026p §2.3; cell mean = 0.6707 ± 0.0103, n = 5).
                      Adds a global pitch-class-profile (PCP) feature input.
  - 'phase1_t6_t1_t2'
                    : Phase I T6_T1_T2 — full pre-registered stack
                      (Su, 2026q §2.4; cell mean = 0.6606 ± 0.0122, n = 5).
                      Same global-PCP feature as T6_T1, plus auxiliary chord
                      heads (chord_root + chord_quality). H4b is fail-to-reject
                      at the cluster-bootstrap level (Su, 2026q): T6_T1_T2 does
                      not statistically outperform T6_T1, so T6_T1 is the
                      recommended deployment target.

The Phase I paths require a global pitch-class profile feature
(`batch['global_pcp']`). At deployment time three causality policies are
supported, controlled by the `causality_policy` constructor argument:

  - 'running'   (DEFAULT) — global PCP is recomputed from all live note
                 events received so far. Fully causal; no future or
                 score-derived information leaks. Recommended for the
                 unscored / unmatched real-time path.
  - 'score_known' — global PCP is supplied by the caller via
                    `set_score_global_pcp(pcp)` once piece identity has
                    been confirmed by the §4.2 fingerprinting layer or
                    the §4.3 score-following layer. Causal in the sense
                    that the score is a constant fixture of the
                    performance, not future information.
  - 'offline'   — global PCP is set once via `set_offline_global_pcp(pcp)`
                  from the full-piece note stream. Non-causal; intended
                  for offline test-set evaluation that mirrors training
                  conditions exactly. **Not safe for live tuning.**

Audit history (see `phd_project_audit_report_2026-04-30.md` finding C4):
the previous version of this file only loaded `HarmonicContextGRU` /
`SymbolicKeyTransformer`, so deploying T6_T1 (the Phase I best-evaluated
detector) was impossible — the model requires `global_pcp` at forward
time and the runtime never computed it. This file (rewritten 2026-05-02)
closes that gap.

Backwards compatibility: existing callers using `model_type='gru'` or
`model_type='transformer'` see no behavioural change; the Phase I paths
are opt-in via `model_type='phase1_t6_t1'` or `'phase1_t6_t1_t2'`.

Intentionally conservative: only emits predictions above
`confidence_threshold`, and (for Phase I paths) only after at least
`global_pcp_warmup` note events have arrived so the running PCP is not
dominated by a single note.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Sequence

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

# Phase I import is package-relative; we add the project root to sys.path so
# that running this module from any cwd resolves the import the same way.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


# ─────────────────────────────────────────────────────────────────────────
# Model-type registry. Adding a new variant is a one-line entry.

_MODEL_TYPES = {
    'gru', 'transformer', 'phase1_t6_t1', 'phase1_t6_t1_t2',
}
_PHASE1_TYPES = {'phase1_t6_t1', 'phase1_t6_t1_t2'}
_CAUSALITY_POLICIES = {'running', 'score_known', 'offline'}


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
        causality_policy: str = 'running',
        global_pcp_warmup: int = 8,
    ):
        """
        Args:
            checkpoint_path: path to a .pt checkpoint dict containing
                'model_state_dict'.
            confidence_threshold: predictions below this softmax max are
                suppressed (returns None).
            max_events: rolling window of note events kept in memory.
            device: torch device string.
            model_type: one of 'gru', 'transformer', 'phase1_t6_t1',
                'phase1_t6_t1_t2'. Phase I types require global PCP feature
                plumbing (this runtime handles it automatically per
                `causality_policy`).
            regularise: apply key-sequence regularisation
                (`regularise_key_sequence`) to suppress short tonicizations.
            min_segment_beats: regularisation parameter (only used if
                onset_beats are provided, currently unused in the live path).
            causality_policy: one of 'running' / 'score_known' / 'offline'.
                Only consulted for Phase I model_types. Default 'running'
                is the only fully-causal option for the unscored live path.
            global_pcp_warmup: minimum note events before Phase I `predict()`
                returns a non-None result. Prevents the running PCP from being
                dominated by a single note. Default 8 mirrors the
                `regularise_key_sequence` `min_segment_notes` default.
        """
        if model_type not in _MODEL_TYPES:
            raise ValueError(
                f'unknown model_type {model_type!r}; expected one of {sorted(_MODEL_TYPES)}'
            )
        if causality_policy not in _CAUSALITY_POLICIES:
            raise ValueError(
                f'unknown causality_policy {causality_policy!r}; '
                f'expected one of {sorted(_CAUSALITY_POLICIES)}'
            )

        self.checkpoint_path = checkpoint_path
        self.confidence_threshold = confidence_threshold
        self.max_events = max_events
        self.device = torch.device(device)
        self.model_type = model_type
        self.regularise = regularise
        self.min_segment_beats = min_segment_beats
        self.causality_policy = causality_policy
        self.global_pcp_warmup = max(1, int(global_pcp_warmup))

        self.model: Optional[torch.nn.Module] = None
        self.note_events: Deque[Dict[str, object]] = deque(maxlen=max_events)
        self._recent_keys: List[int] = []

        # Phase I global-PCP cache. Populated by set_score_global_pcp() or
        # set_offline_global_pcp() depending on causality policy. The
        # 'running' policy ignores these and recomputes per-call from
        # `self.note_events`.
        self._score_global_pcp: Optional[List[float]] = None
        self._offline_global_pcp: Optional[List[float]] = None

    # ─────────────────────────────────────────────────────────────────────
    # Public API

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
        elif self.model_type in _PHASE1_TYPES:
            # Lazy import: only required for Phase I paths, and avoids a
            # hard dependency for callers who only need GRU/Transformer.
            from phase1_beat_classical.phase1_variants import (
                HarmonicContextGRUPhase1,
            )
            use_chord_heads = (self.model_type == 'phase1_t6_t1_t2')
            self.model = HarmonicContextGRUPhase1(
                hidden_size=96,
                num_layers=1,
                dropout=0.1,
                use_global_pcp=True,
                use_chord_heads=use_chord_heads,
            ).to(self.device)
        else:
            self.model = HarmonicContextGRU().to(self.device)

        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.eval()
        return True

    def reset(self) -> None:
        """Reset rolling note buffer and key-sequence regulariser state.

        Note: does NOT clear the score_known / offline global-PCP cache,
        because those are typically set once per piece. Call
        `clear_global_pcp_cache()` to drop them too.
        """
        self.note_events.clear()
        self._recent_keys.clear()

    def clear_global_pcp_cache(self) -> None:
        self._score_global_pcp = None
        self._offline_global_pcp = None

    def set_score_global_pcp(self, pcp_12: Sequence[float]) -> None:
        """Provide a 12-bin pitch-class profile from the matched score.

        Use when piece identity has been confirmed (§4.2 fingerprinting +
        §4.3 score following) and the runtime should consume the score's
        full-piece PCP rather than the live running PCP. Active only when
        `causality_policy == 'score_known'`.

        Args:
            pcp_12: 12-element float sequence, will be normalised to L1=1.
        """
        self._score_global_pcp = self._normalise_pcp_12(pcp_12)

    def set_offline_global_pcp(self, pcp_12: Sequence[float]) -> None:
        """Provide a 12-bin pitch-class profile from a full-piece offline pass.

        For test-set evaluation only — non-causal. Active only when
        `causality_policy == 'offline'`.
        """
        self._offline_global_pcp = self._normalise_pcp_12(pcp_12)

    def add_note(
        self, pitch: int, velocity: int, time_ms: float,
        active_notes: List[int], duration_ms: Optional[float] = None,
    ) -> None:
        """Append a note event to the rolling buffer.

        `duration_ms` is optional. If supplied (e.g. when the host has both
        note-on and note-off available), the running global PCP weights
        each note by its duration — closer to the training-time
        `compute_global_pcp` convention which weights by `duration_beat`.
        If absent, the running PCP falls back to uniform per-note
        weighting.
        """
        event: Dict[str, object] = {
            'note': int(pitch),
            'velocity': int(velocity),
            'time_ms': float(time_ms),
            'active_notes': list(active_notes),
        }
        if duration_ms is not None:
            event['duration_ms'] = float(duration_ms)
        self.note_events.append(event)

    @torch.no_grad()
    def predict(self) -> Optional[Dict[str, object]]:
        if self.model is None or not self.note_events:
            return None

        # Phase I warm-up gate: don't predict until enough events for a
        # stable running PCP.
        if self.model_type in _PHASE1_TYPES and \
                self.causality_policy == 'running' and \
                len(self.note_events) < self.global_pcp_warmup:
            return None

        encoded = encode_live_events(list(self.note_events))
        encoded['labels'] = [0] * len(encoded['pitch_class'])

        # Path-specific feature plumbing
        if self.model_type == 'transformer':
            encoded['pcp'] = compute_pcp(encoded['pitch_class'], window_size=32)
        elif self.model_type in _PHASE1_TYPES:
            encoded['global_pcp'] = self._resolve_global_pcp()

        batch = collate_harmonic_batch([encoded])

        # collate_harmonic_batch does not know about global_pcp; the
        # phase1_beat_classical package has its own collator, but here we
        # add the tensor manually to keep the runtime free of a hard
        # phase1_beat_classical dependency at import time.
        if self.model_type in _PHASE1_TYPES:
            batch['global_pcp'] = torch.tensor(
                [encoded['global_pcp']], dtype=torch.float32,
            )

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

        out: Dict[str, object] = {
            'key': index_to_key(final_key_idx),
            'confidence': confidence_value,
            'source': 'harmonic_context_model_' + self.model_type,
        }
        if self.model_type in _PHASE1_TYPES:
            out['causality_policy'] = self.causality_policy
        return out

    # ─────────────────────────────────────────────────────────────────────
    # Phase I global-PCP resolution

    def _resolve_global_pcp(self) -> List[float]:
        """Return the 12-bin global PCP per the configured causality policy."""
        if self.causality_policy == 'score_known' and self._score_global_pcp is not None:
            return list(self._score_global_pcp)
        if self.causality_policy == 'offline' and self._offline_global_pcp is not None:
            return list(self._offline_global_pcp)
        # 'running' default (or fallback if score/offline cache not set yet).
        return self._compute_running_global_pcp()

    def _compute_running_global_pcp(self) -> List[float]:
        """Causal running PCP: 12-bin histogram over all events seen so far.

        Weights by `duration_ms` if available, else by 1.0. Mirrors the
        training-time `compute_global_pcp` convention (weight by
        `duration_beat`) as closely as the runtime event schema allows.
        """
        hist = [0.0] * 12
        for ev in self.note_events:
            pitch_class = int(ev['note']) % 12
            weight = float(ev.get('duration_ms', 0.0))
            if weight <= 0:
                weight = 1.0
            hist[pitch_class] += weight
        total = sum(hist)
        if total > 0:
            return [h / total for h in hist]
        return [1.0 / 12] * 12

    @staticmethod
    def _normalise_pcp_12(pcp_12: Sequence[float]) -> List[float]:
        if len(pcp_12) != 12:
            raise ValueError(f'expected 12-element PCP, got {len(pcp_12)}')
        vals = [max(0.0, float(x)) for x in pcp_12]
        total = sum(vals)
        if total > 0:
            return [v / total for v in vals]
        return [1.0 / 12] * 12
