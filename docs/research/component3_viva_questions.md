# Component 3: Viva Preparation

These are concise answers, grounded in the implementation and the stored results.

## Research problem

**Why is this problem important?**
A multi-channel media organisation needs to know which of its channels are connected through their audiences, for example for cross-promotion or content planning. It only has public evidence for this. Turning sparse, noisy public signals into a ranked, explainable list for each channel is a practical, non-trivial problem.

## Research gap

**What is missing from existing work?**
Existing studies measure commenter overlap, detect communities, embed channels or compute graph proximity, but they do these **separately**, and mostly to describe groups. We did not find a method that combines diffusion, learned graph similarity, content similarity and evidence quality into a **directional, per-source, explainable ranking** of potential bridges. That finding comes from a targeted, not systematic, search.

## Novelty

**What is actually your contribution?**
The integrated, confidence-gated framework and its formulation for this task, evaluated against baselines. The individual techniques (PPR, metapath2vec, HGT, E5, shrinkage) are established, and I do not claim them. STEP 32 classified it as a moderate potential contribution.

## Data

**Why the YouTube Data API?**
It is the official, terms-governed source of public channel, video and comment data. It needs no private analytics, and the data can be reproduced from snapshots.

## Graph

**Why a heterogeneous graph?**
Commenters, videos, channels and topics play different roles. A projection onto channels alone would discard the video and topic layers and the multi-hop paths through them, so a typed graph keeps that information for both diffusion and metapath2vec.

## metapath2vec

**Why use it?**
It learns type-aware embeddings guided by meaningful paths, for example CVC (co-commenting), ChVCVCh (channel–audience–channel) and VTV (shared topic). It is deterministic (seeded, single worker) and its channel similarities separate channels well: cosine 0.20–0.56.

## HGT

**Why include HGT?**
As an alternative: an attention-based heterogeneous GNN, to test whether a learned message-passing model gives better channel representations. In this data it did not (see "HGT finding" below), so metapath2vec remains primary.

## PageRank

**Why Personalized PageRank?**
It measures multi-hop reachability from a specific source, which a pairwise overlap count cannot. It is directional by construction, because the walk restarts at the source. It is standard, convergent and interpretable.

## Topic similarity

**Why include semantic similarity?**
Shared commenters capture audience evidence; content similarity captures what the channels publish. It is multilingual, covering Sinhala, Tamil and English. It is gated by confidence, so content alone can never create a bridge.

## Confidence

**Why confidence weighting?**
A similarity based on one shared commenter is much weaker than one based on 36. The shrinkage n/(n+3) discounts thin evidence, and topic coverage discounts profiles built from little text. In the sensitivity analysis, removing confidence changed the top-1 destination for 9 of 18 sources, more than any other component.

## Audience Bridge Score

**How is it calculated?**

```
score(s → d) = [ (1/3)·norm_PPR(s→d) + (1/3)·norm_m2v(s,d) + (1/3)·norm_topic(s,d) ] × n/(n+3) × min(coverage_s, coverage_d)
```

- Normalisation is per-source min-max, and ranking is per source with deterministic ties.
- The score lies in [0, 1).
- Missing components give a NULL score, never 0.

## Directionality

**What does source → destination mean?**
"Starting from this source channel, which destinations are most strongly connected to it?"
- Direction comes from PPR, which is personalised to the source, and from per-source normalisation.
- The evidence term and topic similarity are symmetric.
- It is a ranking question, **not** observed movement of people.

## Baselines

**Why Louvain?**
It is the standard "overlap communities" view. If bridges were just community membership, the score would match it. It doesn't: Spearman 0.33.

**Why node2vec?**
It is the standard homogeneous-embedding view. It isolates the value of type-aware paths and of the combined score: Spearman −0.29.

## Simple overlap

**Why not just count shared commenters?**
I tested exactly that with a simple-overlap baseline. On Derana the score agrees closely with the count (Spearman 0.99 over all pairs, inflated by shared zeros; about 0.8 among pairs that share commenters), and it picks a different top bridge for 3–4 of 13 channels. So with today's sparse data, the evidence term dominates. The diffusion, embedding and topic components mainly break ties and reorder close pairs, and they add an explanation of *why* a pair is connected. Showing a larger added value needs bigger same-period collections and expert labels; I report this as a limitation, not a strength.

## Evaluation

**How do you know the method works?**
I can show that it is **consistent, robust and different**, not that it is correct, because no labels exist:
- **Different:** agreement with Louvain is 0.33 and with node2vec −0.29.
- **Consistent:** temporal Spearman is 0.946, over 1.5 days with largely shared data.
- **Robust:** at 50 % of comments, Spearman is 0.814, better than both baselines.
- **Explainable:** decomposition error is 0.

Correctness would need expert labels, which is future work.

## Limitations

**Can you prove audience migration?**
No. The system identifies potential audience bridges based on observed public interaction and content evidence. A snapshot of shared commenters shows co-activity, not movement, and no causal or subscription data is observed.

## HGT finding

**Why did HGT produce highly similar channel vectors?**
Channel–channel cosine was 0.90–1.00 (median 0.978) on the main snapshot and 0.96–1.00 (median 0.989) on the newest.
- HGT was trained only on commenter→video link prediction. Nothing in that objective pushes channels apart.
- With 18 channel nodes and message passing through shared video and commenter nodes, the channel representations converge.
- Validation loss (2.77) far above training loss (0.46) also suggests that it fits edges without learning channel-level structure.

It is reported as a negative result. The main score uses metapath2vec.

## Computational cost

**Why did evaluation take so long?**
The recorded total was 67,504 s (about 18.75 h), but one single metapath2vec retraining in a sparse run accounts for 62,287 s; the identical step for the other seed took 52 s. That points to the machine being suspended or overloaded; the cause was not recorded. Without it, the run took about 1.4 h. The genuine systematic cost is that sparse robustness re-runs the score, PPR, metapath2vec, Louvain and node2vec per subsample, and node2vec is the slowest (350–1,800 s per run). A later full evaluation with 9 sparse runs took 2.5 h with no outlier, which confirms this.
