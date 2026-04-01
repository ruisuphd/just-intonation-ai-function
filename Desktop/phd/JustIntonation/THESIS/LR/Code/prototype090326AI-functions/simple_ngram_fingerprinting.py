#!/usr/bin/env python3
"""
N-Gram Fingerprinting for ATEPP

Uses relative-interval n-grams for transposition-invariant piece identification,
with SHA-256 for deterministic, reproducible hashes across Python versions.

Reference: Baptista et al., "Piano Sheet Music Identification Using Dynamic
N-gram Fingerprinting" (TISMIR 2021, DOI:10.5334/tismir.70).
"""

import hashlib
import os
import pickle
from collections import defaultdict

import pretty_midi
from tqdm import tqdm


def get_midi_files(path):
    """Recursively find all MIDI files in directory."""
    midi_files = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.lower().endswith(('.mid', '.midi')):
                midi_files.append(os.path.join(root, file))
    return sorted(midi_files)


def _interval_hash(intervals: tuple) -> str:
    """Deterministic SHA-256 hash of an interval tuple (full 256-bit digest)."""
    return hashlib.sha256(str(intervals).encode('ascii')).hexdigest()


class SimpleNGramFingerprinter:
    """
    Transposition-invariant n-gram fingerprinting using relative intervals.

    Instead of absolute MIDI pitches, fingerprints encode the pitch
    intervals between consecutive notes (e.g., +4, +3, +5 for a major
    arpeggio). This makes identification robust to transposition.
    """

    def __init__(self, n=4):
        """
        Initialize fingerprinter.

        Args:
            n: Number of consecutive notes per fingerprint (default: 4).
               The resulting interval n-gram has (n-1) interval values.
        """
        self.n = n
        self.database = defaultdict(lambda: defaultdict(list))
        # database[fingerprint_hash][piece_id] = [position1, position2, ...]

    def extract_fingerprints(self, midi_file):
        """
        Extract relative-interval n-gram fingerprints from a MIDI file.

        Returns:
            List of (fingerprint_hash, position) tuples.
        """
        try:
            midi = pretty_midi.PrettyMIDI(midi_file)

            if len(midi.instruments) == 0:
                return []

            notes = sorted(midi.instruments[0].notes, key=lambda x: x.start)

            fingerprints = []

            for i in range(len(notes) - self.n + 1):
                pitches = [notes[j].pitch for j in range(i, i + self.n)]
                intervals = tuple(
                    pitches[k + 1] - pitches[k] for k in range(len(pitches) - 1)
                )

                fp_hash = _interval_hash(intervals)
                fingerprints.append((fp_hash, i))

            return fingerprints

        except Exception as e:
            print(f"Error processing {midi_file}: {e}")
            return []
    
    def add_to_database(self, piece_id, midi_file):
        """Add a piece to the fingerprint database"""
        fingerprints = self.extract_fingerprints(midi_file)
        
        for fp_hash, position in fingerprints:
            self.database[fp_hash][piece_id].append(position)
        
        return len(fingerprints)
    
    def build_database(self, midi_files, metadata_map=None):
        """
        Build fingerprint database from collection of MIDI files
        
        Args:
            midi_files: List of MIDI file paths
            metadata_map: Optional dict mapping filenames to composition names
        """
        print(f"Building fingerprint database for {len(midi_files)} pieces...")
        
        for midi_file in tqdm(midi_files, desc="Processing MIDI files"):
            piece_id = os.path.basename(midi_file)
            
            # Use metadata name if available
            if metadata_map and piece_id in metadata_map:
                piece_id = metadata_map[piece_id]
            
            num_fps = self.add_to_database(piece_id, midi_file)
        
        total_fps = len(self.database)
        print(f"✓ Database built: {total_fps:,} unique fingerprints")
        
        return self.database
    
    def identify(self, query_midi_file, top_k=3):
        """
        Identify piece from query MIDI
        
        Returns:
            List of (piece_id, match_count, confidence) tuples
        """
        # Extract query fingerprints
        query_fps = self.extract_fingerprints(query_midi_file)
        
        if len(query_fps) == 0:
            return []
        
        # Vote across database
        matches = defaultdict(int)
        matched_fps = 0  # number of query fingerprints that matched at least one piece
        
        for fp_hash, _ in query_fps:
            if fp_hash in self.database:
                matched_fps += 1
                # Each piece that contains this fingerprint gets a vote
                for piece_id in self.database[fp_hash]:
                    matches[piece_id] += 1
        
        # Sort by match count
        sorted_matches = sorted(matches.items(), key=lambda x: x[1], reverse=True)
        
        if not sorted_matches:
            return []
        
        results = []
        coverage = (matched_fps / len(query_fps)) * 100 if query_fps else 0.0
        
        for i, (piece_id, match_count) in enumerate(sorted_matches[:top_k]):
            # Confidence = share of matched fingerprints that voted for this piece
            confidence = (match_count / matched_fps) * 100 if matched_fps else 0.0
            results.append({
                'rank': i + 1,
                'piece': piece_id,
                'matches': match_count,
                'confidence': round(confidence, 1),
                'coverage': round(coverage, 1)
            })
        
        return results
    
    def save_database(self, filepath):
        """Save fingerprint database to file"""
        with open(filepath, 'wb') as f:
            pickle.dump(dict(self.database), f)
        print(f"✓ Database saved to {filepath}")
    
    def load_database(self, filepath):
        """Load fingerprint database from file"""
        with open(filepath, 'rb') as f:
            self.database = defaultdict(lambda: defaultdict(list), pickle.load(f))
        print(f"✓ Database loaded from {filepath}")


if __name__ == "__main__":
    print("Simple N-Gram Fingerprinting System")
    print("Run build_atepp_fingerprint_db.py or create_filtered_database.py to build database")

