# Research Log

## 2026-03-09

### Topic

Project framing and first implementation phase.

### Work Completed

- formalized the project as a tonal-context estimation problem rather than a ratio-design problem
- audited the current score-free and score-aware paths
- created the research documentation structure
- recorded the initial literature matrix
- recorded dataset governance and evaluation requirements
- implemented a stronger score-free classical baseline in `js/key-detection.js` with recency weighting, active-note weighting, score smoothing, and hysteresis
- added deterministic composition-level research splits and generated `research_data/composition_splits.json`
- implemented a pure-stdlib MusicXML label extractor to avoid the broken local SciPy and Partitura stack for research-side label generation
- added the first harmonic-model training and runtime scaffolds
- added hybrid retrieval infrastructure and optional backend support for a coarse retrieval index
- hardened `two_stage_server.py` so broken Partitura or Parangonar imports no longer prevent module import
- consolidated the current verified evidence into `docs/research/current-evidence.md`
- defined a shared causal comparison protocol in `docs/research/causal-harmonic-benchmark.md`
- implemented the first backend harmonic-runtime assistance path in `two_stage_server.py`, `two_stage_client.js`, and `js/main.js`
- specified the first function-label pilot in `docs/research/function-label-pilot.md`
- specified the hybrid retrieval comparison study in `docs/research/hybrid-retrieval-study.md`
- wrote a thesis-ready contribution framing in `docs/research/thesis-contribution-framing.md`

### Main Findings

- the live unknown-piece path was originally key-based and context-light, and now has a stronger classical causal baseline
- the known-piece path is strong but still depends on exact retrieval and score-following robustness
- chord and functional context are not yet part of the runtime tuning logic
- direct AI-driven real-time JI appears underexplored in the recent adjacent literature, though that claim still needs fuller review
- the local Python environment has binary incompatibilities in `numpy` / `scipy` / `pandas`, so new research-side utilities were written to avoid those dependencies where possible
- the first upgraded classical baseline reduced predicted key-change count but did not improve note-level agreement against score-derived key labels
- the first learned harmonic-model checkpoint reached `0.3756` validation accuracy and `0.4310` test accuracy under the current windowed evaluation
- the learned harmonic model can now participate in the live unknown-piece path as a confidence-gated backend assistance signal when a checkpoint is present
- the next defensible empirical step is now clearly the shared causal benchmark, not another windowed evaluation

### Open Questions

- whether reliable function labels can be derived automatically from the available scores
- whether browser-side learned inference will ever be required
- whether dataset-derived label outputs can be redistributed
- whether the live backend harmonic path improves score-free tuning once evaluated under the shared causal protocol
- whether transposition invariance helps or hurts early known-piece identification in this use case

### Next Actions

- benchmark the stronger score-free classical baseline
- extract more score-derived label files for training and evaluation
- train and evaluate the first causal harmonic-state model
- run the shared causal harmonic benchmark
- execute the function-label pilot before committing to richer harmonic targets
- benchmark learned coarse retrieval against the exact and statistical baselines
