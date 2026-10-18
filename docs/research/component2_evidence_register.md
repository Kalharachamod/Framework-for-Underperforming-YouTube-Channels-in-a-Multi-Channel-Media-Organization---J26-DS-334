# Component 2 dashboard evidence register

Evidence audit: **18 October 2026**, for the viva on **22 October 2026**.
This register deliberately contains aggregates and row references, not private datasets,
participant names, comment IDs, video IDs, credentials or annotation exports.
The dashboard is a static research snapshot at `/component-2`.

## E1 — Pilot preparation

Sources: `research/component_2/sql/pilot_dataset_extraction.sql`,
`research/component_2/src/{validation,eda,text_processing,annotation}.py`,
the four Component 2 notebooks, and the local ignored
`data/analysis/component_2/dataset_quality_summary.csv`.

The raw snapshot and quality summary were checked: 2,000 comments, five channels,
400 comments per channel, 327 catalogue videos and 255 comment-covered videos.
Zero duplicate comment/video IDs, empty comment fields, missing video metadata
or channel mismatches were reported. Current validated/preprocessed comment files
each have 2,000 rows; validated/prepared video files each have 327 rows.
The deterministic, balanced pilot does not represent the whole YouTube audience.
Sinhala, Latin/Singlish, mixed-script and emoji features do not establish language labels.
Exact raw text in the canonical schema is distinct from the earlier NFC `original_text`.

## E2 — Annotation workflow and attribution

Sources: `research/component_2/annotation_guidelines.md`,
`annotation_portal/README.md`, assignment/preparation implementations and a local
read-only inspection of the ignored annotation sample/database.

The 300-row template contains 60 comments per channel. Its demand-label fields
are blank. The portal supports primary-researcher review of all 300 and five
volunteer sections of 30 each. Assignment capacity is not annotation completion.
The local database contains two participant records and one saved response.
Those totals do not verify participant roles, feedback scope or an independent
annotation study. Live Supabase responses were not accessed.

The researcher reports preliminary feedback from two volunteers. Available
records do not establish what each reviewed, an independently completed sample,
agreement, or attribution permission. Use **Reviewer 1** and **Reviewer 2** only
as neutral identifiers for that reported feedback. The researcher explicitly
selected neutral identifiers during this task. To strengthen this evidence,
record review scope, dates, independence, completed decisions and the applicable
supervisor/ethics clarification; obtain explicit attribution permission before
publishing real names.

## E3 — Calibration and error analysis

Local-only source records (not bundled or committed):

- `research/component_2/feasibility_experiment/outputs/calibration_40_comments.csv`
- `outputs/calibration_40_selection_key.csv`
- `outputs/calibration_40_evaluation/metrics.json`
- `outputs/calibration_40_evaluation/first_calibration_report.md`
- `outputs/calibration_40_evaluation/experiment_1b_error_analysis.md`

The reports state that the researcher manually reviewed and approved the labels,
with AI-assisted suggestions available. This is researcher review, not established
independent double annotation. The unchanged baseline was recomputed in memory
against the frozen calibration during the dashboard audit; no files or labels
were rewritten.

| Diagnostic | Verified value |
| --- | ---: |
| Calibration rows | 40 |
| Selected prior candidates / controls | 20 / 20 |
| Researcher actionability YES / NO / UNCLEAR | 6 / 32 / 2 |
| Binary-evaluable rows | 38 |
| TP / FP / FN / TN | 5 / 13 / 1 / 19 |
| Precision | 27.78% |
| Recall | 83.33% |
| F1 | 41.67% |
| Eight-category agreement, baseline vs researcher | 15/40 = 37.50% |

The set was deliberately selected, including four candidates and four controls
per channel. These are diagnostic figures, not population estimates or final
classifier performance. The two human-actionability UNCLEAR rows are excluded
from binary evaluation, not converted into NO.

Experiment 1B assigns one main explanation to each binary error:

| Main error explanation | Count |
| --- | ---: |
| Sinhala/Singlish context misunderstanding | 3 |
| Praise/reaction mistaken for demand | 4 |
| Keyword-triggered false positive | 1 |
| Missing surrounding context | 2 |
| Request targeting external actors | 2 |
| Implicit storyline preference missed | 1 |
| Broad candidate vs strict actionability mismatch | 1 |

Secondary lexical overreach affects all 13 false positives. Secondary factors
overlap and must not be added to the main-category total.

### Public-safe example selection

Only five non-sensitive calibration excerpts are manually curated into the page.
No dataset is imported into frontend assets. Their text, labels and original
baseline predictions were verified against the CSV and the unchanged detector:

