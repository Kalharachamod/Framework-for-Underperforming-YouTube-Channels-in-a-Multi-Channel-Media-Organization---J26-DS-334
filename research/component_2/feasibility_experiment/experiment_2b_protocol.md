# Experiment 2B: Development-Only Text Representation and Candidate Retrieval

## Research decision

Experiment 2B is an exploratory retrieval study. It is not a demand classifier,
an active-learning experiment, or evidence of population demand prevalence. It
tests whether transparent text-vector representations can retrieve plausible
lexical and spelling variants for later human review.

The experiment uses the frozen Experiment 2A.2 boundary:

- calibration-only comments supply six researcher-reviewed actionable query
  examples;
- TF-IDF is fitted only on the 1,293-comment development pool;
- the 311-comment held-out partition is not used for fitting, querying,
  retrieval, threshold selection, or review-queue construction;
- the existing 94-comment development queue is excluded from the new queue to
  avoid unnecessary duplicate annotation.

The original rule baseline remains frozen. Its candidate flag is used only to
identify retrieved development comments that the rules did not already select.

## Representations compared now

### Word TF-IDF

Word unigrams and bigrams provide interpretable lexical overlap. This is a
useful baseline for direct phrases such as requests for another video, a full
episode, an explanation, or an update. It is weak when Singlish spelling varies
and cannot directly connect Sinhala-script and Latin-script paraphrases.

### Character TF-IDF

`char_wb` 3-5 grams tolerate some inflection, misspelling and Singlish spelling
variation. They can still overvalue shared fragments, names and formulaic
phrases. Character overlap also does not translate Sinhala script into Latin
script, so cross-script similarity remains limited.

### Combined TF-IDF

The normalized word and character matrices are concatenated and normalized
again, giving both blocks equal influence. Combined retrieval is compared with
each individual representation; it is not assumed to be superior.

Cosine similarity ranks neighbors within each representation. Scores are not
probabilities and must not be compared as if they were calibrated across
different representations.

## Query and queue design

The six `YES` comments in the frozen researcher-reviewed calibration set are
used as query examples. For each query, each representation retrieves up to 10
development comments with positive cosine similarity; zero-overlap rows are
not treated as neighbors. A private manifest retains query IDs, ranks,
similarities, representation names and frozen baseline outputs.

The blinded 60-comment queue is selected from rule-negative neighbors that do
not already occur in the Experiment 2A.2 queue. Multiple-representation and
multiple-query support are ranked first, with a deterministic hash used only
as a final tie-break. Review order is deterministically shuffled. The reviewer
CSV contains context and blank canonical annotation fields, but no candidate
flag, similarity score, retrieval method or selection reason.

This is intentionally demand-enriched retrieval. It cannot estimate the
frequency of demand in the pilot or in the wider YouTube audience.

## Methods deferred

Logistic Regression and Linear SVM are appropriate supervised baselines after
enough development examples have independent human labels and adjudication.
Classifier uncertainty sampling is also deferred: similarity-ranked review is
retrieval-assisted annotation, not genuine active learning.

For a separate follow-up embedding comparison, `intfloat/multilingual-e5-small`
is a reasonable first CPU-oriented candidate: its model card reports 12 layers,
384-dimensional embeddings, an MIT license and broad multilingual training.
The model card also warns that low-resource languages may perform worse. It
must therefore be evaluated specifically on Sinhala script, Singlish and
code-mixed comments rather than accepted as suitable from its multilingual
label alone. E5 retrieval also requires the documented query/passage prefixes.

`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` is compact, but
the Sentence Transformers language list for that family does not explicitly
include Sinhala. LaBSE explicitly includes Sinhalese and may be a useful
cross-script comparator, but its documentation notes that it is strongest for
translation-pair mining and weaker for non-translation semantic similarity.

No embedding model is downloaded or run in Experiment 2B.

## Reproducibility and outputs

Run from the repository root:

```bash
.venv/bin/python -m research.component_2.feasibility_experiment.prepare_experiment_2b
```

The fixed seed is `20261019`. The experiment validates the frozen partition
fingerprint and calibration-file checksum before feature extraction. Outputs
are written to the Git-ignored directory:

```text
research/component_2/feasibility_experiment/outputs/experiment_2b/
```

The output set contains a private neighbor audit, a private selection manifest,
a blinded annotation CSV, an aggregate JSON summary and an aggregate Markdown
report. Human labels remain blank until independent review.

## Interpretation gate

After annotation, report representation-specific retrieval yield and inspect
false matches by channel and script. Do not use the held-out partition until
the modelling pipeline, thresholds and analysis plan are frozen. Do not claim
that a similar comment is actionable demand without human evidence about the
requested action, target and video context.

## Sources for the deferred model assessment

- [Multilingual E5 small model card](https://huggingface.co/intfloat/multilingual-e5-small)
- [Sentence Transformers pretrained multilingual models](https://sbert.net/docs/sentence_transformer/pretrained_models.html#multilingual-models)
- [LaBSE model card](https://huggingface.co/sentence-transformers/LaBSE)
