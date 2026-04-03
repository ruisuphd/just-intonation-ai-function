# Function-Label Pilot

## Objective

Decide whether the project can responsibly move beyond `local key + confidence` to a richer harmonic target.

The pilot is intentionally small. Its purpose is to test label quality before committing to a full-corpus chord or Roman-numeral pipeline.

## Why A Pilot Is Required

The recent symbolic literature makes richer labels attractive:

- Su and Chen (2021) show that transformer-based symbolic harmony modeling is viable.
- Karystinaios and Widmer (2023) show that Roman numeral analysis from symbolic note structure is feasible.
- BACHI (2025) reinforces that chord-boundary-aware symbolic harmony modeling can be strong on both pop and classical data.

However, those papers do not prove that reliable automatic function labels can be extracted from this repository’s `ATEPP_JI_Dataset` score assets with current tooling.

That is the unknown this pilot must resolve.

## Pilot Scope

Pilot size:

- `24` compositions total
- target at least `6` composers
- preserve stylistic and textural diversity where possible

Recommended split of the pilot subset:

- `12` compositions from training
- `6` compositions from validation
- `6` compositions from test

Reason:

- training subset is useful for iterating on the extraction pipeline
- validation and test subsets reveal whether the label quality generalizes beyond the compositions seen during development

## Label Families To Test

### Tier 1: Chord-Oriented Labels

Required pilot targets:

- harmonic boundary
- chord root
- chord quality
- bass or inversion when recoverable

This tier is the most likely next step if Roman numerals prove too brittle.

### Tier 2: Roman-Numeral Style Labels

Optional pilot targets:

- local key
- primary degree
- secondary degree if present
- inversion
- tonicization flag

This tier should only be promoted if the audit demonstrates reliable extraction quality.

## Existing Repo Assets To Reuse

The pilot should build on the current research stack, not bypass it.

Relevant files:

- `extract_score_key_labels.py`
- `musicxml_score_parser.py`
- `research_data/score_key_labels/`

Useful existing fields:

- `measure_index`
- `onset_div`
- `onset_beat`
- `pitch`
- `key`
- `tonic_pc`
- `scale_degree`

These are enough to construct onset groups and a first symbolic harmonic-analysis table for manual review.

## Proposed Pilot Workflow

### Step 1: Build A Review Table

For each selected composition:

1. parse the score using the existing research parser
2. group notes by onset within measure-aware context
3. export one row per harmonic onset with:
   - onset index
   - measure index
   - sounding pitches
   - bass
   - local key label from the current pipeline
   - scale-degree set relative to tonic

This review table is the shared substrate for either manual annotation or semi-automatic post-processing.

### Step 2: Annotate A Gold Slice

Create a manually reviewed gold subset of approximately:

- `400-600` harmonic onsets

Minimum coverage targets:

- at least `4` composers
- at least `8` pilot compositions
- include passages with modulation, tonicization, arpeggiation, and dense sonorities

### Step 3: Compare Label Granularities

Evaluate three candidate targets separately:

1. chord boundary only
2. chord root plus quality
3. full Roman-numeral style representation

The thesis does not need to jump directly to the richest target if a smaller one is measurably more reliable.

## Decision Thresholds

The pilot should use explicit thresholds.

Promote chord-root-quality labels only if:

- missing or unparseable onset rate is below `5%`
- boundary agreement on the audited slice is at least `0.90`
- chord-root accuracy is at least `0.90`
- chord-quality accuracy is at least `0.85`

Promote Roman-numeral style labels only if:

- the above chord thresholds are met
- full Roman-numeral exact-match agreement on the audited slice is at least `0.75`
- obvious modulation failures are rare enough to keep error analysis tractable

If Roman numerals fail but chord root and quality pass, the next model should be chord-aware rather than fully function-aware.

## Failure Outcomes

If the pilot does not meet the thresholds:

- do not train a full-corpus function model
- keep the main thesis claim at local-key tracking
- use the pilot as evidence that label quality, not only model architecture, is the bottleneck

That is still a valid research result.

## Recommended Deliverables

- `research_data/function_label_pilot/selected_compositions.json`
- `research_data/function_label_pilot/review_tables/`
- `research_data/function_label_pilot/gold_audit.csv`
- `docs/research/experiments/<date>-function-label-pilot-v1.md`

## Suggested Modeling Decision After The Pilot

Use the following decision rule:

1. if Roman numerals pass, train a multi-task harmonic model with `local key + RN components`
2. if Roman numerals fail but chord labels pass, train a multi-task model with `local key + chord root + chord quality`
3. if both fail, keep the learned model at `local key + confidence`

## Status

Status: `designed`

The pilot is now specified tightly enough to execute without first committing to unreliable full-corpus function labels.
