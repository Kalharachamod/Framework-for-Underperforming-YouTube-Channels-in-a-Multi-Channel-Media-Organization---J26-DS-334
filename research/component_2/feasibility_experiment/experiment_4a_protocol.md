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
- The new season shows a larger mismatch. Three topics about Season 12
  finalists have demand but no new-season videos; of 195 such comments, 105
  were posted on Season 13 videos and 66 on a Season 12 performance video.
  This suggests continued audience attention to Season 12 finalists, which
  needs manual confirmation before it is reported as an opportunity.
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
