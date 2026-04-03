"""
Two-Stage Predictive Just Intonation Tuning Server

Stage 1: N-gram fingerprint identification
Stage 2: Parangonar score following with MusicXML key signatures
"""

import math
import os
import pickle
import sys
import tempfile
import time
from collections import deque
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pretty_midi
import torch
from flask import Flask, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit

sys.path.insert(0, 'MIDI-Zero-main')
from harmonic_context_runtime import HarmonicContextRuntime
from hybrid_piece_identifier import HybridPieceIdentifier
from simple_ngram_fingerprinting import SimpleNGramFingerprinter

try:
    import parangonar as pa
    PARANGONAR_IMPORT_ERROR = None
except Exception as exc:
    pa = None
    PARANGONAR_IMPORT_ERROR = exc

try:
    import partitura as pt
    PARTITURA_IMPORT_ERROR = None
except Exception as exc:
    pt = None
    PARTITURA_IMPORT_ERROR = exc


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HARMONIC_CHECKPOINT = os.path.join(BASE_DIR, 'research_data', 'harmonic_context_model.pt')


# Key signature mapping (MusicXML fifths to key names)
FIFTHS_TO_MAJOR_KEY = {
    -7: 'Cb', -6: 'Gb', -5: 'Db', -4: 'Ab', -3: 'Eb', -2: 'Bb', -1: 'F',
    0: 'C', 1: 'G', 2: 'D', 3: 'A', 4: 'E', 5: 'B', 6: 'F#', 7: 'C#'
}

FIFTHS_TO_MINOR_KEY = {
    -7: 'Abm', -6: 'Ebm', -5: 'Bbm', -4: 'Fm', -3: 'Cm', -2: 'Gm', -1: 'Dm',
    0: 'Am', 1: 'Em', 2: 'Bm', 3: 'F#m', 4: 'C#m', 5: 'G#m', 6: 'D#m', 7: 'A#m'
}

KEY_TO_TONIC = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'Fb': 4,
    'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10,
    'Bb': 10, 'B': 11, 'Cb': 11,
    # Minor keys (same tonic pitch class, different mode)
    'Am': 9, 'A#m': 10, 'Bbm': 10, 'Bm': 11, 'Cm': 0, 'C#m': 1, 'Dbm': 1,
    'Dm': 2, 'D#m': 3, 'Ebm': 3, 'Em': 4, 'Fm': 5, 'F#m': 6, 'Gbm': 6,
    'Gm': 7, 'G#m': 8, 'Abm': 8
}

# 5-limit Just Intonation ratios
JI_RATIOS_MAJOR = {
    0: 1.0, 1: 16/15, 2: 9/8, 3: 6/5, 4: 5/4, 5: 4/3,
    6: 45/32, 7: 3/2, 8: 8/5, 9: 5/3, 10: 9/5, 11: 15/8
}

JI_RATIOS_MINOR = {
    0: 1.0, 1: 16/15, 2: 9/8, 3: 6/5, 4: 5/4, 5: 4/3,
    6: 45/32, 7: 3/2, 8: 8/5, 9: 5/3, 10: 16/9, 11: 15/8
}


class SystemState(Enum):
    """System state machine for two-stage processing"""
    IDLE = "idle"
    COLLECTING = "collecting_midi"
    IDENTIFYING = "identifying_piece"
    IDENTIFIED = "piece_identified"
    SCORE_FOLLOWING = "score_following_active"
    ERROR = "error_state"


