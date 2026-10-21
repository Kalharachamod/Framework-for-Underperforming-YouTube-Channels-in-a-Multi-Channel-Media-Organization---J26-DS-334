# Experiment 4B: Comment Understanding (Target, Stance, Intent) for Dream Star Season 2025

## Why

Experiment 4A compared comment topics with video topics. Two problems make its
topic gaps unsuitable as content advice for a reality programme:

- **Supply assignment.** Performance videos were scattered across unrelated
  topics: the 170 videos placed in "Judges debate (English)" and the 123 in
  "Votes, SMS and wild card" are mostly contestant performances.
- **No stance.** A topic or a name count cannot tell support from criticism.
  "Pahanmi should have got the marks, giving them to Anupama was wrong" counts
  as attention for both contestants, although it supports one, criticises the
  other and criticises the judges.

4B adds a comment-understanding step before demand is measured. For each
meaningful comment it records:

| Field | Values |
|---|---|
| Targets (up to 3) | The 12 main contestants, `OTHER_CONTESTANT`, `JUDGES`, `VOTING_OR_RESULTS`, `HOST_OR_CREW`, `CHANNEL_OR_SHOW`, `OTHER_PERSON` |
| Stance per target | `SUPPORT`, `CRITICISE`, `NEUTRAL`, `UNCLEAR` |
| Intent | The eight primary signals of the annotation schema |
| Requested action | Free text, for requests and change preferences |

This follows aspect-based sentiment analysis (Pontiki et al., SemEval-2014
Task 4) and target-specific stance detection (Mohammad et al., SemEval-2016
Task 6).

## Inputs prepared (`prepare_experiment_4b.py`)

- **Scope.** Dream Star Season 2025 window (1 Apr 2025 – 31 Jan 2026), titles
  labelled "Season 12". Training-pool comments only (`ExpandedCorpusGuard`):
  39,963 comments, of which 12,239 are meaningful (Experiment 3E filter, as
  used in 4A). 896 videos.
- **Contestants.** Read from titles of the form
  "Song (සිංහල) First Last | Dream Star Season 12": 501 videos name a
  performer; 32 contestants, 12 of them with at least 10 videos ("main").
  Group songs and judge segments are not people.
- **Spellings.** For each main contestant, Singlish/English spellings similar
  to the first name and Sinhala-script spellings starting with known stems,
  with comment counts and an example (207 candidates). Ambiguous forms are
  flagged (ජනනී also means "mother"; "bring" is an English word). Spellings are
  used only after the researcher verifies them.
- **Blind validation sheet (200 comments).** Shuffled, new IDs, no model
  output, no stratum shown. Strata (private key only): 120 comments mentioning
  a main contestant, 40 about judges or voting without a contestant name, 40
  random meaningful comments. At most three comments per video (105 videos).
  Batch-1 comments are excluded.
- **Prompt-development sample (40 comments).** Drawn first and disjoint from
  the validation sheet. The extraction prompt is developed on this sample only
  and frozen before the validation sheet is scored.

## Planned extraction and evaluation

- **Model.** Gemini with a fixed JSON output schema. Input per comment: comment
  text, parent comment for replies, video title, and the verified contestant
  names in all scripts. Author identifiers are never sent.
- **Validation.** On the 200 blind comments:
  - target detection: precision, recall and F1 over (comment, target) pairs;
  - stance: accuracy and macro-F1 on targets found by both;
  - intent: macro-F1 and Cohen's kappa.
- **Baseline.** Verified name matching for target detection (no stance), to
  show what the comment-understanding step adds, including the share of
  contestant mentions that are criticism.
- **Use in the gap analysis.** Only comparable parts are compared with supply:
  monthly support attention per contestant against uploads per contestant
  (from titles), with Jensen–Shannon divergence and signed gaps. Criticism of
  judges or voting is reported as programme feedback, and explicit requests as
  a ranked list. Neither enters the divergence.

## Status

Waiting for the researcher to verify the contestant list and spellings and to
label the blind sheet. No model has been run.

## Reproduce

```bash
.venv/bin/python -m research.component_2.feasibility_experiment.prepare_experiment_4b
```

Outputs (Git-ignored) in `outputs/experiment_4b/`:
`contestants_season_2025.xlsx`, `validation_blind_200.xlsx`,
`validation_private_key.csv`, `prompt_dev_40.csv`, `prepare_summary.json`.
