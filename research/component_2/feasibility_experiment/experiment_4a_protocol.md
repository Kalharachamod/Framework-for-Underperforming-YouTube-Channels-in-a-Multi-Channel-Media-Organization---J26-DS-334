# Experiment 4A: Demand-Anchored Topics and Jensen-Shannon Gaps (Dream Star)

## Design

- Comments: the 44,070 Dream Star comments in the training pool
  (`development_pool` and `expanded_development_pool`). Held-out and
  quarantined comments are not read.
- Meaningful filter (Experiment 3E) and demand classifier (Experiment 3D), both
  multilingual-e5 + logistic regression trained on all batch-1 labels:
  13,249 meaningful comments.
- Supply: all 967 Dream Star uploads since April 2025.
- Topics: BERTopic with k-means (k = 15) on the meaningful comments; each video
  is assigned to its nearest topic centroid.
- Windows: season 2025 (Apr 2025 – Jan 2026), off-season (Feb – mid-Sep 2026),
  new season (from mid-Sep 2026).
- Gap measures per window: base-2 JSD between demand (meaningful comments per
  topic) and supply (videos per topic), per-topic contributions and signed
  shares; JSD between expected requests and supply.

## Problems found in the first run and how they were fixed

1. **Writing-style artifact.** With raw e5 vectors, 890 of 967 videos fell into
   one comment topic, because English-style titles sit closer to English
   comments than to Sinhala or Singlish comments about the same content. JSD
   (0.56–0.68) measured style, not demand. Fix: centre embeddings within each
   domain and script group before clustering and assignment.
2. **Script clustering.** k-means on raw vectors produced clusters sorted by
   script (purity 0.75 against a chance level of 0.43). Script-group centring
   reduced it to 0.56, and clusters now group content across scripts:
   contestants, songs and singing, voting, judges, finals.
3. **HDBSCAN collapse.** Density clustering merged 80% of comments into one
   topic. k-means with a fixed k, with a sensitivity check over
   k = 10, 15, 20, 25, replaces it.
4. **Request over-counting.** The balanced classifier flagged 41% of meaningful
   comments as requests, against 10.9% observed in the random sample.
   Probabilities are prior-shift corrected (Saerens et al., 2002) to that
   rate and summed into expected request counts. After correction no single
   comment exceeds 0.5, so per-comment request flags are not reliable on
   natural data; only aggregate expected counts are reported.

## Results

| Window | Meaningful comments | Videos | JSD (k = 15) | JSD range over k = 10–25 |
|---|---:|---:|---:|---:|
| Season 2025 | 12,239 | 896 | 0.155 | 0.119 – 0.243 |
| Off-season 2026 | 443 | 2 | 0.621 | 0.428 – 0.837 |
| New season 2026 | 567 | 69 | 0.426 | 0.361 – 0.413 |

- Season 2025 has a moderate, stable mismatch. Audience attention is higher
  than supply on contestant-support topics (Pahanmi, Anupama, Janani) and on
  voting (6.1% of demand vs 0.4% of videos). Supply is higher on song and
  group-song performances.
- The off-season window has only two videos, so its JSD is unstable across k
  and is not interpreted. Windows need a minimum supply size.
- The new-season JSD is not interpreted as a gap. Three topics named after
  Season 12 contestants have demand but no new-season videos; of 195 such
  comments, 105 were posted on Season 13 videos and 66 on a Season 12
  performance video. Topics were fitted across all windows, so contestant
  topics carry over from one season to the next: the zero supply is expected
  once those contestants leave, and it is not a content opportunity.
- Attention also moves within a season. Monthly shares in Season 2025: the
  votes, SMS and wild-card topic fell from 14.5% of interest (July 2025) to
  3.9% (November 2025); the Nipuni topic rose from 6.0% (July) to 13.1%
  (December). Gaps are therefore tied to the period in which they are observed.
- Consequence: each season is analysed with its own topics, and validation
  uses short periods (monthly) within a season. Season 13 is analysed once
  enough comments and videos exist. Only Season 2025 is reported in the UI.
- Expected request counts follow meaningful-comment counts closely (request
  JSD 0.140 vs interest JSD 0.155 in season 2025), because the demand
  classifier separates requests only weakly on natural data.

## Limitations and next steps

- Video assignment remains approximate: 42.5% of videos share a keyword with
  their assigned topic. A residual style effect remains (the English "judges"
  topic receives 170 videos).
- Stronger request detection (more labelled positives or an LLM second stage)
  is needed before per-topic request counts are interpreted individually.
- Manual reading of the top-contributing topics in each window is the
  validation step for the gap claims.

## Reproduce

```bash
.venv/bin/python -m research.component_2.feasibility_experiment.experiment_4a_demand_supply --channel "Dream Star"
```

Outputs are written to the Git-ignored `outputs/experiment_4a/dream_star/`.

## Second channel: FM Derana (non-reality, mixed talk channel)

FM Derana has no seasons, so three half-year windows with similar upload
counts were used (Apr–Sep 2025, Oct 2025 – Mar 2026, Apr–Oct 2026).
Training-pool comments: 7,745; meaningful comments: 3,757; videos: 302.

| Window | Meaningful comments | Videos | JSD (k = 15) | JSD range over k = 10–25 |
|---|---:|---:|---:|---:|
| Apr–Sep 2025 | 1,366 | 108 | 0.100 | 0.075 – 0.140 |
| Oct 2025 – Mar 2026 | 893 | 90 | 0.208 | 0.115 – 0.319 |
| Apr–Oct 2026 | 1,498 | 104 | 0.133 | 0.133 – 0.242 |

Audience topics are interpretable (folk and supernatural stories from
*Kemmura Adaviya*, religious blessings, cricket and live sport, rap and talent
segments), but video alignment is weak: only 1.3% of videos share a keyword
with their assigned topic (Dream Star: 43%), and JSD varies with the number of
topics. Most uploads are *Kemmura Adaviya* episodes whose titles name the
episode rather than the themes viewers discuss, so title and description text
does not describe this channel's supply well enough.

**Finding.** The method gives stable, interpretable gaps for programme-focused
channels whose titles describe their content (Dream Star), and is limited for
mixed talk channels whose titles do not. Richer supply text (for example
transcripts) would be needed there. Channels with very little comment activity
(for example Pulse.lk: 125 comments on 621 videos) cannot support the analysis.

**Topic labels.** A list of Sinhala-script and romanised-Sinhala function words
(pronouns, particles, auxiliaries, fillers) is removed from comment-topic
labels only. Clustering uses embeddings, so the Dream Star topics and all its
JSD values are unchanged (verified); only the labels became readable.
