# Component 3: Limitations

Each limitation applies to the implemented system and cites its evidence where possible.

## Data

1. **Public YouTube data only.** Comments, video metadata and public statistics. Watch time, impressions, likes by individual users and subscriptions are invisible.
2. **API quota and collection limits.** Up to 50 newest videos per channel and 100 comment threads per video. Coverage is biased towards recent, active videos.
3. **Comment availability varies.** In the main snapshot, 344 videos had zero public comments and 51 had comments disabled. Some channels have almost no comments: Ada Derana Tamil and Pulse.lk have 2 each.
4. **Incomplete snapshots from collection interruptions.** `rs-20261015T174938Z` is missing 718 comments (Finding 2). Structural validation cannot detect missing comments.
5. **Sparse interaction evidence.**
   - 41 of 153 channel pairs share commenters; the median is 0 and the maximum 36.
   - 73.2 % of ordered pairs score 0.
6. **Single organisation, small channel set.** 18 Derana channels; generalisability is not shown.
7. **Sampling bias.** Commenters are a small, self-selected subset of viewers. Collection depth and channel type affect who is observed.

## Interpretation

8. **Commenter identifiers do not prove real-world identity.** A pseudonym is an account token. One person may have several accounts, and accounts may be shared.
9. **Public comments do not prove subscription** or regular viewing.
10. **No direct observation of audience migration.** The data is a snapshot of who commented where, not of movement.
11. **No causal inference.** Shared commenters may reflect common interests, recommendation exposure, collaborations or chance.
12. **No demographic inference** is made or possible.
13. **Topic similarity is content resemblance**, not influence. Raw E5 cosines are compressed into a narrow band (0.78–0.98).
14. **Directionality is partial.** Only PPR and per-source normalisation are directional; confidence and topic similarity are symmetric.
15. **Scores are relative within a source.** Per-source min-max normalisation means scores are not calibrated for comparison across sources.
16. **Popularity bias.** Confidence uses absolute shared-commenter counts, which favours channels with many commenters.
17. **Shared evidence.** Commenter overlap enters both PPR (reachability) and confidence (support).

## Method and evaluation

18. **No ground truth.** No relevance labels exist, so evaluation shows consistency, not correctness.
19. **Temporal coverage.** There are two comparable snapshot pairs. One is complete (1.5 days apart, sharing 87 % of videos); the other has a partial later snapshot (5.4 days). Score stability is 0.946 and 0.888 respectively. Long-term stability is not shown.
20. **HGT representation limitation.** HGT channel embeddings are nearly identical: cosine median 0.978 to 0.989 (Finding 3).
21. **Sensitivity to sparse channels.** Five channels have no bridge evidence, and several have fewer than k = 3 shared commenters with every other channel (low confidence).
22. **Untuned defaults.** The weights (1/3 each), k = 3 and the model hyperparameters are documented defaults, not tuned values.
23. **Computational cost.** Evaluation with sparse re-runs is expensive; node2vec is the slowest stage (Finding 1).
24. **Non-systematic literature search.** The novelty position must be confirmed by a systematic review.
