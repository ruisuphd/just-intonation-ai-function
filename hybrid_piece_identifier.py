#!/usr/bin/env python3
"""
Hybrid piece identification infrastructure.

Current implementation:
- coarse retrieval using lightweight symbolic statistics
- exact reranking using the existing n-gram fingerprint database

This is designed so a learned coarse encoder can replace the current coarse
retriever later without changing the reranking contract.
"""

from __future__ import annotations

import math
import os
import pickle
from typing import Dict, List, Sequence

import numpy as np
import pretty_midi

from simple_ngram_fingerprinting import SimpleNGramFingerprinter


INTERVAL_RANGE = list(range(-12, 13))
IOI_BUCKETS = [0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0]
REGISTER_BUCKETS = [(21, 36), (36, 48), (48, 60), (60, 72), (72, 84), (84, 96), (96, 109)]


def cosine_similarity(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    denom = np.linalg.norm(vector_a) * np.linalg.norm(vector_b)
    if denom == 0:
        return 0.0
    return float(np.dot(vector_a, vector_b) / denom)


class StatisticalCoarseRetriever:
    def __init__(self) -> None:
        self.index: Dict[str, np.ndarray] = {}

    def extract_features(self, midi_file: str) -> np.ndarray:
        midi = pretty_midi.PrettyMIDI(midi_file)
        if not midi.instruments:
            return np.zeros(len(INTERVAL_RANGE) + len(IOI_BUCKETS) + len(REGISTER_BUCKETS), dtype=np.float32)

        notes = sorted(midi.instruments[0].notes, key=lambda note: note.start)
        if len(notes) < 2:
            return np.zeros(len(INTERVAL_RANGE) + len(IOI_BUCKETS) + len(REGISTER_BUCKETS), dtype=np.float32)

        interval_hist = np.zeros(len(INTERVAL_RANGE), dtype=np.float32)
        ioi_hist = np.zeros(len(IOI_BUCKETS), dtype=np.float32)
        register_hist = np.zeros(len(REGISTER_BUCKETS), dtype=np.float32)

        previous_note = notes[0]
        for note in notes[1:]:
            interval = int(np.clip(note.pitch - previous_note.pitch, -12, 12))
            interval_hist[interval + 12] += 1

            ioi = max(0.0, note.start - previous_note.start)
            ioi_idx = sum(ioi > edge for edge in IOI_BUCKETS)
            if ioi_idx < len(ioi_hist):
                ioi_hist[ioi_idx] += 1

            previous_note = note

        for note in notes:
            for idx, (lower, upper) in enumerate(REGISTER_BUCKETS):
                if lower <= note.pitch < upper:
                    register_hist[idx] += 1
                    break

        vector = np.concatenate([interval_hist, ioi_hist, register_hist]).astype(np.float32)
        if np.linalg.norm(vector) > 0:
            vector /= np.linalg.norm(vector)
        return vector

    def build_index(self, piece_map: Dict[str, str]) -> None:
        self.index = {
            piece_id: self.extract_features(midi_file)
            for midi_file, piece_id in piece_map.items()
        }

    def retrieve(self, query_midi_file: str, top_k: int = 20) -> List[Dict[str, float]]:
        query_vector = self.extract_features(query_midi_file)
        ranked = [
            {'piece': piece_id, 'coarse_score': cosine_similarity(query_vector, feature_vector)}
            for piece_id, feature_vector in self.index.items()
        ]
        ranked.sort(key=lambda row: row['coarse_score'], reverse=True)
        return ranked[:top_k]

    def save(self, path: str) -> None:
        with open(path, 'wb') as handle:
            pickle.dump(self.index, handle)

    def load(self, path: str) -> None:
        with open(path, 'rb') as handle:
            self.index = pickle.load(handle)


class AriaEmbBaselineRetriever:
    """Zero-shot piece retrieval baseline using AriaEmb embeddings.

    AriaEmb (Bradshaw et al., ISMIR 2025, arXiv:2506.23869) is a SimCLR-based
    contrastive model trained on ~60k hours of piano MIDI. This class provides
    a baseline for prefix identification at varying note counts.

    The thesis contribution must beat this baseline at short prefixes (N=5-15
    notes) to demonstrate that a purpose-built prefix identifier adds value
    over a general-purpose symbolic embedding.

    Requires: pip install aria-embeddings (or equivalent HuggingFace model)
    """

    def __init__(self, model_name: str = 'EleutherAI/aria') -> None:
        self.model = None
        self.model_name = model_name
        self.index: Dict[str, np.ndarray] = {}

    def _load_model(self) -> None:
        if self.model is not None:
            return
        try:
            # TODO: Replace with actual AriaEmb import once package is available
            # from aria_embeddings import AriaEmbedder
            # self.model = AriaEmbedder.from_pretrained(self.model_name)
            raise ImportError(
                'AriaEmb not yet installed. Install from '
                'https://github.com/EleutherAI/aria or HuggingFace.'
            )
        except ImportError as exc:
            print(f'AriaEmb baseline unavailable: {exc}')
            raise

    def _embed_notes(self, notes: List[Dict], max_notes: int | None = None) -> np.ndarray:
        """Embed a note sequence using AriaEmb (truncated to max_notes for prefix tests)."""
        self._load_model()
        if max_notes is not None:
            notes = notes[:max_notes]
        # TODO: Tokenize notes into AriaEmb format and run forward pass
        raise NotImplementedError('AriaEmb embedding not yet connected')

    def build_index(self, piece_map: Dict[str, str]) -> None:
        """Build full-piece embedding index for nearest-neighbour retrieval."""
        self._load_model()
        for midi_file, piece_id in piece_map.items():
            midi = pretty_midi.PrettyMIDI(midi_file)
            if not midi.instruments:
                continue
            notes = [
                {'pitch': n.pitch, 'start': n.start, 'end': n.end, 'velocity': n.velocity}
                for n in sorted(midi.instruments[0].notes, key=lambda n: n.start)
            ]
            self.index[piece_id] = self._embed_notes(notes)

    def retrieve_at_prefix(
        self, query_notes: List[Dict], n_notes: int, top_k: int = 20,
    ) -> List[Dict[str, float]]:
        """Retrieve using only the first n_notes of the query.

        Key protocol: measure retrieval accuracy at N = 5, 10, 15, 20, 30
        notes to establish the AriaEmb baseline for prefix identification.
        """
        query_embedding = self._embed_notes(query_notes, max_notes=n_notes)
        results = []
        for piece_id, piece_embedding in self.index.items():
            sim = cosine_similarity(query_embedding, piece_embedding)
            results.append({'piece': piece_id, 'score': sim})
        results.sort(key=lambda r: r['score'], reverse=True)
        return results[:top_k]

    def run_prefix_evaluation(
        self,
        test_queries: Dict[str, List[Dict]],
        prefix_sizes: tuple = (5, 10, 15, 20, 30),
    ) -> Dict[int, Dict[str, float]]:
        """Compute MRR and recall at each prefix size.

        Args:
            test_queries: {piece_id: notes} for ground-truth pieces.
            prefix_sizes: Tuple of N values to test.

        Returns:
            {N: {'mrr': float, 'recall_at_1': float, 'recall_at_10': float}}
        """
        results = {}
        for n in prefix_sizes:
            reciprocal_ranks = []
            hits_at_1 = 0
            hits_at_10 = 0
            for true_id, notes in test_queries.items():
                if len(notes) < n:
                    continue
                retrieved = self.retrieve_at_prefix(notes, n_notes=n, top_k=20)
                retrieved_ids = [r['piece'] for r in retrieved]
                if true_id in retrieved_ids:
                    rank = retrieved_ids.index(true_id) + 1
                    reciprocal_ranks.append(1.0 / rank)
                    if rank == 1:
                        hits_at_1 += 1
                    if rank <= 10:
                        hits_at_10 += 1
                else:
                    reciprocal_ranks.append(0.0)

            total = len(reciprocal_ranks) or 1
            results[n] = {
                'mrr': sum(reciprocal_ranks) / total,
                'recall_at_1': hits_at_1 / total,
                'recall_at_10': hits_at_10 / total,
                'n_queries': len(reciprocal_ranks),
            }
        return results


class HybridPieceIdentifier:
    def __init__(self, fingerprinter: SimpleNGramFingerprinter | None = None):
        self.fingerprinter = fingerprinter or SimpleNGramFingerprinter(n=4)
        self.coarse_retriever = StatisticalCoarseRetriever()

    def build_indices(self, midi_files: Sequence[str], metadata_map: Dict[str, str] | None = None) -> None:
        piece_map = {}
        for midi_file in midi_files:
            piece_id = os.path.basename(midi_file)
            if metadata_map and piece_id in metadata_map:
                piece_id = metadata_map[piece_id]
            piece_map[midi_file] = piece_id

        self.coarse_retriever.build_index(piece_map)
        self.fingerprinter.build_database(midi_files, metadata_map)

    def rerank_candidates(self, query_midi_file: str, candidate_piece_ids: Sequence[str], top_k: int = 3) -> List[Dict[str, float]]:
        candidate_piece_ids = set(candidate_piece_ids)
        query_fingerprints = self.fingerprinter.extract_fingerprints(query_midi_file)
        if not query_fingerprints:
            return []

        matches: Dict[str, int] = {}
        matched_fingerprints = 0

        for fingerprint_hash, _ in query_fingerprints:
            if fingerprint_hash not in self.fingerprinter.database:
                continue

            candidate_hits = [
                piece_id
                for piece_id in self.fingerprinter.database[fingerprint_hash]
                if piece_id in candidate_piece_ids
            ]
            if not candidate_hits:
                continue

            matched_fingerprints += 1
            for piece_id in candidate_hits:
                matches[piece_id] = matches.get(piece_id, 0) + 1

        ranked = sorted(matches.items(), key=lambda row: row[1], reverse=True)
        results = []
        for rank, (piece_id, match_count) in enumerate(ranked[:top_k], start=1):
            confidence = 0.0 if matched_fingerprints == 0 else (match_count / matched_fingerprints) * 100
            coverage = 0.0 if not query_fingerprints else (matched_fingerprints / len(query_fingerprints)) * 100
            results.append(
                {
                    'rank': rank,
                    'piece': piece_id,
                    'matches': match_count,
                    'confidence': round(confidence, 1),
                    'coverage': round(coverage, 1),
                }
            )

        return results

    def identify(self, query_midi_file: str, top_k: int = 3, coarse_top_k: int = 20) -> List[Dict[str, float]]:
        if self.coarse_retriever.index:
            coarse_results = self.coarse_retriever.retrieve(query_midi_file, top_k=coarse_top_k)
            candidate_piece_ids = [row['piece'] for row in coarse_results]
            reranked = self.rerank_candidates(query_midi_file, candidate_piece_ids, top_k=top_k)
            coarse_scores = {row['piece']: row['coarse_score'] for row in coarse_results}

            for result in reranked:
                result['coarse_score'] = round(coarse_scores.get(result['piece'], 0.0), 4)

            if reranked:
                return reranked

        return self.fingerprinter.identify(query_midi_file, top_k=top_k)
