# Backend Harmonic Integration

## Objective

Introduce the first live-safe deployment path for the learned harmonic-state model without replacing the current classical score-free detector.

The integration target is the Python backend, not browser-side inference.

## Current Status

Status: `implemented` for the first low-latency assistance path

Verified integration points:

- `harmonic_context_runtime.py`
- `two_stage_server.py`
- `two_stage_client.js`
- `js/main.js`

## Implemented Runtime Contract

### Server Side

The backend now supports an optional harmonic-model checkpoint path and runtime threshold.

Runtime behavior:

- load the checkpoint if present
- keep the model on CPU
- update the harmonic runtime on every incoming note
- emit a `harmonic_prediction` event only when the runtime confidence gate is passed
- stop using the harmonic runtime for tuning decisions once score-following is active

Current server parameters:

- `--harmonic-checkpoint`
- `--harmonic-threshold`
- `--harmonic-active-duration-ms`

### Client Side

The browser now treats backend harmonic inference as an optional assistance signal.

Client behavior:

- store the latest backend harmonic prediction
- use it only while it is fresh
- ignore it when score-following and MusicXML tuning are active
- fall back automatically to the classical detector when the backend signal expires

### Tuning Decision Order

The runtime priority is now:

1. score-aware predictive note-level tuning from MusicXML
2. fresh backend harmonic-model prediction
3. local causal ensemble detector
4. equal-temperament fallback if no key is available

This is the intended first deployment claim because it is conservative and auditable.

## Confidence-Gated Policy

The learned model is not allowed to force a switch when uncertain.

Implemented rule:

- if the backend harmonic model emits a prediction above threshold, it can drive the current key for score-free tuning
- if it does not emit, the existing `js/key-detection.js` result remains the active fallback

This matches the original design intent in `docs/research/harmonic-model.md`.

## Why Backend First

The backend-first choice is deliberate.

- it avoids immediate browser inference constraints
- it allows PyTorch checkpoint loading without distillation work
- it keeps the existing frontend tuning engine intact
- it lets the thesis isolate harmonic inference quality from MIDI-output engineering

## Implemented Event Payload

The backend emits:

- `key`
- `confidence`
- `source`
- `timestamp`
- `latency_ms`
- `event_count`

These fields are sufficient for:

- UI updates
- confidence-aware fallback
- latency logging
- later calibration studies

## Current Approximations

The first live backend path still uses approximations that must be reported honestly.

- the backend currently receives note-ons only from the existing client hook
- active-note context is approximated using a fixed active-note lifetime
- the learned model still predicts local key only, not chord or function

These are acceptable for the first deployment experiment, but they are not the end state.

## Immediate Evaluation Use

The implemented path is suitable for the first live backend study:

- unknown-piece performance
- score-free tuning only
- confidence-gated assistance
- CPU latency reporting

It is not yet sufficient for claiming richer harmonic-context reasoning.

## Boundaries

This integration does **not** claim:

- end-to-end direct tuning prediction
- browser-side learned inference
- superiority over the classical detector before the shared causal benchmark is run
- function-aware tuning

## Next Validation Step

The next required experiment is the protocol defined in:

- `docs/research/causal-harmonic-benchmark.md`

That benchmark determines whether this implemented assistance path is a real research result or only a promising engineering hook.
