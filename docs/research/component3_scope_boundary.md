# Component 3: Scope Boundary (what it does **not** claim)

Component 3 identifies **potential cross-channel audience bridges based on observed public interaction and content evidence**. For each source channel it ranks other channels by a confidence-weighted score built from graph diffusion, learned graph similarity and content similarity over **public YouTube comments and video metadata** collected for one research snapshot.

## Component 3 does NOT claim

| Not claimed | Why |
|---|---|
| **Actual audience migration** | The data is a static snapshot of who commented where. A high score means overlap and reachability, not that viewers moved from one channel to another. |
| **Actual subscriber movement / transfer** | Subscriptions are not observed per user. Only public channel-level subscriber counts are stored, and they are never linked to commenters. |
| **Causality** | No intervention or counterfactual is modelled. Shared commenters may reflect common interests, recommendation exposure, collaborations or chance. |
| **Future audience growth** | The score is not a forecast. Temporal-stability checks (STEP 21) measure whether rankings are stable across snapshots, not whether audiences grow. |
| **Guaranteed recommendations** | Rankings are research signals for analysts. Acting on them (for example cross-promotion) is outside the evaluated scope, and outcomes are not guaranteed. |
| **Demographic inference** | No age, gender, location or other personal attribute is inferred or stored. |
| **Private viewer behaviour** | Only **public comments** are used. Silent viewers, watch time, likes by individual users and private activity are invisible to the method. |
| **Complete YouTube audience representation** | Commenters are a small, self-selected subset of viewers. Collection covers a bounded number of recent videos per channel, and the channel set is fixed (18 Derana channels in the current snapshot). |
| **Novelty of the individual techniques** | PageRank / PPR, metapath2vec, HGT, sentence embeddings, Louvain, node2vec and evidence shrinkage are established methods (see [component3_novelty_threat_analysis.md](component3_novelty_threat_analysis.md)). |
| **Validated accuracy** | No ground-truth relevance labels exist. Evaluation reports consistency (agreement with baselines, temporal stability, sparse-data robustness), not correctness. |

## What the system does identify

> Potential cross-channel audience bridges based on observed public interaction and content evidence: for a source channel, which other research channels are most strongly connected to it through shared public commenters, multi-hop graph reachability and similar published content, weighted by how much evidence supports each pair.

## Privacy boundary

Commenter identities are pseudonymised (salted hashes) in storage and never shown. Every result leaving the pipeline is an aggregate (counts, similarities, channel-level values). See [../architecture/privacy.md](../architecture/privacy.md).
