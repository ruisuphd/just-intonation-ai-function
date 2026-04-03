# Decision Log

## 2026-03-09 - Problem Framing

### Decision

Frame the project as real-time harmonic-context estimation for Just Intonation, with two modes:

- score-aware tuning for known pieces
- score-free harmonic tracking for unknown pieces

### Reason

The ratio tables are mostly fixed. The central research challenge is choosing the right tonal reference in real time.

## 2026-03-09 - First AI Target

### Decision

Use `local key + confidence` as the first learned target.

### Reason

It aligns with the current system, is easier to evaluate rigorously, and supports confidence-aware fallback.

## 2026-03-09 - Baseline Order

### Decision

Strengthen the classical unknown-piece baseline before training a neural model.

### Reason

A stronger non-neural baseline makes later neural claims more defensible and prevents weak comparisons.

## 2026-03-09 - Retrieval Strategy

### Decision

Keep exact fingerprinting as the known-piece baseline and future reranking component.

### Reason

The existing exact matcher is already implemented, interpretable, and suitable as a deterministic second stage in a hybrid design.

## 2026-03-09 - Documentation Standard

### Decision

Record design, experiments, and open unknowns explicitly inside the repository.

### Reason

This project is intended to operate at PhD standard and needs a durable research trail beyond chat transcripts.

## 2026-03-09 - Research-Side Score Parsing

### Decision

Use a pure-stdlib MusicXML parser for the new research label-extraction path instead of depending on Partitura.

### Reason

The local Python environment currently has binary incompatibilities in the SciPy stack. The research pipeline needs a dependable way to derive score-note labels even when the heavier symbolic stack is unstable.

## 2026-03-09 - Unknown-Piece Baseline Upgrade

### Decision

Upgrade the score-free classical baseline before any learned model is integrated.

### Reason

The original live detector lacked temporal persistence and explicit active-note weighting. A stronger classical baseline makes later learned-model comparisons more meaningful and safer.

## 2026-03-09 - Graceful Score-Following Imports

### Decision

Wrap Partitura and Parangonar imports in `two_stage_server.py` so the backend can still import and report missing dependencies gracefully.

### Reason

The local research environment currently has binary incompatibilities in the SciPy stack. The server should degrade honestly instead of crashing at import time.

## 2026-03-09 - First Learned Deployment Target

### Decision

Use low-latency Python backend inference as the first learned harmonic-model deployment target.

### Reason

This allows checkpoint-based runtime evaluation without immediately committing to browser-side model deployment, distillation, or JavaScript inference constraints.

## 2026-03-09 - Runtime Harmonic Integration Policy

### Decision

Integrate the learned harmonic model as confidence-gated backend assistance for the unknown-piece path rather than a full replacement of the classical detector.

### Reason

This keeps the first deployment conservative, auditable, and aligned with the existing score-free fallback logic.

## 2026-03-09 - Retrieval Comparison Scope

### Decision

Treat transposition-sensitive and transposition-invariant learned coarse retrieval as explicit study variants.

### Reason

It is not yet known which objective best matches the project’s known-piece identification use case, so the trade-off should be measured directly rather than assumed.

## 2026-03-09 - Function-Label Escalation Rule

### Decision

Do not promote chord or Roman-numeral labels to full-corpus training targets until a small audited pilot demonstrates acceptable label quality.

### Reason

Richer harmonic targets only help the thesis if the supervision is reliable enough to support defensible claims.
