# Component 3: Contribution Statement

This statement was validated in STEP 32 ([component3_research_position.md](component3_research_position.md)), with the overall decision **MODERATE POTENTIAL CONTRIBUTION**.

## Primary Contribution

**The Audience Bridge Scoring framework:** a confidence-weighted framework for ranking potential directional cross-channel audience bridges. It integrates:
- heterogeneous audience–content–channel relationships
- graph-based diffusion
- learned graph similarity
- semantic content similarity
- evidence-quality factors

The resulting ranking is evaluated against established community-detection (Louvain) and graph-embedding (node2vec) baselines.

The contribution is the **task-specific integration and formulation**, not any individual technique. It is a *potential* contribution until a systematic literature review confirms the gap.

## Supporting Contributions

| Supporting contribution | What is new here | What is established (not claimed) |
|---|---|---|
| Heterogeneous audience–content–channel modelling | The commenter–video–channel–topic schema used for bridge ranking | Heterogeneous information networks; YouTube co-commenter graphs |
| Graph-based diffusion | PPR from each channel as an audience-reachability signal between channels | PageRank / Personalized PageRank |
| Semantic content similarity | Multilingual (Sinhala / Tamil / English) channel content profiles as one gated score component | Sentence embeddings (multilingual E5) |
| Evidence-quality confidence weighting | Shared-commenter shrinkage × topic coverage, **gating** the score so content alone cannot create a bridge | Shrinkage `n/(n+k)` (Bell & Koren 2007); significance weighting |
| Directional bridge ranking | A per-source ranking combining all signals; direction from PPR and per-source normalisation | Asymmetric audience relations (documented at group level) |
| Explainable decomposition | Exact per-pair decomposition, evidence and rule-based reasons exposed in a dashboard | Additive decomposition |

## What is not claimed

- That metapath2vec, HGT, node2vec, Louvain, PageRank / PPR, E5 embeddings, evidence shrinkage, heterogeneous graphs or commenter overlap are new.
- Superior accuracy (there are no labels).
- That the framework reveals migration, causality or growth.

## Thesis wording

> "This research proposes and evaluates a confidence-weighted framework for ranking potential directional cross-channel audience bridges. The framework integrates established techniques (heterogeneous graph modelling, Personalized PageRank diffusion, metapath2vec embeddings, multilingual semantic similarity and evidence shrinkage) into a single, explainable, per-source ranking. It is compared with Louvain and node2vec baselines."