class TwoStageSystem:
    """Fingerprint identification + Parangonar score following with MusicXML keys."""
    
    def __init__(
        self,
        fingerprint_db_path: str,
        score_mapping_path: str,
        atepp_path: str,
        coarse_index_path: Optional[str] = None,
        harmonic_checkpoint_path: Optional[str] = None,
        harmonic_confidence_threshold: float = 0.60,
        harmonic_active_duration_ms: float = 500.0,
    ):
        self.state = SystemState.IDLE
        self.atepp_path = atepp_path
        
        # Load score mapping
        print("Loading score mapping...")
        with open(score_mapping_path, 'rb') as f:
            self.score_mapping = pickle.load(f)
        print(f"✓ Loaded score mapping for {len(self.score_mapping)} pieces")
        
        # Stage 1: Fingerprint identification
        print("Initializing Stage 1: Fingerprint Identification...")
        self.fingerprinter = SimpleNGramFingerprinter(n=4)
        self.fingerprinter.load_database(fingerprint_db_path)
        print(f"✓ Loaded {len(self.fingerprinter.database):,} fingerprints")
        self.hybrid_identifier = None
        if coarse_index_path and os.path.exists(coarse_index_path):
            print("Initializing hybrid coarse retrieval...")
            self.hybrid_identifier = HybridPieceIdentifier(self.fingerprinter)
            self.hybrid_identifier.coarse_retriever.load(coarse_index_path)
            print("✓ Loaded hybrid coarse index")
        
        # MIDI buffer for identification
        self.midi_buffer = deque(maxlen=500)
        self.identification_threshold = 30
        self.confidence_threshold = 30.0
        self.last_identification_attempt = 0
        self.identification_interval = 10.0
        self.identifying = False
        self.first_note_timestamp = None
        
        # Stage 2: Score following
        print("Initializing Stage 2: Score Following...")
        self.score_follower = None
        self.current_score = None
        self.current_position = 0
        self.identified_piece = None
        
        # Prediction and tuning
        self.predicted_notes = []
        self.current_tempo = 120.0
        self.performance_note_counter = 0
        self.parangonar_prepared = False
        self.prediction_session_id = 0
        self.current_prediction_session = None
        
        # Key signature handling
        self._partitura_ks_map = None
        self._beat_map = None
        self.key_signature_map = []
        self.current_key = None
        self.current_key_tonic = 0
        self.current_key_is_minor = False

        # Optional learned harmonic-state runtime for unknown pieces
        self.harmonic_runtime = None
        self.harmonic_active_duration_ms = max(50.0, float(harmonic_active_duration_ms))
        self.harmonic_active_notes: List[Tuple[float, int]] = []
        self.harmonic_last_prediction: Optional[Dict[str, object]] = None
        self.harmonic_last_inference_ms: Optional[float] = None
        self.harmonic_prediction_ttl_ms = 1500.0
        self._initialize_harmonic_runtime(
            harmonic_checkpoint_path=harmonic_checkpoint_path,
            confidence_threshold=harmonic_confidence_threshold,
        )

        if pt is None or pa is None:
            print("⚠️  Score-following dependencies unavailable")
            if pt is None:
                print(f"   Partitura import error: {PARTITURA_IMPORT_ERROR}")
            if pa is None:
                print(f"   Parangonar import error: {PARANGONAR_IMPORT_ERROR}")
        
        print("✓ Two-stage system initialized")
        print()
    
    def add_midi_note(self, pitch: int, velocity: int, timestamp: float):
        """Add MIDI note to buffer for identification"""
        if velocity > 0:  # Note on
            self.midi_buffer.append({
                'pitch': pitch,
                'timestamp': timestamp,
                'velocity': velocity
            })
            
            # Update state
            if self.state == SystemState.IDLE:
                self.state = SystemState.COLLECTING

    def _initialize_harmonic_runtime(self, harmonic_checkpoint_path: Optional[str], confidence_threshold: float) -> None:
        checkpoint_path = harmonic_checkpoint_path or DEFAULT_HARMONIC_CHECKPOINT
        runtime = HarmonicContextRuntime(
            checkpoint_path=checkpoint_path,
            confidence_threshold=confidence_threshold,
            device='cpu',
        )

        try:
            if runtime.load():
                self.harmonic_runtime = runtime
                print("Initializing optional harmonic-state runtime...")
                print(f"✓ Loaded harmonic checkpoint: {checkpoint_path}")
                print(f"  Harmonic confidence threshold: {confidence_threshold:.2f}")
            else:
                print("Optional harmonic-state runtime disabled (checkpoint not found)")
                print(f"  Expected checkpoint: {checkpoint_path}")
        except Exception as exc:
            self.harmonic_runtime = None
            print(f"⚠️  Harmonic runtime unavailable: {exc}")

    def get_active_harmonic_prediction(self) -> Optional[Dict[str, object]]:
        if not self.harmonic_last_prediction:
            return None

        age_ms = (time.time() - float(self.harmonic_last_prediction['timestamp'])) * 1000.0
        if age_ms > self.harmonic_prediction_ttl_ms:
            return None
        return self.harmonic_last_prediction

    def update_harmonic_prediction(self, pitch: int, velocity: int, timestamp: float) -> Optional[Dict[str, object]]:
        if self.harmonic_runtime is None or self.state == SystemState.SCORE_FOLLOWING:
            return None

        current_time_ms = float(timestamp) * 1000.0
        self.harmonic_active_notes = [
            (end_time_ms, active_pitch)
            for end_time_ms, active_pitch in self.harmonic_active_notes
            if end_time_ms > current_time_ms
        ]
        active_notes = [active_pitch for _, active_pitch in self.harmonic_active_notes]
        self.harmonic_runtime.add_note(pitch, velocity, current_time_ms, active_notes)
        self.harmonic_active_notes.append((current_time_ms + self.harmonic_active_duration_ms, int(pitch)))

        inference_started = time.perf_counter()
        prediction = self.harmonic_runtime.predict()
        self.harmonic_last_inference_ms = round((time.perf_counter() - inference_started) * 1000.0, 3)

        if prediction is None:
            return None

        payload = {
            **prediction,
            'timestamp': float(timestamp),
            'latency_ms': self.harmonic_last_inference_ms,
            'event_count': len(self.harmonic_runtime.note_events),
        }
        self.harmonic_last_prediction = payload
        return payload
    
    def should_attempt_identification(self) -> bool:
        """Check if enough data collected for identification"""
        current_time = time.time()
        
        # Criteria:
        # 1. Enough notes collected
        # 2. Enough time passed since last attempt
        # 3. Not already identified
        # 4. Not currently identifying (prevent race condition)
        
        sufficient_notes = len(self.midi_buffer) >= self.identification_threshold
        sufficient_interval = (current_time - self.last_identification_attempt) >= self.identification_interval
        not_identified = self.state not in [SystemState.IDENTIFIED, SystemState.SCORE_FOLLOWING]
        not_currently_identifying = not self.identifying
        
        return sufficient_notes and sufficient_interval and not_identified and not_currently_identifying
    
    def attempt_identification(self) -> Optional[Dict]:
        """Attempt to identify piece from current buffer."""
        if self.identifying:
            return {'success': False, 'reason': 'Identification already in progress'}
        
        self.identifying = True
        self.last_identification_attempt = time.time()
        self.state = SystemState.IDENTIFYING
        
        temp_midi_path = None
        try:
            # Convert buffer to temporary MIDI file
            temp_midi_path = self._buffer_to_midi_file(self.midi_buffer)
            
            # Check if buffer was sufficient
            if not temp_midi_path:
                return {'success': False, 'reason': 'Insufficient notes in buffer'}
            
            # Identify using hybrid retrieval when available, otherwise exact fingerprints
            if self.hybrid_identifier is not None:
                results = self.hybrid_identifier.identify(temp_midi_path, top_k=3)
            else:
                results = self.fingerprinter.identify(temp_midi_path, top_k=3)
            
            # Clean up temp file
            if temp_midi_path and os.path.exists(temp_midi_path):
                os.remove(temp_midi_path)
                temp_midi_path = None
            
            if results and results[0]['confidence'] >= self.confidence_threshold:
                # Confident identification!
                self.identified_piece = results[0]
                self.state = SystemState.IDENTIFIED
                
                print(f"✓ Identified: {self.identified_piece['piece']}")
                print(f"  Confidence: {self.identified_piece['confidence']}%")
                

                # Check if MusicXML score available
                has_score = self._check_score_availability(self.identified_piece["piece"])
                print(f"  MusicXML score: {'Yes' if has_score else 'No'}")

                return {
                    'success': True,
                    'piece': self.identified_piece['piece'],
                    'confidence': self.identified_piece['confidence'],
                    'alternatives': results[1:3],
                    'score_available': has_score
                }
            else:
                # Not confident enough
                return {
                    'success': False,
                    'reason': 'Low confidence',
                    'best_guess': results[0] if results else None
                }
                
        except Exception as e:
            self.state = SystemState.ERROR
            print(f"✗ Identification error: {e}")
            return {'success': False, 'reason': str(e)}
        finally:
            # Always reset identifying flag
            self.identifying = False
            # Ensure temp file is always cleaned up
            if temp_midi_path and os.path.exists(temp_midi_path):
                try:
                    os.remove(temp_midi_path)
                except Exception as cleanup_error:
                    print(f"Warning: Failed to clean up temp file: {cleanup_error}")
    
    def _buffer_to_midi_file(self, buffer: List[Dict]) -> str:
        """Convert MIDI buffer to temp file (normalizes timestamps to start from 0)"""
        if not buffer:
            return None
        
        midi = pretty_midi.PrettyMIDI()
        instrument = pretty_midi.Instrument(program=0)
        
        min_timestamp = min(note['timestamp'] for note in buffer)
        for note_data in buffer:
            relative_start = note_data['timestamp'] - min_timestamp
            note = pretty_midi.Note(
                velocity=note_data['velocity'],
                pitch=note_data['pitch'],
                start=relative_start,
                end=relative_start + 0.5
            )
            instrument.notes.append(note)
        
        midi.instruments.append(instrument)
        temp_path = tempfile.mktemp(suffix='.mid')
        midi.write(temp_path)
        return temp_path
    
    def initialize_score_following(self) -> bool:
        """Initialize Parangonar score follower (requires MusicXML score)"""
        if not self.identified_piece:
            return False

        if pt is None or pa is None:
            print("⚠️  Score following unavailable due to missing or broken dependencies")
            if pt is None:
                print(f"   Partitura import error: {PARTITURA_IMPORT_ERROR}")
            if pa is None:
                print(f"   Parangonar import error: {PARANGONAR_IMPORT_ERROR}")
            return False
        
        try:
            # Find MusicXML score using metadata mapping
            score_info = self._find_musicxml_score(self.identified_piece['piece'])
            
            if not score_info:
                print(f"⚠️  No MusicXML score available for: {self.identified_piece['piece']}")
                print(f"   Score following not possible (falling back to reactive tuning)")
                return False
            
            score_path = score_info['score_path']
            print(f"Loading MusicXML score: {os.path.basename(score_path)}")
            
            # CRITICAL FIX: Load MusicXML score (NOT MIDI performance!)
            score = pt.load_score(score_path)  # Loads .musicxml or .mxl
            
            # Get the Part object for key signature extraction
            part = score[0]
            
            # Get score note array (includes grace notes for Parangonar)
            score_array = part.note_array(include_grace_notes=True)
            
            print(f"  ✓ Loaded MusicXML score")
            print(f"  ✓ Score notes: {len(score_array)}")
            
            # Extract key signatures from MusicXML
            self.key_signature_map = self._extract_key_signatures(part)
            print(f"  ✓ Extracted {len(self.key_signature_map)} key signature(s)")
            
            # Log key signature information
            if self.key_signature_map:
                first_key = self.key_signature_map[0]
                self.current_key = first_key[1]
                self.current_key_tonic = first_key[2]
                self.current_key_is_minor = first_key[3]
                print(f"  ✓ Initial key: {self.current_key} ({'minor' if self.current_key_is_minor else 'major'})")
                
                if len(self.key_signature_map) > 1:
                    print(f"  ✓ Key changes in piece:")
                    for onset, key_name, tonic, is_minor in self.key_signature_map[:5]:
                        print(f"      Beat {onset:.1f}: {key_name}")
            
            # Initialize Parangonar RL matcher
            # This aligns user's live performance → MusicXML score
            self.score_follower = pa.OnlineTransformerMatcher(score_array)
            self.current_score = score_array
            self.current_position = 0
            self.performance_note_counter = 0
            self.parangonar_prepared = False
            self.first_note_timestamp = None
            self.prediction_session_id += 1
            self.current_prediction_session = self.prediction_session_id
            
            self.state = SystemState.SCORE_FOLLOWING
            
            print(f"✓ Parangonar score following initialized")
            print(f"  Ready to track position in real-time")
            
            return True
            
        except Exception as e:
            print(f"✗ Score following initialization error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _find_musicxml_score(self, piece_name: str) -> Optional[Dict]:
        """Find MusicXML score file for identified piece"""
        for midi_filename, score_info in self.score_mapping.items():
            full_name = f"{score_info['composer']}: {score_info['track']}"
            if full_name in piece_name or piece_name in full_name:
                if os.path.exists(score_info['score_path']):
                    return score_info
        return None
    
    def _check_score_availability(self, piece_name: str) -> bool:
        """Quick check if MusicXML score exists for piece"""
        return self._find_musicxml_score(piece_name) is not None
    
    def _extract_key_signatures(self, score_part) -> List[Tuple]:
        """Extract key signatures from MusicXML using partitura's key_signature_map."""
        key_map = []
        
        try:
            # Store beat_map for time conversions (divisions ↔ beats)
            if hasattr(score_part, 'beat_map'):
                self._beat_map = score_part.beat_map
            
            # PRIMARY METHOD: Use Partitura's built-in key_signature_map
            # This is efficient - uses interpolation, handles defaults
            if hasattr(score_part, 'key_signature_map'):
                self._partitura_ks_map = score_part.key_signature_map
                print("  ✓ Using Partitura's built-in key_signature_map (efficient)")
                
                # Still build the list for UI display and logging
                # Extract key signatures for display purposes
                if hasattr(score_part, 'key_sigs') and score_part.key_sigs:
                    for ks in score_part.key_sigs:
                        # Correctly access start time from TimePoint object
                        onset_div = ks.start.t if ks.start is not None else 0
                        fifths = ks.fifths
                        mode = ks.mode if ks.mode else 'major'
                        
                        is_minor = str(mode).lower() in ['minor', 'min', 'm']
                        
                        if is_minor:
                            key_name = FIFTHS_TO_MINOR_KEY.get(fifths, 'Am')
                        else:
                            key_name = FIFTHS_TO_MAJOR_KEY.get(fifths, 'C')
                        
                        tonic = KEY_TO_TONIC.get(key_name, 0)
                        key_map.append((float(onset_div), key_name, tonic, is_minor))
                else:
                    # No explicit key signatures, partitura defaults to C major
                    key_map.append((0.0, 'C', 0, False))
                    print("  ⚠️  No key signatures found in MusicXML, partitura defaults to C major")
            
            # FALLBACK: Manual extraction using iter_all
            elif hasattr(score_part, 'iter_all'):
                print("  ⚠️  key_signature_map not available, using manual extraction")
                import partitura.score as pt_score
                
                for element in score_part.iter_all(pt_score.KeySignature):
                    # Correctly access start time from TimePoint object
                    onset_div = element.start.t if element.start is not None else 0
                    fifths = element.fifths
                    mode = element.mode if element.mode else 'major'
                    
                    is_minor = str(mode).lower() in ['minor', 'min', 'm']
                    
                    if is_minor:
                        key_name = FIFTHS_TO_MINOR_KEY.get(fifths, 'Am')
                    else:
                        key_name = FIFTHS_TO_MAJOR_KEY.get(fifths, 'C')
                    
                    tonic = KEY_TO_TONIC.get(key_name, 0)
                    key_map.append((float(onset_div), key_name, tonic, is_minor))
            
            # Fallback if still empty
            if not key_map:
                key_map.append((0.0, 'C', 0, False))
                print("  ⚠️  No key signatures found, defaulting to C major")
        
        except Exception as e:
            print(f"  ⚠️  Error extracting key signatures: {e}")
            import traceback
            traceback.print_exc()
            # Default to C major
            key_map.append((0.0, 'C', 0, False))
            self._partitura_ks_map = None
        
        # Sort by onset time (divisions)
        key_map.sort(key=lambda x: x[0])
        
        return key_map
    
    def _get_key_at_position(self, position: int) -> Tuple[str, int, bool]:
        """Get key signature at given score position."""
        # Default fallback
        if self.current_score is None or position >= len(self.current_score):
            if self.key_signature_map:
                return self.key_signature_map[-1][1:]  # Return last key
            return ('C', 0, False)
        
        # Get onset time in divisions (the native partitura unit)
        # Note: note_array has 'onset_div' as the primary time unit
        score_fields = self.current_score.dtype.names if hasattr(self.current_score, 'dtype') else ()
        
        # Try onset_div first (native partitura unit), then onset_beat
        if 'onset_div' in score_fields:
            current_onset = float(self.current_score[position]['onset_div'])
        elif 'onset_beat' in score_fields:
            current_onset = float(self.current_score[position]['onset_beat'])
            # If using onset_beat but partitura_ks_map expects divisions,
            # we need to convert - but this should rarely happen with proper setup
        else:
            # Fallback to position index
            current_onset = float(position)
        
        # PRIMARY: Use Partitura's efficient key_signature_map callable
        if self._partitura_ks_map is not None:
            try:
                # key_signature_map returns (fifths, mode_int) 
                # mode_int: 1 = major, -1 = minor
                result = self._partitura_ks_map(current_onset)
                fifths = int(round(result[0]))
                mode_int = int(round(result[1]))
                
                is_minor = (mode_int == -1)
                
                if is_minor:
                    key_name = FIFTHS_TO_MINOR_KEY.get(fifths, 'Am')
                else:
                    key_name = FIFTHS_TO_MAJOR_KEY.get(fifths, 'C')
                
                tonic = KEY_TO_TONIC.get(key_name, 0)
                return (key_name, tonic, is_minor)
                
            except Exception as e:
                # Fall through to binary search fallback
                print(f"  ⚠️  Partitura key lookup error at position {position}: {e}")
        
        # FALLBACK: Binary search on key_signature_map list
        if not self.key_signature_map:
            return ('C', 0, False)
        
        # Binary search for the most recent key change
        left, right = 0, len(self.key_signature_map) - 1
        result_idx = 0
        
        while left <= right:
            mid = (left + right) // 2
            if self.key_signature_map[mid][0] <= current_onset:
                result_idx = mid
                left = mid + 1
            else:
                right = mid - 1
        
        return self.key_signature_map[result_idx][1:]  # (key_name, tonic, is_minor)
    
    def _predict_upcoming_keys(self, current_position: int, lookahead_notes: int = 20) -> List[Dict]:
        """Predict upcoming key changes based on score position."""
        upcoming_keys = []
        
        # Need either partitura callable or fallback list
        if (self._partitura_ks_map is None and not self.key_signature_map) or self.current_score is None:
            return upcoming_keys
        
        # Get current key
        current_key, current_tonic, current_is_minor = self._get_key_at_position(current_position)
        
        # Look ahead in the score for key changes
        end_position = min(current_position + lookahead_notes, len(self.current_score))
        
        # Determine available time fields
        score_fields = self.current_score.dtype.names if hasattr(self.current_score, 'dtype') else ()
        
        for pos in range(current_position, end_position):
            key_name, tonic, is_minor = self._get_key_at_position(pos)
            
            # Check if key changes
            if key_name != current_key:
                # Get onset time - prefer onset_beat, fallback to onset_div
                if 'onset_beat' in score_fields:
                    onset_time = float(self.current_score[pos]['onset_beat'])
                elif 'onset_div' in score_fields:
                    onset_time = float(self.current_score[pos]['onset_div'])
                else:
                    onset_time = float(pos)
                
                upcoming_keys.append({
                    'position': pos,
                    'onset_beat': onset_time,
                    'key': key_name,
                    'tonic': tonic,
                    'is_minor': is_minor,
                    'notes_until_change': pos - current_position
                })
                current_key = key_name  # Update for next comparison
        
        return upcoming_keys
    
    def update_position(self, performed_note: Dict) -> Optional[Dict]:
        """Update score position with incoming note using Parangonar."""
        if self.state != SystemState.SCORE_FOLLOWING or not self.score_follower:
            return None
        
        try:
            # Track first note timestamp for relative timing
            if self.first_note_timestamp is None:
                self.first_note_timestamp = performed_note['timestamp']
            
            relative_time = performed_note['timestamp'] - self.first_note_timestamp
            
            # Build live performance note dict for Parangonar
            perf_note = {
                'id': f"live_{self.performance_note_counter}",
                'pitch': performed_note['pitch'],
                'onset_sec': relative_time,
                'duration_sec': 0.5,
                'velocity': performed_note['velocity']
            }
            self.performance_note_counter += 1
            
            if not self.parangonar_prepared and self.score_follower:
                try:
                    self.score_follower.prepare_performance(perf_note['onset_sec'])
                except Exception as prep_error:
                    print(f"Parangonar preparation warning: {prep_error}")
                self.parangonar_prepared = True
            
            # Use Parangonar's online matching (RL agent)
            try:
                alignment = self.score_follower.online(perf_note)
                if alignment is not None and 'score_idx' in alignment:
                    self.current_position = int(alignment['score_idx'])
                else:
                    self.current_position = min(self.current_position + 1, len(self.current_score) - 1)
            except Exception as parangonar_error:
                print(f"Parangonar alignment error (using fallback): {parangonar_error}")
                self.current_position = min(self.current_position + 1, len(self.current_score) - 1)
            
            # Ensure position is within bounds
            self.current_position = max(0, min(self.current_position, len(self.current_score) - 1))
            
            # Calculate progress with division by zero protection
            total_notes = len(self.current_score)
            progress = self.current_position / total_notes if total_notes > 0 else 0.0
            
            return {
                'position': self.current_position,
                'total_notes': total_notes,
                'progress': progress
            }
            
        except Exception as e:
            print(f"Position update error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def predict_upcoming_notes(self, lookahead_seconds: float = 2.0) -> List[Dict]:
        """Predict upcoming notes with key signature info."""
        if (
            self.state != SystemState.SCORE_FOLLOWING
            or self.current_score is None
            or len(self.current_score) == 0
        ):
            return []
        
        # Bounds check
        if self.current_position >= len(self.current_score):
            return []
        
        # Calculate how many notes fit in lookahead time
        seconds_per_note = 60.0 / (self.current_tempo * 4)  # Assuming 16th notes
        num_notes = int(lookahead_seconds / seconds_per_note)
        
        # Extract upcoming notes from score
        predicted = []
        end_pos = min(self.current_position + num_notes, len(self.current_score))
        
        score_fields = self.current_score.dtype.names if hasattr(self.current_score, 'dtype') else ()
        session_id = self.current_prediction_session or "pending"
        
        for i in range(self.current_position, end_pos):
            if i >= len(self.current_score):
                break
            note = self.current_score[i]
            offset = (i - self.current_position) * seconds_per_note
            note_id = f"{session_id}_{i}"
            
            duration = 0.5
            if score_fields:
                if 'duration_quarter' in score_fields:
                    duration = float(note['duration_quarter'])
                elif 'duration_beat' in score_fields:
                    duration = float(note['duration_beat'])
                elif 'duration_div' in score_fields:
                    duration = float(note['duration_div'])
            
            # Get key signature at this note's position
            key_name, tonic, is_minor = self._get_key_at_position(i)
            
            predicted.append({
                'note_id': note_id,
                'pitch': int(note['pitch']),
                'position': i,  # Score position for key lookup
                'time_offset': offset,
                'duration': duration,
                'key': key_name,  # Key signature from MusicXML
                'is_minor': is_minor
            })
        
        return predicted
    
    def calculate_ji_ratios(self, predicted_notes: List[Dict]) -> Dict[int, float]:
        """Calculate JI ratios using MusicXML key signatures."""
        if not predicted_notes:
            return {}
        
        tuning_table: Dict[int, List[Dict]] = {}
        current_timestamp = time.time()
        
        for note in predicted_notes:
            pitch = note['pitch']
            note_position = note.get('position', self.current_position)
            
            # Get the actual key signature at this note's position from MusicXML
            key_name, tonic, is_minor = self._get_key_at_position(note_position)
            
            # Update current key tracking
            if key_name != self.current_key:
                self.current_key = key_name
                self.current_key_tonic = tonic
                self.current_key_is_minor = is_minor
            
            # Select appropriate JI ratios based on mode (major vs minor)
            ji_ratios = JI_RATIOS_MINOR if is_minor else JI_RATIOS_MAJOR
            
            # Calculate scale degree relative to the ACTUAL tonic from MusicXML
            scale_degree = (pitch - tonic) % 12
            ratio = ji_ratios.get(scale_degree, 1.0)
            
            # Calculate cents offset from equal temperament
            # JI ratio gives the frequency ratio from tonic
            # Cents offset = (JI cents) - (ET cents for that scale degree)
            cents_offset = 1200 * math.log2(ratio) - (scale_degree * 100)
            
            tuning_table.setdefault(pitch, []).append({
                'note_id': note.get('note_id'),
                'ratio': ratio,
                'cents': round(cents_offset, 2),
                'scale_degree': scale_degree,
                'tonic_pc': tonic,
                'key': key_name,
                'is_minor': is_minor,
                'source': 'musicxml_key_signature',  # Indicates this came from score analysis
                'timestamp': current_timestamp
            })
        
        return tuning_table
    
    def get_status(self) -> Dict:
        """Get current system status including key signature information"""
        # Determine tuning source
        has_partitura_map = self._partitura_ks_map is not None
        has_fallback_list = len(self.key_signature_map) > 0
        active_harmonic_prediction = self.get_active_harmonic_prediction()
        
        if has_partitura_map:
            tuning_source = 'musicxml_partitura'  # Using efficient partitura callable
        elif has_fallback_list:
            tuning_source = 'musicxml_fallback'  # Using manual list extraction
        else:
            tuning_source = 'client_fallback'  # No MusicXML, rely on client
        
        return {
            'state': self.state.value,
            'buffer_size': len(self.midi_buffer),
            'identified_piece': self.identified_piece.get('piece') if self.identified_piece else None,
            'confidence': self.identified_piece.get('confidence', 0) if self.identified_piece else 0,
            'position': self.current_position if self.score_follower else 0,
            'score_length': len(self.current_score) if self.current_score is not None else 0,
            # Key signature information
            'current_key': self.current_key,
            'current_key_is_minor': self.current_key_is_minor,
            'key_signature_count': len(self.key_signature_map),
            'tuning_source': tuning_source,
            'partitura_ks_map_available': has_partitura_map,
            'harmonic_runtime_available': self.harmonic_runtime is not None,
            'harmonic_current_key': active_harmonic_prediction['key'] if active_harmonic_prediction else None,
            'harmonic_current_confidence': active_harmonic_prediction['confidence'] if active_harmonic_prediction else None,
            'harmonic_last_inference_ms': self.harmonic_last_inference_ms,
        }
    
    def reset(self):
        """Reset system to initial state"""
        self.midi_buffer.clear()
        self.score_follower = None
        self.current_score = None
        self.current_position = 0
        self.identified_piece = None
        self.predicted_notes = []
        self.first_note_timestamp = None
        self.identifying = False
        self.performance_note_counter = 0
        self.parangonar_prepared = False
        self.current_prediction_session = None
        self.last_identification_attempt = 0  # Reset to allow immediate re-identification
        # Reset key signature data
        self._partitura_ks_map = None  # Clear partitura callable
        self._beat_map = None  # Clear time conversion map
        self.key_signature_map = []
        self.current_key = None
        self.current_key_tonic = 0
        self.current_key_is_minor = False
        self.harmonic_active_notes = []
        self.harmonic_last_prediction = None
        self.harmonic_last_inference_ms = None
        if self.harmonic_runtime is not None:
            self.harmonic_runtime.reset()
        self.state = SystemState.IDLE
        print("✓ System reset")


# Global system instance
system = None
# Track connected clients to handle disconnects properly
connected_clients = set()
last_disconnect_time = 0


@socketio.on('connect')
def handle_connect():
    global connected_clients, last_disconnect_time
    client_id = request.sid
    connected_clients.add(client_id)
    print(f'Client connected (total: {len(connected_clients)})')
    
    # Check if this is a quick reconnect (within 5 seconds)
    SESSION_GRACE_PERIOD = 5.0  # seconds
    time_since_disconnect = time.time() - last_disconnect_time if last_disconnect_time > 0 else float('inf')
    
    # If system was in active state from previous session, reset it
    # But allow quick reconnects to preserve session
    if system and system.state in [SystemState.SCORE_FOLLOWING, SystemState.IDENTIFIED]:
        if time_since_disconnect > SESSION_GRACE_PERIOD:
            print('⚠️  Resetting stale system state from previous session')
            system.reset()
        else:
            print(f'✓  Quick reconnect detected ({time_since_disconnect:.1f}s) - preserving session')
    
    emit('status', {'message': 'Connected to two-stage server', 'state': system.state.value if system else 'not_initialized'})


@socketio.on('disconnect')
def handle_disconnect():
    global connected_clients, last_disconnect_time
    client_id = request.sid
    connected_clients.discard(client_id)
    print(f'Client disconnected (remaining: {len(connected_clients)})')
    
    # Track last disconnect time for grace period
    last_disconnect_time = time.time()
    
    # Reset system when last client disconnects (after grace period)
    # This ensures clean state for next session
    if len(connected_clients) == 0 and system:
        print('⚠️  Last client disconnected - resetting system state after grace period')
        system.reset()


@socketio.on('midi_note')
def handle_midi_note(data):
    """Handle incoming MIDI note"""
    global system
    
    if system is None:
        emit('error', {'message': 'System not initialized'})
        return
    
    try:
        pitch = data.get('pitch')
        velocity = data.get('velocity')
        timestamp = data.get('timestamp', time.time())
        
        # Validate inputs
        if pitch is None or not isinstance(pitch, int) or not (0 <= pitch <= 127):
            emit('error', {'message': f'Invalid pitch: {pitch}'})
            return
        if velocity is None or not isinstance(velocity, int) or not (0 <= velocity <= 127):
            emit('error', {'message': f'Invalid velocity: {velocity}'})
            return
        if not isinstance(timestamp, (int, float)) or timestamp < 0:
            emit('error', {'message': f'Invalid timestamp: {timestamp}'})
            return
        
        # Add to buffer
        system.add_midi_note(pitch, velocity, timestamp)

        # Optional learned harmonic-state prediction for unknown-piece path
        if len(connected_clients) > 0:
            harmonic_prediction = system.update_harmonic_prediction(pitch, velocity, timestamp)
            if harmonic_prediction is not None and system.state != SystemState.SCORE_FOLLOWING:
                emit('harmonic_prediction', harmonic_prediction)
        
        # Stage 1: Attempt identification if ready
        if system.should_attempt_identification():
            result = system.attempt_identification()
            
            if result and result.get('success'):
                # Successfully identified!
                emit('piece_identified', {
                    'piece': result['piece'],
                    'confidence': result['confidence'],
                    'alternatives': result.get('alternatives', [])
                })
                
                # Stage 2: Initialize score following (if score available)
                if result.get('score_available'):
                    if system.initialize_score_following():
                        emit('score_following_started', {
                            'piece': system.identified_piece['piece'],
                            'score_length': len(system.current_score),
                            # Key signature information from MusicXML
                            'initial_key': system.current_key,
                            'is_minor': system.current_key_is_minor,
                            'key_changes_count': len(system.key_signature_map),
                            'tuning_source': 'musicxml'
                        })
                    else:
                        emit('score_following_failed', {
                            'reason': 'Score loading failed',
                            'fallback': 'reactive_tuning'
                        })
                else:
                    # No MusicXML score available - inform user
                    emit('score_not_available', {
                        'piece': result['piece'],
                        'message': 'MusicXML score not available for this piece',
                        'fallback': 'Continuing with reactive Just Intonation tuning',
                        'note': '43.6% of ATEPP has scores - piece may not have one'
                    })
        
        # If score following active, update position
        # Only send updates if clients are connected (prevents stale state issues)
        if system.state == SystemState.SCORE_FOLLOWING and len(connected_clients) > 0:
            position_info = system.update_position({'pitch': pitch, 'timestamp': timestamp, 'velocity': velocity})
            
            if position_info:
                # Predict upcoming notes
                predicted = system.predict_upcoming_notes(lookahead_seconds=2.0)
                
                # Calculate JI ratios using actual key signatures from MusicXML
                ji_ratios = system.calculate_ji_ratios(predicted)
                
                # Predict upcoming key changes
                upcoming_key_changes = system._predict_upcoming_keys(
                    system.current_position, 
                    lookahead_notes=30
                )
                
                # Send to frontend with key information
                emit('position_update', {
                    'position': position_info['position'],
                    'total_notes': position_info['total_notes'],
                    'progress': position_info['progress'],
                    'predicted_notes': predicted[:5],  # Next 5 notes
                    'ji_ratios': ji_ratios,
                    # Key signature information from MusicXML
                    'current_key': system.current_key,
                    'current_key_is_minor': system.current_key_is_minor,
                    'upcoming_key_changes': upcoming_key_changes[:3],  # Next 3 key changes
                    'tuning_source': 'musicxml'
                })
        
        # Send status update
        emit('system_status', system.get_status())
        
    except Exception as e:
        print(f"Error handling MIDI note: {e}")
        emit('error', {'message': str(e)})


@socketio.on('reset')
def handle_reset():
    """Reset system to initial state"""
    global system
    if system:
        system.reset()
        # Send both status and system_status to ensure client gets clean state
        emit('status', {'message': 'System reset', 'state': 'idle'})
        emit('system_status', system.get_status())


@app.route('/health')
def health():
    """Health check endpoint"""
    return {
        'status': 'ok',
        'system_initialized': system is not None,
        'state': system.state.value if system else 'not_initialized'
    }


def initialize_system(
    fingerprint_db_path: str,
    score_mapping_path: str,
    atepp_path: str,
    coarse_index_path: Optional[str] = None,
    harmonic_checkpoint_path: Optional[str] = None,
    harmonic_confidence_threshold: float = 0.60,
    harmonic_active_duration_ms: float = 500.0,
):
    """Initialize the two-stage system"""
    global system
    try:
        system = TwoStageSystem(
            fingerprint_db_path,
            score_mapping_path,
            atepp_path,
            coarse_index_path=coarse_index_path,
            harmonic_checkpoint_path=harmonic_checkpoint_path,
            harmonic_confidence_threshold=harmonic_confidence_threshold,
            harmonic_active_duration_ms=harmonic_active_duration_ms,
        )
        print("✓ Two-stage system ready!")
        return True
    except Exception as e:
        print(f"✗ Initialization error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Two-Stage Predictive JI Tuning Server')
    parser.add_argument('--fingerprint-db', default='atepp_filtered_database.pkl',
                        help='Path to fingerprint database (filtered for scores)')
    parser.add_argument('--score-mapping', default='atepp_score_mapping.pkl',
                        help='Path to score mapping file')
    parser.add_argument('--coarse-index', default=None,
                        help='Optional path to hybrid coarse retrieval index')
    parser.add_argument('--harmonic-checkpoint', default=DEFAULT_HARMONIC_CHECKPOINT,
                        help='Optional harmonic-model checkpoint path for unknown-piece inference')
    parser.add_argument('--harmonic-threshold', type=float, default=0.60,
                        help='Confidence threshold for harmonic-model runtime emission')
    parser.add_argument('--harmonic-active-duration-ms', type=float, default=500.0,
                        help='Approximate active-note lifetime for backend harmonic inference')
    parser.add_argument('--atepp-path', default='ATEPP-1.2/ATEPP-1.2',
                        help='Path to ATEPP MIDI files')
    parser.add_argument('--port', type=int, default=5005,
                        help='Server port')
    
    args = parser.parse_args()
    
    print("="*70)
    print("TWO-STAGE PREDICTIVE JI TUNING SERVER")
    print("="*70)
    print(f"Fingerprint DB: {args.fingerprint_db}")
    print(f"Score mapping: {args.score_mapping}")
    print(f"Coarse index: {args.coarse_index or 'disabled'}")
    print(f"Harmonic checkpoint: {args.harmonic_checkpoint}")
    print(f"Harmonic threshold: {args.harmonic_threshold:.2f}")
    print(f"ATEPP path: {args.atepp_path}")
    print(f"Port: {args.port}")
    print("="*70)
    print()
    
    # Initialize system
    if not initialize_system(
        args.fingerprint_db,
        args.score_mapping,
        args.atepp_path,
        coarse_index_path=args.coarse_index,
        harmonic_checkpoint_path=args.harmonic_checkpoint,
        harmonic_confidence_threshold=args.harmonic_threshold,
        harmonic_active_duration_ms=args.harmonic_active_duration_ms,
    ):
        print("Failed to initialize system. Exiting.")
        sys.exit(1)
    
    # Start server
    print(f"\nStarting server on http://localhost:{args.port}")
    print("Press Ctrl+C to stop\n")
    
    socketio.run(app, host='0.0.0.0', port=args.port, debug=False, allow_unsafe_werkzeug=True)

