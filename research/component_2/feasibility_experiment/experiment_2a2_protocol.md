# Experiment 2A.2: Corrected Video-Grouped Sampling Protocol

## Research decision

Experiment 2A showed that a comment-first sample of 500 rows touched 197 of
the 255 comment-covered videos. Treating all those videos as held out consumed
1,825 of the 2,000 pilot comments. Experiment 2A.1 also found that the sample
overlapped the researcher-reviewed calibration data by 10 comments and 35
videos. The sample is therefore retained as an exploratory annotation pool,
not used as a fresh final test set.

The next dependency is a defensible data boundary, not a more complex model.
Experiment 2A.2 creates that boundary before further annotation, feature
engineering, model selection, topic modelling, or divergence analysis.

## Estimand and exclusions

The sampling frame is the local five-channel pilot after excluding every video
that contributed a row to the 40-comment calibration experiment. This prevents
earlier error analysis and methodological decisions from leaking into a later
held-out evaluation. Results from the future held-out labels will describe this
calibration-excluded pilot frame, not all YouTube viewers or the organization's
entire catalogue.

The frozen calibration labels are used only to locate comment IDs and their
videos. Their values are never copied into new templates.

## Video-grouped selection

1. Resolve the 40 calibration comments to their source videos.
2. Mark every comment from those videos as `calibration_only`.
3. Within each channel, order the remaining videos by publication time and
   divide them into four near-equal chronological strata.
4. In each channel-time stratum, select approximately 20 percent of videos by
   a seed-controlled SHA-256 rank.
5. Assign all comments from selected videos to `held_out_evaluation` and every
   other eligible video to `development_pool`.
6. Record exact video inclusion probabilities and inverse-probability weights.

The split uses no comment text, language/script category, human label, rule
prediction, programme guess, or engagement value. Every `video_id` has exactly
one role. Later model validation inside the development pool must also group by
video rather than split individual comments.

## Frozen partition identity

The approved comment-to-video-to-role mapping is frozen by
`experiment_2a2_partition_lock.json`. Its canonical partition fingerprint is:

```text
fbc2bdaca6ff73987e257a3408d23ea405e062168a4a535218f5ac4117a46f9f
```

The lock also records the split seed, source hashes, total counts, and
comment/video counts by role. `partition_guard.py` verifies that identity before
future regeneration or model-data loading. It rejects missing manifests,
duplicate comments, videos crossing roles, mismatched source hashes, and any
training record assigned to `held_out_evaluation` or `calibration_only`.

Changing the seed, source snapshot, role assignment, or fingerprint is a new
research decision. It requires researcher approval and a new documented lock;
the existing held-out partition must not be silently replaced.

## Two separate review purposes

The held-out template contains all locally collected comments from selected
videos and blank human fields. It is intended for sealed, prevalence-oriented
evaluation after independent annotation and adjudication.

The development review queue is deliberately enriched. It combines the frozen
rule-based retrieval and transparent supplementary phrase retrieval with one
deterministically matched control per candidate. Matching first uses channel,
script category, and time stratum, with recorded fallbacks when needed. The
reviewer CSV hides candidate/control provenance; a separate local manifest
preserves it. This queue may support training and error analysis but must not
be used to estimate demand prevalence.

The queue contains 47 retrieved candidates and 47 matched controls. Matching
improves development error analysis; it does not reproduce the naturally
occurring candidate rate. Neither the queue nor its candidate/control ratio is
valid evidence of actionable-demand prevalence.

## Historical exploratory exposure

The earlier 500-comment pool cross-walks to 314 development comments, 100
calibration-only comments, and 86 held-out comments. The crosswalk records the
overlap but does not establish whether a person previously read those 86 rows
or whether a rule or threshold was adjusted after seeing them.

Before final evaluation, the researcher must answer and record both questions:

1. Were any of the 86 held-out comments or their labels manually reviewed?
2. Was any retrieval rule, model choice, or threshold tuned using those rows?

If either answer is yes, the consequences must be agreed with the supervisor.
Do not silently replace the frozen partition or describe it as unseen without
that confirmation.

## Annotation and ethics gate

All generated annotation fields are blank. No automatic prediction is treated
as human truth. Before labels are collected, the researcher and supervisor
must confirm the human-participant and ethics position because the approved
proposal describes a no-human-participant design while the implemented method
uses human annotators.

At least an overlap subset should be independently annotated by two people.
Report raw agreement and chance-corrected agreement for the actionable-demand,
primary-signal, and spam decisions, then preserve both labels and adjudication.

## Canonical annotation and text provenance

New Experiment 2A.2 templates use the versioned contract in
`annotation_schema_v1.md`. The eight primary audience-signal classes and the
separate `YES`/`NO`/`UNCLEAR` actionability decision are canonical for this
experiment. Requested action, topic, format, target, evidence, annotator
identity, workflow status, timestamps, and adjudication provenance are retained.
Programme/content type remains contextual metadata rather than a demand label.

Future templates preserve `raw_comment_text` and its UTF-8 SHA-256 separately
from NFC `normalized_text` and NLP-oriented `cleaned_text`. Evidence spans refer
to `raw_comment_text`. The compatibility field `original_text` may already be
NFC-normalized and must not be described as byte-faithful raw evidence.

## Programme and temporal limitations

Channel identity is not a substitute for programme intention. The local data
do not contain a verified programme name or content-type field, and one channel
can publish news, drama, interviews, clips, or other formats. Experiment 2A.2
therefore stratifies only by channel and publication-time block. Programme and
content type require source-verified or manually reviewed metadata before they
can be used for subgroup evaluation or demand-supply interpretation.

Comment and video publication dates are preserved, but later gap claims also
need an explicit analysis date and a catalogue check. A demand signal is not a
verified content gap merely because the current local video snapshot lacks an
obvious match.

## Statistical use

The pilot was collected as 400 comments from each of five channels. Experiment
2A.2 samples videos within channel and publication-order strata, then retains
all collected comments from selected videos. Comments within one video are not
independent observations. Future uncertainty estimates must account for video
clustering and the recorded inclusion probabilities rather than use naive
comment-level intervals.

Channel and publication-order stratification supports inference only to the
calibration-excluded local pilot under this design. Programme-category coverage
is provisional because the source lacks verified programme labels. The 311-row
held-out file is an unlabelled evaluation frame, not a completed final test set.

## Success criteria

- Calibration videos do not enter development or held-out evaluation.
- No video crosses partitions.
- Selection is reproducible from the recorded seed and input hashes.
- The historical 500 rows remain unchanged and are explicitly cross-walked as
  exploratory data.
- New review templates preserve multilingual text and contain no generated
  human labels or visible candidate flags.
- The development side retains enough candidate evidence for human review
  without consuming the held-out evaluation partition.

Meeting these criteria establishes a valid foundation. It does not validate a
classifier, estimate population demand, discover final topics, or prove a
content gap.
