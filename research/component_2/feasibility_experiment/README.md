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
