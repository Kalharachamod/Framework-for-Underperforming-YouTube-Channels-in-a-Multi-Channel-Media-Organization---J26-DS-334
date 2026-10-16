# Experiment 2A.1: Dataset Split, Candidate Attrition and Leakage Audit

## Scope

This is a read-only audit of the existing local Component 2 pilot, Experiment
1 calibration file, and Experiment 2A outputs. No datasets, annotations,
baseline rules, Supabase data, or external APIs were modified or accessed.

The audit used the existing `build_experiment_source()` assembly,
`baseline.detect_frame()`, `video_split_manifest.csv`,
`representative_evaluation_500.csv`, `demand_enriched_candidates.csv`, and
`calibration_40_comments.csv`.

## 1. Candidate attrition

The baseline produced 84 candidate comments across the full 2,000-comment
pilot. The current Experiment 2A process excludes every comment from a video
represented in the 500-comment evaluation sample before constructing the
demand-enriched pool.

| Stage | Comments | Videos | Baseline candidates | Explanation |
|---|---:|---:|---:|---|
| Full pilot | 2,000 | 255 | 84 | Existing rule detector output; not human labels |
| Evaluation-video exclusion | 1,825 | 197 | 80 | All comments from evaluation videos are withheld to prevent video leakage |
| Eligible after evaluation-video exclusion | 175 | 58 | 4 | Candidate pool available for development enrichment |
| Retained existing-rule candidates | 4 | 4 | 4 | Four baseline candidates remain eligible |
| Supplementary non-baseline retrieval matches | 1 | 1 | 0 | One re-upload/full-version phrase match remains eligible |
| Final selected enriched rows | 5 | 5 | 4 | Four existing candidates plus one supplementary match |

Within the 175 eligible comments, 171 were not baseline candidates. One of
those matched the supplementary retrieval rules and 170 matched neither the
baseline nor the supplementary rules. Of the nine supplementary non-baseline
matches in the full pilot, eight were also removed because their videos belong
to the evaluation partition.

Therefore, the reduction from 84 baseline candidates to 4 eligible baseline
candidates is primarily a consequence of video-group leakage prevention, not
evidence that the baseline found only four possible requests in the pilot.

The baseline candidate counts by source channel were:

| Channel | Baseline candidates |
|---|---:|
| Ada Derana | 18 |
| Ada Derana Sports | 18 |
| Dream Star | 11 |
| FM Derana | 21 |
| TV Derana | 16 |

The 500-row evaluation sample itself contains 21 baseline candidates. The full
evaluation-video partition contains 80 because it includes 1,325 additional
comments from the same 197 videos that were not selected into the 500-row
sample.

## 2. Current video partitions

The following counts are for complete video partitions, not only the selected
review rows. This distinction is important: the five selected enriched rows
belong to five videos containing 20 total pilot comments.

| Partition | Comments | Videos | Baseline candidates | Ada Derana | Ada Derana Sports | Dream Star | FM Derana | TV Derana |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Evaluation videos | 1,825 | 197 | 80 | 326 | 390 | 351 | 381 | 377 |
| Enriched development videos | 20 | 5 | 4 | 18 | 2 | 0 | 0 | 0 |
| Future training videos | 155 | 53 | 0 | 56 | 8 | 49 | 19 | 23 |
| **Total** | **2,000** | **255** | **84** | **400** | **400** | **400** | **400** | **400** |

Baseline candidates by partition and channel:

| Partition | Ada Derana | Ada Derana Sports | Dream Star | FM Derana | TV Derana |
|---|---:|---:|---:|---:|---:|
| Evaluation videos | 15 | 17 | 11 | 21 | 16 |
| Enriched development videos | 3 | 1 | 0 | 0 | 0 |
| Future training videos | 0 | 0 | 0 | 0 | 0 |

The current `video_split_manifest.csv` is therefore leakage-safe, but the
future training partition contains no baseline candidates and has no verified
positive labels.

## 3. Calibration overlap

The calibration file contains 40 unique comments from 37 videos. Comparing it
with the new 500-comment evaluation sample found:

- Exact comment-ID overlap: **10 comments**
- Exact video-ID overlap: **35 videos**
- Calibration comments absent from the local pilot: **0**

Exact overlapping comment IDs:

```text
Ugx0PLRybqJdX5vYWCd4AaABAg
UgxRBlUA81y46gqutil4AaABAg
UgxxQTwoAhWTchWHna94AaABAg
UgyY1UbGUNBsU4DU1Op4AaABAg
UgymCqM6VdHL-P0ACut4AaABAg
UgzH-sQoeS_GkWakdUt4AaABAg
UgzUbYu3wwVuhYZxwSd4AaABAg
UgzZUxeHMc7aeBcarIB4AaABAg
UgzjHZXN6bE4Jz497Xt4AaABAg.AbcoKw3k2uWAbcsg24XXYV
UgznYtOPbvmgKLb1--94AaABAg
```

Exact overlapping video IDs:

```text
15oxxeqi04o, 1TYDfVlm-Rg, 2Oz5uLIv1CA, 2h_4xF2JRBY, 3ByXn2q2etM,
3qSA3XM4ZPY, 4dihtmEODXY, 5drQjswFscs, 5zS4MxB3BZI, 6dMqkKQLAOQ,
9NnejWFnfh0, BBhtx19-2Qg, EDXzNQClk5U, FdnvYxfJSOs, GDfrF7vtU9U,
HFVvQMG1954, M7drybqC3tA, NOMTO1G17As, OGdJtTYmka4, PgnT0lNmMfA,
Q_MhzRjOQ60, S3cQ2OMyVj8, Xu9z3XKmHt0, akc2aoS_dSE, bUvIjrvU50s,
ifhA6-rzv_Q, miZv_J377Zg, oV--pMov9-Y, pTytCPrWWWA, sIQHTl8g6iI,
vmUtyiGDBfY, woMv4dRpLFQ, wt7_zP_X7Jg, yWCWwDGhth4, yvu2tmrDr0Y
```

