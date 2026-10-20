# Component 3: Final Research Overview

## Title

**Diffusion-Based Cross-Channel Audience Bridge Scoring**

Owner: Koonara K M K C (IT23200760) · SLIIT J26-DS-334

## Research Problem

A media organisation runs many YouTube channels. For each channel, it wants to know which of its other channels share, or could reach, a related audience: its **potential cross-channel audience bridges**.

Public data gives only partial evidence of this:
- who commented where (public comments)
- what each channel publishes (video titles and descriptions)
- the multi-hop structure linking commenters, videos, channels and topics

The research question is how to turn this partial, noisy evidence into a **ranked, directional, explainable** list of potential bridges for each source channel. A second question is how far that ranking agrees with simpler, established methods.

## Research Gap

This is the gap validated in STEP 32 ([component3_research_position.md](component3_research_position.md)). It is unchanged here.

The relevant signals are already studied **separately** in the literature:
- commenter-overlap statistics
- community detection
- channel embeddings
- Personalized PageRank proximity
- content similarity
- evidence shrinkage

YouTube overlap studies describe groups and communities; they do not rank individual channel pairs. In a targeted (non-systematic) search, we did **not** find work that combines the following into a **directional, per-source ranking of potential audience bridges**, with an explainable decomposition and an evaluation against community-detection and embedding baselines:
- heterogeneous commenter–video–channel–topic diffusion
- learned graph similarity
- content similarity
- evidence-based confidence

This is absence of evidence. A systematic review is still required.

## Proposed Solution

```
public comments + video metadata (one immutable snapshot)
→ heterogeneous graph (commenter, video, channel, topic)
→ graph features and shared-commenter evidence
→ learned graph similarity: metapath2vec (primary) / HGT (alternative)
→ diffusion: Personalized PageRank from each source channel
→ content similarity: multilingual-E5 channel topic profiles
→ Audience Bridge Score = (w_d·diffusion + w_e·embedding + w_t·topic) × confidence
→ per-source directional ranking + explanations
→ evaluation against Louvain, node2vec and the score's own components
```

## Research Contribution

This is the conservative statement retained after the STEP 32 novelty audit:

> This research proposes a **confidence-weighted framework for ranking potential directional cross-channel audience bridges**. It integrates heterogeneous audience–content–channel relationships, graph-based diffusion, learned graph similarity, semantic content similarity and evidence-quality factors, and it evaluates the resulting ranking against established community-detection and graph-embedding baselines.

Every building block is an established technique. The contribution is the **task-specific integration and formulation**. STEP 32 classified it as a **moderate potential contribution**. See [component3_contribution_statement.md](component3_contribution_statement.md).

## Research Scope

**What the system does:** for each of the 18 research channels (the Derana channel set), it ranks every other channel by a confidence-weighted score built from public commenter co-activity, graph reachability, learned graph similarity and content similarity. Each score comes with its decomposition and supporting evidence.

**What it does not do:**
- observe or claim audience migration, subscriber transfer or causal influence
- forecast growth
- infer demographics
- use private viewer data
- represent all viewers: commenters are a self-selected subset
- prove accuracy: no ground-truth labels exist

See [component3_claims_and_boundaries.md](component3_claims_and_boundaries.md).
