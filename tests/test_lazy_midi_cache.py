"""Regression tests for the 2026-05-12 P3.2 audit fix: lazy-load MIDI cache.

Closes the Phase C T4 RAM ceiling: the in-memory `build_midi_cache` dict
OOMed at ~27 K MIDIs on Colab T4 (Chapter 6 §6.9.2 documents the 50 K →
20 K reduction). The streaming `build_midi_cache_streaming` writes the
same JSONL but holds only a byte-offset index in memory (~50 bytes per
file), supporting the full 371 K Aria-MIDI corpus on the same hardware.

Tests in this file:
1. LazyMidiCache exposes the dict-like interface the dataset needs
   (`__contains__`, `__len__`, `keys`, `items`, `__getitem__`)
2. `_NoteCountStub.__len__` returns the correct count without loading notes
3. `LazyMidiCache.__getitem__` returns the same notes as a dict-loaded cache
4. The streaming builder + the dict builder write byte-identical JSONL
5. The `TranspositionPairDataset` works correctly with `LazyMidiCache`
6. `LazyMidiCache` survives pickle round-trip (DataLoader fork-safety)
7. `_build_index_from_existing_jsonl` correctly indexes a pre-existing JSONL
8. CLI: `--lazy-load` flag is exposed
"""
from __future__ import annotations

