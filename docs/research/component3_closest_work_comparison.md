# Component 3: Closest-Work Comparison

These are the existing studies closest to Component 3, found in the STEP 32 search (web search of arXiv, AAAI/ICWSM, ACM, Springer and SAGE listings, October 2026).

**Reading levels:**
- **full**: the paper page or HTML text was read.
- **abstract**: only the abstract or listing was read.
- **summary**: known only from a search-engine summary. Verify before citing.

`?` means the information could not be verified in this step and is **not** filled in. Full references are in [component3_research_position.md](component3_research_position.md#references).

| Study | Read | Data | Graph | Audience relationship | Semantic signal | Diffusion | Confidence | Directional ranking | Main difference from Component 3 |
|---|---|---|---|---|---|---|---|---|---|
| Violot, Sosnovik & Humbert 2025, *Exploring YouTube's Political Communication Networks during the 2024 French Elections* [R2] | full | ~64 French news-media and politician channels; ~43.5k videos; 7.4M comments; ~700k commenters (YouTube API) | Video–commenter bipartite graphs; commenter projection; channel–commenter bipartite graph projected to a channel graph | Shared commenters, weighted by **Jaccard** (symmetric). Group-to-group "% of A's commenters also on B" (asymmetric, descriptive) | NER/LLM on titles and descriptions to find politicians; no content-similarity score between channels | No | No | No (descriptive network statistics) | Describes political communication networks. No per-source ranking, diffusion, content similarity or evidence weighting. |
| Ribeiro, Ottoni, West, Almeida & Meira 2020, *Auditing Radicalization Pathways on YouTube* (FAT*) [R1] | abstract | 349 channels; 330,925 videos; 72M+ comments; 2M+ recommendations | Channel / commenter overlap over time; recommendation graph | Shared user base growing over time; **users migrating** from milder to more extreme channels (temporal, directional) | Channel categories (manual) | Recommendation reachability (not PPR) | ? | No (group-level pathways) | Directional *temporal migration* between channel **categories**. Component 3 makes no migration claim and ranks individual channel pairs from a static snapshot. |
| Boesinger, Horta Ribeiro, Veselovsky & West, *Tube2Vec: Social and Semantic Embeddings of YouTube Channels* (arXiv 2023; listed in ICWSM proceedings) [R7] | abstract + summary | 44k channels; Reddit sharing; recommendations; metadata | Channel graph from recommendations (node2vec, per search summary) | Social-sharing similarity (Reddit), not commenter co-activity | **Yes**: semantic embeddings from metadata / recommendations | node2vec random walks (embedding, not PPR scoring) | No | No | The closest "social + semantic channel representation" work. It produces embeddings evaluated on partisanship and semantic tasks, not a confidence-weighted directional bridge ranking from commenter co-activity. |
| Clark & Zaitsev 2020, *Understanding YouTube Communities via Subscription-based Channel Embeddings* (arXiv) [R12] | abstract | Commenters' public subscription pages; annotated political channel tags | Self-supervised channel embeddings from subscriptions (word2vec-style per summary) | Co-subscription (audience-side) | No | No | No | No | Audience-based channel embeddings for classification and discovery. It does not rank directional bridges or combine signals. |
| Shajari, Alassad & Agarwal 2023, *Commenter Behavior Characterization on YouTube Channels* / *Detecting Suspicious Commenter Mob Behaviors … Graph2Vec* [R4, R5] | abstract + summary | 20 channels; 7,782 videos; ~294k commenters | Per-channel co-commenter networks | Co-commenting inside a channel | No | No | No | No | Detects coordinated or anomalous commenter behaviour; different goal. |
| Trujillo, Gruppi, Buntain & Horne 2020, *What is BitChute?* (HT'20 long version) [R3] | abstract + summary | BitChute channels and comments | Channel audience-overlap network (shared commenters; per summary, a share-of-commenters weight with a 10% threshold and greedy modularity) | Shared commenters (symmetric) | No | No | Threshold only | No | Platform characterisation, not ranking. Edge-weight details known only from a summary. |
| Lee & Oh, *Memes, gatekeepers, and the dynamics of viral K-pop diffusion on YouTube* (Convergence, 2025/26) [R13] | summary | Commenter-overlap networks around four viral songs (per summary) | Channel commenter-overlap network; ERGM (per summary) | Shared commenters; mid-tier channels as **brokers** (per summary) | ? | "Diffusion" of virality (not graph diffusion scoring) | ? | No | Close in vocabulary ("brokers" between subnetworks) but explanatory network modelling, not ranking. Must be read in full before citing. |
| PathRank (heterogeneous-graph PPR for hybrid recommendation) [R9] | abstract | Recommendation datasets | Heterogeneous graph | User–item | Content-based paths (hybrid) | **Yes** (PPR variant) | ? | Ranks items per user | Closest *methodological* analogue (PPR on a heterogeneous graph mixing collaborative and content signals), but for user→item recommendation, not channel→channel audience bridges. |
| Bell & Koren 2007, *Improved Neighborhood-based CF* [R11] | summary (formula confirmed via secondary sources) | Netflix Prize | Item–item neighbourhoods | Co-rating users | No | No | **Yes**: shrinkage `n/(n+λ)` | Ranks neighbours | Same family of evidence-shrinkage factor as Component 3's `n/(n+k)`. Component 3 reuses the idea and does not claim it. |

## What this comparison shows

- **Commenter-overlap channel networks are well established** [R1–R6, R13]. Component 3's basic data signal is not new.
- **Asymmetric / directional audience relations are documented** at group level: temporal migration [R1] and conditional percentages [R2]. "Directional audience relationships" must not be claimed as new.
- **Social + semantic channel representations exist** (Tube2Vec [R7]), as do **PPR on heterogeneous graphs mixing collaborative and content signals** [R9] and **evidence shrinkage** [R10, R11].
- **Not found in this search:** a framework that ranks, per source channel, *potential directional audience bridges* by combining
  - heterogeneous commenter–video–channel–topic diffusion
  - learned graph similarity
  - content similarity
  - shared-commenter evidence shrinkage

  …with an explainable decomposition, evaluated against Louvain and node2vec baselines. This is the remaining differentiation. Because it rests on the *absence* of a found match, it is a **potential** contribution that requires a systematic search (Scopus / Google Scholar / ACM DL) before it is stated as a gap.
