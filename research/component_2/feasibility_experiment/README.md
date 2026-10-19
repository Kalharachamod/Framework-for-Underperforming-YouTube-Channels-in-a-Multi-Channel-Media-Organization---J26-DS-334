# Component 2 Demand Feasibility Experiment

This is a reproducible, offline experiment for finding possible actionable
audience-demand signals in the local pilot data. It is separate from the
Streamlit annotation portal, the production taxonomy, Supabase, and the
existing 300-comment annotation sample.

## Run it

From the repository root:

```bash
.venv/bin/python -m research.component_2.feasibility_experiment.run_experiment
```

The default seed is `20261015`. The runner reads the local pilot comments,
pilot video context, existing preprocessed text, and existing 300-comment
sample without changing any input. It writes aggregate audit data and raw
review artifacts to:

```text
data/processed/component_2/feasibility_experiment/
```

That directory is Git-ignored because its files contain comment text and
heuristic predictions. The aggregate report is written to
`initial_feasibility_report.md` in this package and contains no comment text.

## Baseline

The transparent rule baseline is multilingual and deliberately high-recall.
It uses original and cleaned text, available title/description context,
script features, request/change/information/quality/spam/reaction signals, and
an explicit candidate flag. It produces eight experimental signal classes:

`EXPLICIT_CONTENT_REQUEST`, `CONTENT_CHANGE_PREFERENCE`,
`INFORMATION_NEED`, `CONTENT_QUALITY_FEEDBACK`,
`TOPICAL_INTEREST_OR_DISCUSSION`, `ORDINARY_REACTION`,
`SPAM_OR_IRRELEVANT`, and `UNCLEAR`.

These are exploratory signals, not verified human labels. In particular, a
topic-specific expression of interest is not automatically unmet demand, and
not every question is a request for future content. See
[`decision_guide.md`](decision_guide.md) for the review rules and examples.

## Blinded review

The default run selects 10 heuristic candidates and 10 controls per channel,
for up to 100 rows across the five pilot channels. The review CSV contains
comment IDs, channel/video context, original and cleaned text, and blank human
review fields. It does not contain the baseline class or candidate/control
group. The separate local manifest retains the sampling provenance and must
not be shown to reviewers.

Reviewers should independently complete the blank fields. Evaluation code
returns `not_available` until verified human labels exist. Recall and demand
prevalence require a defensible representative sample; the demand-enriched
review is suitable for candidate precision and false-positive investigation,
not prevalence estimation.

## Optional methods

`model_adapter.py` is a lazy local semantic adapter. It only loads a model when
`COMPONENT2_FEASIBILITY_MODEL` is explicitly set and the adapter is called.
No model is downloaded or run by the default experiment. Model coverage of
Sinhala, Singlish, and code-mixed text must be tested locally before use.

`gemini_adapter.py` is a disabled-by-default structured JSON adapter. It is
never called by the runner. It requires explicit enablement, a configurable
model, a small batch limit, a request limit, and an approved `GEMINI_API_KEY`.
It must remain an offline review aid and must never write labels to Supabase.

## Scientific use

The representative sample should remain separate for prevalence and evaluation.
After human verification, a separately tracked demand-enriched sample can be
used for supervised model training and demand-topic discovery. Report results
by channel and script, retain sampling seed and IDs, inspect false positives,
and account for class imbalance when interpreting BERTopic distributions and
Jensen-Shannon Divergence. This experiment makes no accuracy claim.

## Experiment 2A.2 corrected sampling frame

Experiment 2A.1 found that the original 500-comment sample touched 197 videos,
leaving too little video-disjoint development data, and that it overlapped the
40-comment calibration experiment. The historical 500 rows remain unchanged
and are now treated as an exploratory annotation pool.

The corrected offline preparation samples videos first, excludes all
calibration videos, preserves a held-out evaluation partition, and builds a
separate blinded candidate/control queue from development videos:

```bash
.venv/bin/python -m research.component_2.feasibility_experiment.prepare_experiment_2a2
```

Local outputs are written under `outputs/experiment_2a2/` and are ignored by
Git because the review files contain comment text and IDs. The design and its
limits are documented in
[`experiment_2a2_protocol.md`](experiment_2a2_protocol.md). The command does
not train a model, assign labels, access Supabase, or call an external API.

The approved split is frozen by
[`experiment_2a2_partition_lock.json`](experiment_2a2_partition_lock.json).
Future training code must load data through `partition_guard.py` or call
`PartitionGuard.validate_training_frame()` before feature extraction. The guard
accepts only `development_pool` identifiers and rejects calibration-only,
held-out, unknown, duplicate, or conflicting identifiers. A changed seed,
source hash, manifest identity, or checksum fails rather than silently creating
a different test set.

New review templates follow
[`annotation_schema_v1.md`](annotation_schema_v1.md). They preserve exact source
text in `raw_comment_text`, retain NFC text separately in `normalized_text`, and
define evidence spans against the raw field. The legacy 300-comment portal
taxonomy is not automatically migrated into the refined eight-class schema.

## Experiment 2B development-only TF-IDF retrieval

Experiment 2B compares word unigram/bigram TF-IDF, character `char_wb` 3-5
gram TF-IDF, and an equally weighted combined representation. It uses the six
researcher-reviewed actionable calibration comments only as retrieval queries
and fits every representation exclusively on the frozen 1,293-comment
development pool. The held-out partition remains protected.

```bash
.venv/bin/python -m research.component_2.feasibility_experiment.prepare_experiment_2b
```

Private outputs are written under `outputs/experiment_2b/` and remain ignored.
The new blinded 60-row review queue excludes the existing Experiment 2A.2
candidate/control queue and hides similarity scores, representation names and
baseline predictions. See [`experiment_2b_protocol.md`](experiment_2b_protocol.md)
for the scientific scope, deferred methods and interpretation limits.