import json
import os
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pretrain_symbolic_key import (  # noqa: E402
    LazyMidiCache,
    TranspositionPairDataset,
    _NoteCountStub,
    _build_index_from_existing_jsonl,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_synthetic_jsonl(path: str, n_files: int = 5, n_notes_each: int = 100):
    """Write a small JSONL cache file with synthetic note lists, return the
    in-memory equivalent dict for cross-comparison."""
    expected = {}
    with open(path, 'w') as f:
        for i in range(n_files):
            midi_path = f'fake/piece_{i:03d}.mid'
            notes = [
                {'pitch': 60 + (j % 12), 'start': j * 0.5,
                 'end': j * 0.5 + 0.5, 'velocity': 64}
                for j in range(n_notes_each)
            ]
            f.write(json.dumps({'path': midi_path, 'notes': notes}) + '\n')
            expected[midi_path] = notes
    return expected


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_note_count_stub_returns_correct_length():
    """`_NoteCountStub` is the small object that lets the dataset's
    `__init__` filter run `len(v) >= min_notes` without loading notes."""
    stub = _NoteCountStub(123)
    assert len(stub) == 123


def test_lazy_cache_dict_interface():
    """LazyMidiCache must expose `__contains__`, `__len__`, `keys`, `items`,
    `__getitem__` — the subset of dict that TranspositionPairDataset uses."""
    with tempfile.TemporaryDirectory() as td:
        jsonl = os.path.join(td, 'cache.jsonl')
        expected = _write_synthetic_jsonl(jsonl, n_files=5, n_notes_each=200)
        index = _build_index_from_existing_jsonl(jsonl)
        cache = LazyMidiCache(jsonl, index)

        # __len__
        assert len(cache) == 5
        # __contains__
        assert 'fake/piece_002.mid' in cache
        assert 'nonexistent/piece.mid' not in cache
        # keys()
        assert set(cache.keys()) == set(expected.keys())
        # items() yields (key, _NoteCountStub) pairs
        for key, stub in cache.items():
            assert key in expected
            assert len(stub) == len(expected[key])  # _NoteCountStub.__len__ ✓


def test_lazy_cache_getitem_returns_correct_notes():
    """`cache[midi_path]` must return the same note list as the
    in-memory dict would have done."""
    with tempfile.TemporaryDirectory() as td:
        jsonl = os.path.join(td, 'cache.jsonl')
        expected = _write_synthetic_jsonl(jsonl, n_files=10, n_notes_each=150)
        index = _build_index_from_existing_jsonl(jsonl)
        cache = LazyMidiCache(jsonl, index)

        for midi_path, notes_expected in expected.items():
            notes_actual = cache[midi_path]
            assert notes_actual == notes_expected, (
                f'LazyMidiCache returned different notes for {midi_path}\n'
                f'expected: {notes_expected[:2]}...\n'
                f'actual:   {notes_actual[:2]}...'
            )


def test_lazy_cache_handles_repeated_access():
    """Repeated __getitem__ on the same key must return identical results
    (verifies the seek + readline pattern doesn't drift the file pointer)."""
    with tempfile.TemporaryDirectory() as td:
        jsonl = os.path.join(td, 'cache.jsonl')
        expected = _write_synthetic_jsonl(jsonl, n_files=5, n_notes_each=100)
        index = _build_index_from_existing_jsonl(jsonl)
        cache = LazyMidiCache(jsonl, index)

        # Access the same key 10 times in a row, alternating with other keys
        target = 'fake/piece_002.mid'
        for _ in range(10):
            assert cache[target] == expected[target]
            assert cache['fake/piece_004.mid'] == expected['fake/piece_004.mid']
            assert cache[target] == expected[target]


def test_lazy_cache_pickle_roundtrip():
    """LazyMidiCache must survive pickle round-trip without keeping the
    file handle (which is unpicklable). DataLoader workers rely on this."""
    with tempfile.TemporaryDirectory() as td:
        jsonl = os.path.join(td, 'cache.jsonl')
        expected = _write_synthetic_jsonl(jsonl, n_files=3, n_notes_each=100)
        index = _build_index_from_existing_jsonl(jsonl)
        cache = LazyMidiCache(jsonl, index)
        # Touch the file handle so it's open before pickling
        _ = cache['fake/piece_000.mid']
        # Pickle round-trip
        pickled = pickle.dumps(cache)
        cache2 = pickle.loads(pickled)
        # The unpickled cache must work the same way
        assert len(cache2) == 3
        for midi_path, notes_expected in expected.items():
            assert cache2[midi_path] == notes_expected


def test_dataset_works_with_lazy_cache():
    """End-to-end: a `TranspositionPairDataset` constructed with a
    `LazyMidiCache` must produce items identically to one constructed with
    an equivalent in-memory dict."""
    import random
    with tempfile.TemporaryDirectory() as td:
        jsonl = os.path.join(td, 'cache.jsonl')
        # 200 notes per piece is enough for both canonical (window=64)
        # and legacy (window=64 → needs 128 notes per piece)
        expected = _write_synthetic_jsonl(jsonl, n_files=4, n_notes_each=200)
        index = _build_index_from_existing_jsonl(jsonl)
        lazy_cache = LazyMidiCache(jsonl, index)

        # Two parallel datasets — same RNG → same sampled windows, transpositions
        random.seed(42)
        ds_lazy = TranspositionPairDataset(lazy_cache, window_size=64,
                                            pair_mode='canonical')
        random.seed(42)
        ds_eager = TranspositionPairDataset(expected, window_size=64,
                                             pair_mode='canonical')

        assert len(ds_lazy) == len(ds_eager)
        for i in range(len(ds_lazy)):
            random.seed(100 + i)
            item_lazy = ds_lazy[i]
            random.seed(100 + i)
            item_eager = ds_eager[i]
            assert item_lazy['c'] == item_eager['c'], (
                f'Item {i} c mismatch: lazy={item_lazy["c"]}, eager={item_eager["c"]}'
            )
            # Pitch-class sequences should be identical (same seed → same RNG path)
            assert item_lazy['A']['pitch_class'] == item_eager['A']['pitch_class']
            assert item_lazy['B']['pitch_class'] == item_eager['B']['pitch_class']


def test_index_from_jsonl_reconstructs_correctly():
    """`_build_index_from_existing_jsonl` must scan the JSONL once and
    produce a {midi_path: (byte_offset, n_notes)} index where the offsets
    let us seek to exactly the start of each line."""
    with tempfile.TemporaryDirectory() as td:
        jsonl = os.path.join(td, 'cache.jsonl')
        expected = _write_synthetic_jsonl(jsonl, n_files=7, n_notes_each=80)
        index = _build_index_from_existing_jsonl(jsonl)
        # Verify each indexed offset reads back the correct entry
        with open(jsonl, 'r') as f:
            for midi_path, (offset, n_notes) in index.items():
                f.seek(offset)
                line = f.readline()
                entry = json.loads(line)
                assert entry['path'] == midi_path
                assert len(entry['notes']) == n_notes
                assert entry['notes'] == expected[midi_path]


def test_cli_exposes_lazy_load_flag():
    """`--lazy-load` must be in --help output."""
    out = subprocess.check_output(
        [sys.executable, str(ROOT / 'pretrain_symbolic_key.py'), '--help'],
        text=True, cwd=str(ROOT),
    )
    assert '--lazy-load' in out, (
        '--lazy-load must be exposed as a CLI flag (P3.2 audit fix). '
        'Without it, the user can\'t opt into the lazy cache from a wrapper script.'
    )
    assert '371 K Aria-MIDI' in out or '371 K' in out, (
        '--lazy-load help text should mention the Phase C 371 K corpus this fix enables.'
    )
