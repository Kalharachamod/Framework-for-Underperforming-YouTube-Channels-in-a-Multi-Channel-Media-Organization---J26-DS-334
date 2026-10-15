# Component 3: Novelty Threat Analysis

STEP 32 audits each methodological element of Component 3 against the literature found so far, so that established techniques are never presented as novel. Reference keys ([F1], [R1] …) are listed in [component3_research_position.md](component3_research_position.md#references).

**Categories:**
- **A — Clearly established:** the technique or idea already exists.
- **B — Existing technique, new context:** application value only.
- **C — Combination that may be novel:** a **potential contribution**, requires literature validation.
- **D — Potentially novel formulation:** the exact formulation was not found in this search. A **proposed contribution**, requires literature validation.

No element is "proven novel". C and D are statements about what this search did *not* find.

---

## 1. Audit of the implemented elements

| Element (where implemented) | Category | Classification | Basis |
|---|---|---|---|
| YouTube Data API collection (`shared/data_collection/`) | A | Existing technique | Standard data source in every cited YouTube study [R1–R5]. |
| Commenter overlap / shared commenters (STEP 14 `channel_pair_features`) | A | Existing technique | Jaccard and overlap coefficients on shared commenters [R1, R2, R3]. |
| Commenter–channel relationships (`participates_in`) | A | Existing technique | Channel–commenter bipartite graphs [R2]. |
| Heterogeneous graph: commenter, video, channel, topic (STEP 13) | B | Existing technique, new context | Heterogeneous information networks are established [F2, F3, R8]. This node and relation schema built for audience bridging is a *proposed application* (see §5). |
| Graph features (STEP 14) | A | Existing technique | Degree, overlap, activity counts. |
| metapath2vec (STEP 15) | A | Existing technique | Dong et al. 2017 [F2]. |
| HGT (STEP 16) | A | Existing technique | Hu et al. 2020 [F3]. |
| Personalized PageRank (STEP 17) | A (technique) / B (use) | Existing technique, proposed application | PageRank [F1], topic-sensitive / personalised PageRank [F6], PPR on heterogeneous graphs [R9]. Its use as an audience-reachability signal between channels is an application. |
| Topic modelling / semantic similarity (STEP 18) | A (technique) / B (use) | Existing technique, proposed application | Multilingual E5 embeddings [F7]; KMeans topic clusters; semantic channel embeddings exist [R7]. |
| Confidence weighting (STEP 19) | A (concept) / C (formulation for this task) | Proposed combination | Shrinkage `n/(n+λ)` [R11] and significance weighting [R10] are established. Multiplying it by topic-profile coverage for audience-bridge scoring is a proposed formulation. |
| Audience Bridge Score (STEP 19) | C / D | **Potential contribution** | A weighted linear combination of normalised signals times a confidence is a common pattern (hybrid scoring). The specific integration of these signals for directional cross-channel audience bridges was not found. |
| Directional ranking (STEP 19) | B / C | Proposed application / combination | Directional and asymmetric audience relations are documented [R1, R2]. Per-source ranking with PPR is an application. Combined with the other signals it is part of the C-level contribution. |
| Explainability: decomposition, reasons, evidence states (STEP 22) | B | Application contribution | Additive decomposition and rule-based reasons are standard. Exposing them for each bridge is application value. |
| Louvain baseline (STEP 20) | A | Existing technique | Blondel et al. 2008 [F5]. Used only as a baseline. |
| node2vec baseline (STEP 20) | A | Existing technique | Grover & Leskovec 2016 [F4]. Used only as a baseline. |
| Temporal validation (STEP 21) | A | Existing evaluation practice | Rank-stability across snapshots. |
| Sparse-data robustness (STEP 21) | A | Existing evaluation practice | Subsampling robustness analysis. |
| Evaluation design: agreement, top-k, stability, robustness, performance (STEP 21) | B | Proposed application | The metrics are standard. The evaluation protocol for this ranking task is part of the study design, not a methodological novelty. |

---

## 2. Audit of the Audience Bridge Score

### 2.1 Formula actually implemented (correction to the STEP 32 brief)

The STEP 32 brief quotes a **two-part** base score (`w_d × diffusion + w_t × topic`). The implemented method since method version 2.0 (team decision 2026-10-10) is **three-part**:

```
base_score = w_d × norm_diffusion + w_e × norm_embedding_similarity + w_t × norm_topic_similarity   (w_d + w_e + w_t = 1)
confidence = [n / (n + k)] × min(topic_coverage(source), topic_coverage(destination))              (k = 3)
AudienceBridgeScore = base_score × confidence
```

`w_e` can be set to 0 (`--embedding-source none`), which reproduces the two-part form as an ablation. Runs from method 1.x are the two-part form. **The formula was not changed in this step.** The proposal text should state the three-part form, or name the two-part form explicitly as the ablation.

### 2.2 Questions

| Question | Finding |
|---|---|
| 1. Is this exact formulation already in the literature? | **Not found.** No source in this search combines PPR, embedding similarity and topic similarity with an `n/(n+k)` × coverage confidence for channel→channel ranking. This is absence of evidence from a non-systematic search → *requires literature validation*. |
| 2. Are similar formulas used? | **Yes, structurally.** Weighted linear combinations of normalised similarity signals are standard in hybrid recommenders. Multiplying a similarity by a support factor is standard in neighbourhood CF [R10, R11]. PathRank mixes collaborative and content signals in a PPR framework [R9]. |
| 3. Are diffusion and semantic similarity commonly combined? | **Yes, in recommendation** (hybrid graph + content recommenders, PathRank [R9]; Tube2Vec combines social and semantic channel signals [R7]). Not found combined for cross-channel *audience-bridge* ranking. |
| 4. Is evidence / confidence weighting common? | **Yes.** Significance weighting [R10] and shrinkage [R11] are textbook. Component 3's `n/(n+k)` is the same shrinkage form. |
| 5. Is a directional score of this type used for YouTube audience analysis? | Directional or asymmetric audience *relations* are studied (temporal migration [R1]; conditional overlap percentages [R2]). A directional, multi-signal **score** for ranking individual channel pairs was **not found**. |
| 6. Is the combination specific to cross-channel audience-bridge ranking? | **Yes, by design.** Normalisation is per source, the confidence gate means no shared commenters gives a score of 0, and the ranking is per source. This is task-specific engineering of known parts: a *proposed formulation* (Category C), not a new algorithm. |

---

## 3. Confidence weighting audit

- **What is established:** down-weighting a similarity by the amount of supporting evidence. Herlocker et al. 1999 [R10] introduced significance weighting. Bell & Koren 2007 [R11] use `n_ij/(n_ij+λ) · ρ_ij`. Component 3's `n/(n+k)` is the **same family**.
- **What is specific to Component 3 (the proposed contribution):**
  - **evidence** = public **shared commenters** between two channels (`k = 3`, the count at which confidence = 0.5)
  - multiplied by **topic-profile coverage** (the minimum usable-text share of the two channels), so a content signal built from little text is trusted less
  - the confidence **gates** the whole base score: no shared commenters gives confidence 0 and score 0, so content similarity alone can never create a "bridge"
- **Correction to the brief:** the confidence uses **only** shared-commenter count and topic coverage. Interaction counts, video coverage and temporal support are computed in STEP 22 as **explanation evidence**, not inside the confidence. They must not be described as confidence inputs.
- **Wording to use:** "confidence weighting is an established concept; our specific evidence- and coverage-based confidence for cross-channel audience bridge scoring is a proposed formulation."

---

## 4. Directionality audit

- **Existing work already models direction:**
  - Ribeiro et al. 2020 [R1] report users *migrating* from milder to more extreme channel categories over time.
  - Violot et al. 2025 [R2] report the share of one group's commenters also active in another group, which is source-conditioned and asymmetric.
  - **Claiming "directional audience relationships are new" is therefore not safe.**
- **Where Component 3's direction comes from (implementation fact):**
  1. **PPR is personalised to the source channel**: the reachability of B from A is not the reachability of A from B.
  2. **Normalisation and ranking are per source**: a destination is scored relative to that source's other candidates.
  3. **Evidence confidence `n/(n+k)` and topic similarity are symmetric.** Direction therefore comes **only** from diffusion and per-source normalisation. This should be stated plainly. A future option (not implemented, not required) is an asymmetric evidence term such as the share of the source's commenters also on the destination, which STEP 22 already reports as explanation evidence.
- **Remaining gap (potential):** direction is combined with diffusion, learned similarity, content similarity and confidence into one **per-channel ranking**. Related work found here describes direction at group level or temporally. The combination is a **Category C** potential contribution.
- **Never claim:** direction as audience flow or migration. The score is directional because the *ranking question* is directional ("from this source, which destinations?"), not because observed people moved.

---

## 5. Heterogeneous graph audit

| Aspect | Status |
|---|---|
| Heterogeneous information networks, meta-paths, type-aware GNNs | **Established** [F2, F3, R8] |
| Commenter–video and channel–commenter graphs on YouTube | **Established** [R2, R4, R5] |
| Video–topic links from text clusters | Established technique (topic models / embedding clusters) |
| **This schema:** commenter → video (`comments`), video → channel (`belongs_to`), commenter → channel (`participates_in`, derived), video → topic (`has_topic`), used to rank channel→channel audience bridges | **No exact precedent found** for this schema and purpose → *proposed application* (Category B/C), requires literature validation |
| Design choices specific to this problem | Topic edges excluded from PPR by default (to avoid counting content twice with topic similarity); derived `participates_in` edges excluded from diffusion; edge weights = comment counts |

**Do not claim** heterogeneous graphs, or YouTube interaction graphs, as novel.

---

## 6. Novelty claim checklist

| Claim | Safe to claim? | Reason |
|---|---|---|
| YouTube commenter overlap is new | **NO** | Established [R1, R2, R3] |
| Heterogeneous graph is new | **NO** | Established [F2, F3, R8] |
| metapath2vec is new | **NO** | Dong et al. 2017 [F2] |
| HGT is new | **NO** | Hu et al. 2020 [F3] |
| PageRank / PPR is new | **NO** | [F1, F6] |
| Topic / semantic similarity is new | **NO** | [F7, R7] |
| Directional audience networks are new | **NO** | Asymmetric / temporal audience relations documented [R1, R2] |
| Confidence weighting is new | **NO** | Established concept [R10, R11]; same `n/(n+k)` family |
| Proposed confidence formulation (shared-commenter shrinkage × topic coverage, gating the score) is a contribution | **POTENTIAL** | Formulation not found; needs systematic search and an ablation showing it matters |
| Diffusion + semantic similarity combination | **POTENTIAL** (for this task only) | Combined in recommendation [R9]; not found for audience-bridge ranking |
| Audience Bridge Score formulation | **POTENTIAL** | Exact prior art not found; structurally a standard weighted hybrid score |
| Integrated framework (heterogeneous graph → diffusion + learned similarity + content similarity + confidence → directional ranking) | **POTENTIAL CONTRIBUTION** | Main differentiation; gap must be established by a systematic review |
| Explainable decomposition | **APPLICATION CONTRIBUTION** | Additive decomposition is standard; its application to bridge ranking is useful but not methodological novelty |
| "First" / "novel algorithm" / "no previous work" | **NO** | Never supported by a non-systematic search |

---

## 7. Category summary

- **A (clearly established):** YouTube API, commenter overlap, commenter–channel bipartite graphs, graph features, metapath2vec, HGT, PageRank / PPR, sentence embeddings, Louvain, node2vec, evidence shrinkage, rank-stability and subsampling evaluation.
- **B (existing technique, new context):** the heterogeneous commenter–video–channel–topic schema for this task; PPR as audience reachability between channels; per-channel explainable decomposition.
- **C (combination that may be novel):** the integrated, confidence-gated, directional ranking framework; the confidence formulation for this task.
- **D (potentially novel formulation):** the exact Audience Bridge Score as specified (three normalised components, per-source normalisation, shrinkage × coverage confidence gate). Treat as D only after a systematic search; until then, report it as C.