The 10 comment overlaps are expected because the calibration sample was
selected before the new evaluation sample. They must not be counted as fresh
independent evaluation labels. The 40 calibration labels contain 6 `YES`, 32
`NO`, and 2 `UNCLEAR` actionability decisions; the 84 automatic candidates
must not be treated as verified positives.

## 4. Representativeness and leakage

The 500-row sample is representative only in the limited design-based sense of
being a uniform, channel-balanced sample of this particular 2,000-comment
pilot. Each pilot channel contributed 400 comments, so each row had a 0.25
within-channel inclusion probability and a design weight of 4.

That does not establish representativeness of the broader YouTube audience,
other time periods, other channels, or all content produced by the
organization. It also does not mean the sample is a random sample of videos:
comments were sampled first, and the resulting 500 rows span 197 of the 255
comment-covered videos.

The current video-grouped rule is leakage-safe because every comment from an
evaluation video is kept out of development and future training. Its cost is
that 77.3% of comment-covered videos and 91.25% of all pilot comments are
reserved in the evaluation video partition. Only 155 comments across 53 videos
remain for future training, and none are baseline candidates.

## 5. Feasibility of a held-out representative evaluation

The existing 500 rows can serve as a held-out evaluation sample if all 197
associated videos remain excluded from training and development. This gives a
strong video-disjoint test boundary, but the development side is too small for
robust multilingual model development and has no baseline-candidate comments
in its future-training partition.

There is also a label-scarcity problem. The 500 template is still blank, and
the 5 enriched rows are still blank. Only the separate 40-comment calibration
file has human-reviewed labels, with 6 actionability `YES` rows. This is a
small calibration result, not a prevalence estimate or a sufficient training
set. Actionable-demand positives may be scarce, and the calibration sample was
not designed for final evaluation.

## 6. Alternative split strategies

### Strategy A: Keep the current split unchanged

Use the 500 rows as a strict evaluation sample and hold out all 197 associated
videos. Annotate only the 500 test rows and collect additional training data
from new videos.

Advantages: strongest leakage control and clear evaluation boundary.

Trade-offs: only 155 future-training comments remain locally; development is
too small; the test partition contains many more unlabeled comments than the
reviewed 500 rows; positive-demand scarcity remains unresolved.

### Strategy B: Use the 500 rows as a general annotation pool, not a frozen test

Annotate the prepared 500 rows first, retain their provenance, and postpone the
final test designation. After labels are available, select a smaller,
channel-stratified set of whole videos for testing and use disjoint videos for
training/development.

Advantages: preserves work already prepared, allows the final test size to be
based on observed label scarcity, and avoids declaring a test set before its
class distribution is known.

Trade-offs: the 500 rows cannot be treated as a final unbiased test result
until a video-grouped split is frozen and test rows are excluded from all model
selection.

### Strategy C: Grouped cross-validation over labeled videos

Once enough comments are human-labeled, use stratified group cross-validation
where the group is `video_id` and channel is retained as a balancing variable.
Each fold must keep every video's comments together. Reserve one final test
fold only after model choices are complete.

Advantages: makes better use of a small labeled dataset and exposes variance
across channels and videos.

Trade-offs: repeated evaluation is less simple to communicate; very rare
positive labels may still make some folds unstable; the final test fold still
needs to remain untouched.

### Strategy D: Collect additional video-disjoint data before freezing a test

Use the current 500 as an annotation pool, then collect a larger approved local
snapshot or additional comments from videos not present in the current
evaluation pool. Build two separate sets: a random channel-balanced sample for
prevalence/evaluation and a demand-enriched sample for training and topic
discovery. Both must retain video provenance and use independent human labels.

Advantages: addresses both the 155-comment training bottleneck and positive
class scarcity.

Trade-offs: requires additional collection and annotation approval; targeted
data cannot be used to estimate demand prevalence.

## 7. Training and labeling inventory

Under the current strict video split:

- Future training inventory: **155 comments across 53 videos**.
- Human-labeled comments in that future training inventory: **0**.
- Enriched development inventory: **20 comments across 5 videos**.
- Human-labeled comments in that development inventory: **0**.
- Prepared evaluation rows: **500 comments across 197 videos**, currently blank.
- Existing researcher-reviewed calibration rows: **40 comments**, with 6 `YES`,
  32 `NO`, and 2 `UNCLEAR` actionability labels.
- Automatic baseline candidates: **84**, but verified positive training labels:
  **0** from those predictions.

The 40 calibration comments overlap the 500-row sample by 10 comment IDs and
35 video IDs. Those rows can support calibration and guideline review but must
not be counted as independent fresh test labels.

## Recommendation

Retain the current 500 rows as a general annotation pool and do not regenerate
or delete them. Do not freeze them as the final test split yet. First annotate
the 500 rows using independent review where possible, preserving the 40
calibration labels as a separately identified calibration subset.

Before model training, obtain additional human-labeled comments from videos
outside the eventual test boundary. Prioritize a modest video-disjoint
demand-enriched training set, supplemented by randomly selected controls from
the same new videos. Keep the current 155-comment future-training inventory as
an available control pool, but do not assume it contains positives.

After the additional labels reveal the real positive-class frequency, freeze a
smaller channel-balanced, video-disjoint test set and use grouped validation
for model selection. This minimizes wasted annotation work while avoiding the
current failure mode in which the evaluation sample consumes nearly all
available videos and leaves no useful positive training data.

No sampling strategy has been changed by this audit. Approval is required
before any dataset is regenerated or any new data are collected.
