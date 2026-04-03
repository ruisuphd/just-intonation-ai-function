# Dataset Protocol

## Dataset In Scope

The current in-repository dataset asset is `ATEPP_JI_Dataset`.

Verified from the repository metadata:

- `5,091` MIDI performances
- `319` unique compositions
- `319` MusicXML scores
- `13` composers

The metadata file is:

- `ATEPP_JI_Dataset/ATEPP-metadata-JI.csv`

The main grouping fields relevant to the research are:

- `composition_id`
- `composer`
- `track`
- `score_path`
- `midi_path`
- `perf_id`

## Governance Rules

The research pipeline should treat the dataset as follows:

- split by `composition_id`, not by performance, to avoid leakage
- keep score-aware and score-free evaluations conceptually separate
- record every preprocessing transformation
- do not assume dataset-derived artifacts are openly redistributable until licensing is verified

## Split Strategy

The default research split should be deterministic and composition-based.

Recommended split:

- `70%` train compositions
- `15%` validation compositions
- `15%` test compositions

Implemented manifest:

- `research_data/composition_splits.json`
- `research_data/score_key_labels/` with `319` extracted score-note label files

Current generated counts:

- train: `217` compositions, `3453` performances
- validation: `44` compositions, `733` performances
- test: `58` compositions, `905` performances

Recommended additional rule:

- preserve composer diversity as much as possible during splitting

Why this matters:

- multiple performances of the same work exist
- performance-level splitting would leak compositional structure and overstate generalization

## Label Types

The project needs several label families.

### 1. Local-Key Labels

Primary target for the first score-free harmonic model.

Source:

- derive from MusicXML key signatures using Partitura

Granularity:

- score-note level
- optionally measure level

Confidence:

- high for notated key signatures
- lower if extended to inferred local harmonic function beyond explicit notation

### 2. Harmonic Function Labels

Optional later-stage target.

Status:

- useful if reliable labels can be generated
- not yet verified as available for the whole dataset

Current rule:

- do not assume Roman numeral labels are available everywhere
- keep this as a secondary research target until label quality is established

### 3. Retrieval Labels

Needed for known-piece identification.

Source:

- `composition_id`
- `track`
- `score_path`

Use:

- candidate matching
- top-k retrieval metrics
- notes-to-identification studies

### 4. Note-Level JI Teacher Labels

Needed for optional direct tuning experiments.

Source:

- derive from the current tuning engine
- later extend if function-aware labels become reliable

## Leakage Controls

The following leakage risks must be controlled explicitly:

- same composition in train and test through different performances
- score-derived labels leaking directly into score-free evaluation without clear protocol
- retrieval evaluation using database entries that include exact duplicates of the query performance
- using future notes to predict current harmonic state in score-free real-time experiments

## Planned Local Research Outputs

The planned local outputs are:

- deterministic composition split manifest
- score-note key-label extraction script
- optional note-level teacher-label extraction script

These are research infrastructure outputs. Their publication status depends on dataset licensing.

## Known Unknowns

- I do not yet know whether note-level performance-score alignments from the underlying ATEPP resources are present in a directly usable form in this repository snapshot.
- I do not yet know whether automated Roman numeral extraction is reliable enough across all 319 scores to be treated as a training target.
- I do not yet know whether generated label files can be redistributed without additional review.
