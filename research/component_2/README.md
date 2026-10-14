# Component 2

**Quantified Audience Demand Mining and Content-Gap Divergence**
Owner: Kahandawa K A N N (IT23307094)

## Research Purpose

Component 2 analyses public YouTube audience comments to identify audience demand signals, prepare multilingual text for modelling, and later compare demand topics against video content supply. Phase 1 focuses on reproducible dataset validation, exploratory analysis, and conservative multilingual preprocessing. Phase 2A prepares a deterministic manual annotation sample and annotation guide for demand-intent labelling.

These phases do **not** implement demand classification, BERTopic, or Jensen-Shannon Divergence yet.

## Required Local Datasets

Place the pilot CSV exports at:

```text
data/raw/component_2/component2_pilot_comments.csv
data/raw/component_2/component2_pilot_videos.csv
```

Expected sources:

- `research.comments`
- `research.videos`
- `research.channels`

The pilot extraction is documented as up to 400 non-empty comments per selected channel, spread across videos, using deterministic `MD5(comment_id)` ordering.Any extraction details not present in the CSV exports are treated as unknown.

## Research Structure

```text
research/component_2/
├── annotation_guidelines.md
├── notebooks/
│   ├── 01_dataset_validation.ipynb
│   ├── 02_exploratory_analysis.ipynb
│   ├── 03_multilingual_preprocessing.ipynb
│   └── 04_demand_annotation_preparation.ipynb
├── src/
│   ├── data_io.py
│   ├── validation.py
│   ├── eda.py
│   ├── text_processing.py
│   ├── annotation.py
│   └── video_processing.py
└── sql/
    └── pilot_dataset_extraction.sql
```

## Environment Setup

From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The notebooks are compatible with VS Code Jupyter using the project `.venv` kernel.

## Notebook Execution Order

```bash
jupyter nbconvert --to notebook --execute research/component_2/notebooks/01_dataset_validation.ipynb --inplace
jupyter nbconvert --to notebook --execute research/component_2/notebooks/02_exploratory_analysis.ipynb --inplace
jupyter nbconvert --to notebook --execute research/component_2/notebooks/03_multilingual_preprocessing.ipynb --inplace
jupyter nbconvert --to notebook --execute research/component_2/notebooks/04_demand_annotation_preparation.ipynb --inplace
```

## Generated Outputs

Generated files are written under:

```text
data/processed/component_2/
data/analysis/component_2/
```

Important outputs:

- validated comments and videos
- preprocessed comments
- prepared video metadata
- dataset quality summary
- EDA summary tables
- preprocessing audit tables
- research charts
- manual demand annotation sample and aggregate distribution summaries

These outputs are not intended for Git commits.

## Phase 2A Annotation Preparation

Phase 2A creates a deterministic 300-comment manual annotation template at:

```text
data/processed/component_2/annotation/component2_demand_annotation_sample.csv
```

The annotation template includes:

- original and cleaned comment text for human labelling
- channel and video identifiers for traceability
- reply status and publication timestamp
- script category and preprocessing flags
- blank fields for primary demand label, demand subtype, annotator labels, notes, and final adjudication

Use `annotation_guidelines.md` when filling the labels. Do not generate artificial labels. The annotation output is a local research artifact and should not be committed to Git.

## Methodology Choices

- Original comment text is preserved.
- Sinhala Unicode is preserved.
- Latin-script text is not automatically labelled as English.
- Code-mixed Sinhala and Latin-script content is preserved.
- URLs are normalized to a placeholder token.
- Emojis are retained and flagged when comments are emoji-only.
- Very short, repeated, empty, or spam-like comments are flagged for review rather than silently removed.
- Aggressive stemming, stopword removal, translation, and transliteration are avoided in Phase 1.

## Known Limitations

- The pilot is deterministic and balanced by selected channels;it is not a random representative sample of all YouTube audiences.
- Script detection is not language detection.
- Demand-related usefulness requires later manual review and labelling.
- Video supply coverage is limited to the stored pilot video metadata, not the complete historical YouTube catalogue.

## Next Planned Research Stages

1. Pilot demand-intent labelling.
2. Inter-annotator agreement and adjudication.
3. Baseline demand classifier experiments.
4. BERTopic demand-topic modelling.
5. Video supply topic modelling.
6. Demand-supply topic distribution comparison.
7. Jensen-Shannon Divergence and underserved-topic ranking.
