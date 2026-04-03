# Baseline Audit

## Audit Scope

This document records the baseline system behavior at the start of the AI-enhancement phase.

The audit covers:

- live score-free tuning in `js/main.js` and `js/key-detection.js`
- score-aware predictive tuning in `two_stage_server.py` and `two_stage_client.js`
- exact retrieval in `simple_ngram_fingerprinting.py`
- offline MIDI tuning in `js/midi-file-tuner.js`
- note-level tuning output in `js/tuning-core.js`, `js/tuning-mts.js`, and `js/tuning-mpe.js`

## System Summary

The repository currently implements a hybrid system with two practical paths:

1. `score-free live path`
   The browser listens to MIDI note-ons, estimates a key from a recent note window, and applies fixed 5-limit JI ratios relative to that key.
2. `score-aware predictive path`
   The backend identifies a piece using exact n-gram fingerprints, loads the corresponding MusicXML, follows the score, and emits note-level JI predictions back to the frontend.

## Live Score-Free Path

### Entry Point

The live path starts in `handleNoteOn()` in `js/main.js`.

Observed behavior:

- note-ons are added to a sliding `keyDetectionBuffer`
- the live window is fixed at `2000 ms`
- key detection starts after at least `8` note events
- the frontend then applies tuning immediately before forwarding the note to internal audio or external MIDI

### Key Detection

`js/key-detection.js` implements an ensemble detector based on three published pitch-class profile families:

- Albrecht-Shanahan
- Temperley
- Krumhansl-Kessler

The detector now:

- builds a recency-weighted and velocity-weighted pitch-class histogram from the recent note window
- adds an explicit weight for currently active notes
- scores every major and minor key against all three profile families
- smooths combined key scores over time
- uses a hysteresis-style pending-candidate rule before switching keys

### Live Tuning Decision

After key detection, `applyTuning()` in `js/main.js` does the following:

- if predictive note-level tuning is available, use it
- otherwise fetch the current key from the key detector
- if no key is available, leave pitch bend at zero
- if a key is available, call `calculateJIPitchBend()` from `js/tuning-core.js`

This means the score-free live path is currently **key-based**, not chord-aware.

### Main Score-Free Limitations

The strengthened live detector is still a classical baseline, and its limitations remain clear:

- it still does not model chord function or Roman numeral relationships
- it still relies on pitch-class profile matching rather than learned harmonic structure
- its held-note modeling is still approximate
- it can be sensitive to ambiguity, tonicization, chromatic passages, and sparse textures
- the tuning decision is relative to tonic and mode only

## Score-Aware Predictive Path

### Retrieval

`simple_ngram_fingerprinting.py` builds and queries an exact absolute-pitch n-gram database.

Observed behavior:

- fingerprints are consecutive note-pitch tuples from the first MIDI instrument
- identification is based on exact hash matches
- confidence is computed from the share of matched fingerprints voting for a piece

Main limitations:

- likely transposition-sensitive
- likely sensitive to expressive deviations that alter exact pitch sequences
- limited use of rhythm or higher-level musical context

### Score Following

`two_stage_server.py` initializes Parangonar once a piece is identified and a score exists.

Observed behavior:

- performed MIDI notes are buffered for identification
- once identified, the server loads the MusicXML score with Partitura
- key signatures are extracted from MusicXML
- Parangonar updates the score position online
- the server predicts upcoming score notes and computes JI ratios from the MusicXML key signature at those note positions

### Predictive Tuning

The frontend receives `ji_ratios` through `two_stage_client.js`, and `window.applyJITuning()` in `js/main.js` stores them in a note-indexed predictive queue.

At note-on time:

- if a fresh predictive entry exists for the incoming MIDI note, it is used
- otherwise the system falls back to the local score-free key estimate

### Main Score-Aware Limitations

The score-aware path is strong, but it is not an oracle.

- retrieval can fail
- score following can drift
- key signatures are not identical to full harmonic analysis
- note-level predictions are still derived from key signature context, not explicit chord or function labels

## Offline MIDI File Path

`js/midi-file-tuner.js` applies the same broad logic to imported MIDI files.

Observed behavior:

- files are segmented into fixed-duration windows
- each segment gets a key estimate using the same profile-based logic
- consecutive identical keys are merged
- missing segments inherit the last known key
- all tuning remains key-relative and ratio-table driven

This is useful as an offline baseline, but it also remains key-based rather than function-aware.

## Tuning Engine

`js/tuning-core.js` defines the core JI tables and conversion utilities.

Important properties:

- fixed major and minor 5-limit ratio tables
- cents deviation computed against equal temperament
- output can be delivered by MTS or MPE

This confirms the core research problem is not how to invent new ratios first, but how to select the right tonal reference at the right time.

## Immediate Research Implications

The baseline audit supports the following conclusions:

1. The score-free path should be strengthened first with a more rigorous causal harmonic baseline.
2. The score-aware path should keep the existing exact matcher as a verified baseline even if a hybrid retrieval stack is added later.
3. Chord and function awareness are absent from the current runtime and remain a clear research opportunity.
4. The existing runtime already exposes clean insertion points for:
   - stronger score-free key tracking
   - learned harmonic-state inference
   - hybrid known-piece retrieval
   - confidence-aware tuning fallback

## Unknowns Recorded During Audit

- I have not yet verified whether the ATEPP-derived material includes note-level performance-score alignments in a form directly usable for harmonic label transfer.
- I have not yet verified whether full Roman numeral labels can be derived reliably from the available MusicXML without extra tooling or manual review.
- I have not yet measured the current live latency under the new planned baseline changes.
