# Evaluation Protocol

## Principle

The project should be evaluated as a research system, not as a demo.

Every reported improvement should specify:

- which operating mode it applies to
- what baseline it is compared against
- what metric improved
- what latency cost was incurred

## Evaluation Axes

### 1. Score-Free Harmonic Tracking

Primary metrics:

- local-key accuracy
- change-point or modulation detection F1
- prediction stability under ambiguity
- confidence calibration

Notes:

- evaluation must be causal
- future notes must not be used to label the present prediction at inference time

### 2. Known-Piece Retrieval

Primary metrics:

- top-1 accuracy
- top-k accuracy
- mean reciprocal rank
- notes-to-identification

Robustness probes:

- tempo variation
- partial observation
- ornamentation
- transposition, if relevant to the chosen design

### 3. Tuning Quality

Primary metrics:

- note-level cents error against teacher labels where applicable
- interval-purity proxies for simultaneously sounding notes
- consonance-related summary measures

Perceptual layer:

- structured listening tests
- clear reporting of listener pool, stimuli, and rating method

### 4. Real-Time Performance

Primary metrics:

- inference latency
- end-to-end latency
- CPU load
- throughput
- dropped or skipped update rate

The existing `js/latency-metrics.js` should be reused where possible for runtime measurement.

## Statistics

Every major comparison should report:

- sample size
- confidence intervals
- effect size
- statistical test choice
- assumptions or limitations of the test

If a result is exploratory or underpowered, it should be labeled as such.

## Ablations

At minimum, the project should include:

- classical baseline vs learned model
- key-only vs richer harmonic context
- exact retrieval vs hybrid retrieval
- latency with and without learned inference

## Reporting Template

Each experiment report should answer:

1. What changed?
2. Against which baseline?
3. Which metric moved?
4. By how much?
5. At what latency cost?
6. Is the result robust?

## Known Unknowns

- I do not yet know which consonance proxy will best reflect the actual tuning objective for struck-string instruments in this project.
- I do not yet know whether teacher-label error or listening tests will be the stronger evaluation axis for later direct-tuning experiments.