| Calibration row | Human signal | Actionability | Baseline signal | Candidate |
| --- | --- | --- | --- | --- |
| 4 | TOPICAL_INTEREST_OR_DISCUSSION | NO | EXPLICIT_CONTENT_REQUEST | Yes |
| 16 | ORDINARY_REACTION | NO | EXPLICIT_CONTENT_REQUEST | Yes |
| 24 | CONTENT_CHANGE_PREFERENCE | YES | UNCLEAR | No |
| 27 | EXPLICIT_CONTENT_REQUEST | YES | EXPLICIT_CONTENT_REQUEST | Yes |
| 29 | INFORMATION_NEED | UNCLEAR | CONTENT_CHANGE_PREFERENCE | Yes |

Row 24 displays only a short exact excerpt, omitting character references.
Its label was assigned using the full original context, which the excerpt alone
cannot reproduce. The separate “Great video” teaching example is illustrative,
has no measured baseline result, and is excluded from every study metric.
No sensitive political/medical accusations, commenter identities, researcher
private notes or volunteer response exports are displayed.

## E4 — Experiment 2A and 2A.1

Sources: `prepare_experiment_2a.py`,
`dataset_split_and_leakage_audit.md`, and the preserved local Experiment 2A
sample, manifests and methodology report.

The 500 rows contain 100 comments per channel but touch 197 of the 255
comment-covered videos. Holding out every comment from those videos reserves
1,825 comments (91.25%). Enriched-development videos contain 20 comments across
five videos; the future-training partition has 155 comments across 53 videos.
The original selected enriched review queue has five blank-label rows: four
existing-rule candidates and one supplementary match. These are different
counts from the full 20-comment video partition.

The original 500 overlap calibration by 10 exact comments and 35 videos.
The old development/test grouping prevented video crossover but did not remove
calibration exposure. The 500 are now exploratory, not a valid fresh final test.
The dashboard's two-video leakage animation is explicitly illustrative, not a
claim that the original full-video boundary crossed development and evaluation.

## E5 — Experiment 2A.2 and safeguards

Sources: `experiment_2a2_protocol.md`, `annotation_schema_v1.md`,
`experiment_2a2_partition_lock.json`, `partition_guard.py`,
`prepare_experiment_2a2.py`, and local ignored summary/manifests.
The local manifest was verified with `PartitionGuard.load()`.

| Frozen role | Comments | Videos |
| --- | ---: | ---: |
| Calibration only | 396 | 37 |
| Development pool | 1,293 | 175 |
| Held-out evaluation | 311 | 43 |
| Total | 2,000 | 255 |

Selection uses seed **20261018**, eligible videos within channel and chronological
quartile, and approximately 20% held-out videos. It does not use comment text,
labels or retrieval scores. Every calibration-source video is excluded from
both new model partitions. The source hashes and row-order-independent identity
are frozen; the guard requires development identifiers for future training.

Partition fingerprint:
`fbc2bdaca6ff73987e257a3408d23ea405e062168a4a535218f5ac4117a46f9f`

The development queue has **41 rule candidates + 6 supplementary candidates +
47 controls = 94 rows**, from 63 development videos. All controls matched channel,
script and time stratum. Human fields remain blank and predictions/selection
groups are withheld from reviewer-facing templates. Enrichment cannot estimate
natural demand prevalence.

The 500-row crosswalk allocates 314 to development, 100 to calibration-only and
86 to held-out. The 86 establish overlap, not proof that a person saw them.
Prior reading or tuning must be resolved before final evaluation. The held-out
311 are an unlabelled evaluation frame, not completed independent test results.

The existing ignored review CSVs predate the canonical schema additions and lack
six newer annotation fields (request targets and timestamps), plus six text/schema
provenance fields. Their existing human fields are blank. They were preserved
during this task. Current preparation code generates the v1 fields and is
verified by tests using temporary outputs;
prepare fresh v1 templates in a separate approved location and confirm the frozen
identity before further annotation, preserving any subsequent human work.

## E6 — Dates, tests and future methods

Git dates (Asia/Colombo offsets in the original history): `d08d1c3` on 14 October
for validation/preprocessing; `7969e08` and `bd9f7d0` on 14 October for annotation
and video context; portal fixes through `3e7603f` on 15 October; `6afa033` on
16 October for feasibility/evaluation/audit tooling. These establish software
checkpoints, not the exact dates of every annotation or analysis session.
Experiment 2A.2 was verified during the 18 October audit; its seed is not used
as independent proof of a research activity date.

`python -m unittest discover -s tests/component_2 -v` passed **111 tests** on
18 October 2026. Those validate software behavior and partition invariants,
not classifier accuracy. The initial `pytest` attempt could not run because
pytest is not installed; unittest is the existing suite's supported runner.

Independent reliability, ethics clarification, legacy mappings, held-out
exposure, programme metadata and positive-labelled examples remain unresolved.
No trained XLM-R, demand/supply BERTopic clusters, aligned distributions, research
JSD values or validated content opportunities are reported.

The planned JSD formula and the distinction between divergence and square-root
distance are supported by the [official SciPy definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html).
Directional demand-minus-supply topic shares are a planned interpretation;
global JSD is symmetric and does not identify the direction of a gap.
